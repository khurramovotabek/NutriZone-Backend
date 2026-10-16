"""
Products API views.

Thin per Django Implementation Blueprint §3: each view deserializes
the request, calls exactly one Application Service (built via
infrastructure/composition.py), and returns the result through the
standard response envelope (common/responses/). Views never access the
ORM directly -- every read goes through a Selector-backed Application
Service, every write through a Repository-backed Application Service.
Matches `apps/identity/interfaces/api/v1/views.py`'s pattern exactly.
"""
from __future__ import annotations

import uuid

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from apps.products.infrastructure import composition
from apps.products.infrastructure.selectors import (
    BrandSelector,
    CategoryTreeSelector,
    FilterSelector,
    FlavourSelector,
    PackageSelector,
)
from apps.products.interfaces.api.v1.filters import (
    parse_admin_catalog_list_params,
    parse_catalog_list_params,
    parse_search_params,
)
from apps.products.interfaces.api.v1.permissions import (
    BrandPermission,
    CatalogArchivePermission,
    CatalogManagePermission,
    CatalogMediaPermission,
    CatalogPublishPermission,
    CatalogSEOPermission,
    CatalogViewPermission,
    CategoryPermission,
    VariantPermission,
)
from apps.products.interfaces.api.v1.serializers import (
    AdminProductDetailSerializer,
    AdminProductListItemSerializer,
    ArchiveProductSerializer,
    AssignBrandSerializer,
    AssignCategorySerializer,
    AssignFlavoursSerializer,
    AssignTagsSerializer,
    CloneProductSerializer,
    CreateProductSerializer,
    CreateVariantSerializer,
    DuplicateProductSerializer,
    FilterMetadataSerializer,
    HideProductSerializer,
    PublicProductDetailSerializer,
    PublicProductListSerializer,
    PublishProductSerializer,
    RelatedProductSerializer,
    RestoreProductSerializer,
    UpdateDirectionsSerializer,
    UpdateIngredientsSerializer,
    UpdateNutritionFactsSerializer,
    UpdateProductSerializer,
    UpdateSEOSerializer,
    UpdateVariantSerializer,
    UpdateWarningsSerializer,
    UploadMediaSerializer,
)
from common.exceptions import ValidationFailed
from common.responses import paginated_response, success_response
from common.utils.localization import resolve_locale
from core.metrics import default_collector
from core.observability import timed
from core.openapi import STANDARD_ERROR_RESPONSES
from core.ratelimit import ScopedRateLimitThrottle


def _responses(*codes: int) -> dict:
    return {code: STANDARD_ERROR_RESPONSES[code] for code in codes}


def _attach_identity(request) -> None:
    request.identity = request.user


def _actor_id(request):
    return getattr(getattr(request, "user", None), "id", None)


class CreateProductThrottle(ScopedRateLimitThrottle):
    scope = "products.create"
    limit = 60
    window_seconds = 3600
    identifier_source = "user"


class PublishProductThrottle(ScopedRateLimitThrottle):
    scope = "products.publish"
    limit = 100
    window_seconds = 3600
    identifier_source = "user"


class UploadMediaThrottle(ScopedRateLimitThrottle):
    scope = "products.upload_media"
    limit = 100
    window_seconds = 3600
    identifier_source = "user"


class DeleteMediaThrottle(ScopedRateLimitThrottle):
    scope = "products.delete_media"
    limit = 100
    window_seconds = 3600
    identifier_source = "user"


class UpdateSEOThrottle(ScopedRateLimitThrottle):
    scope = "products.update_seo"
    limit = 100
    window_seconds = 3600
    identifier_source = "user"


class AdminOperationThrottle(ScopedRateLimitThrottle):
    scope = "products.admin_operation"
    limit = 600
    window_seconds = 3600
    identifier_source = "user"


# ============================================================
# Public endpoints
# ============================================================


class BestSellersView(APIView):
    """`GET /products/best-sellers` -- real, public (AllowAny). Ranking derived from confirmed order data (apps.ordering), not a fabricated badge -- see CatalogSelector.list_best_sellers()'s own docstring."""

    permission_classes = [AllowAny]

    @extend_schema(tags=["Products"], summary="List best-selling products by real sales volume", responses={200: OpenApiResponse(description="Best-selling products")})
    def get(self, request):
        from apps.products.infrastructure.selectors import CatalogSelector

        limit = min(int(request.query_params.get("limit", 8)), 20)
        return success_response(data=CatalogSelector().list_best_sellers(limit=limit, locale=_explicit_locale(request, "filter[locale]")))


class ProductListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Products"], summary="List published products", responses={200: PublicProductListSerializer(many=True), **_responses(422)})
    def get(self, request):
        """
        Reads go through the Selector directly, not a round-trip
        through an Application Service that would just discard its own
        result -- `CatalogSelector.list()` already enforces the same
        "PUBLISHED only" rule `ListProducts` (application/services/
        queries.py) enforces, since a Selector is itself a read-only,
        zero-business-logic layer (Django Implementation Blueprint §3).
        Calling both would mean querying the same data twice for no
        benefit; this is the CQRS-lite read path, writes always go
        through an Application Service (see every POST/PATCH/DELETE
        view below).
        """
        params = parse_catalog_list_params(request.query_params)
        default_collector.counter("catalog_queries_total")
        from apps.products.infrastructure.selectors import CatalogSelector

        cards, total = CatalogSelector().list(category_id=params.category_id, brand_id=params.brand_id, page=params.page, page_size=params.page_size, locale=_explicit_locale(request, "filter[locale]"))
        total_pages = max((total + params.page_size - 1) // params.page_size, 1)
        return paginated_response(data=cards, pagination={"strategy": "page", "page": params.page, "page_size": params.page_size, "total_pages": total_pages, "total_count": total})


class ProductDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Products"], summary="Get a published product by slug", responses={200: PublicProductDetailSerializer, **_responses(404)})
    def get(self, request, slug: str):
        """
        Existence + visibility (PUBLISHED-only) is still enforced by
        the domain: `GetProduct` (application/services/queries.py)
        raises ResourceNotFound for anything else, and IS called here
        specifically for that enforcement (unlike ProductListView, this
        endpoint's whole job is a single-item lookup where the
        Application Service's business-rule check is the point, not
        redundant with the selector).
        """
        default_collector.counter("catalog_queries_total")
        composition.build_get_product().execute(slug)
        from apps.products.infrastructure.selectors import ProductDetailSelector

        locale = resolve_locale(request, explicit=request.query_params.get("filter[locale]"))
        card = ProductDetailSelector().get_by_slug(slug, locale=locale)
        return success_response(data=card)


class ProductRecommendationsView(APIView):
    """
    Phase 02J: closes the confirmed "built but never wired" gap --
    `ProductRecommendation`/`RelatedProduct`/`RelationType` already
    existed with zero HTTP surface. `AllowAny`, matching
    `ProductDetailView`'s own precedent -- recommendations for a
    publicly-viewable product are themselves public, anonymous-safe
    data (Step 7).
    """

    permission_classes = [AllowAny]

    @extend_schema(tags=["Products"], summary="Get related/recommended products for a published product", responses={200: RelatedProductSerializer(many=True), **_responses(404)})
    def get(self, request, slug: str):
        default_collector.counter("catalog_queries_total")
        composition.build_get_product().execute(slug)  # existence + PUBLISHED-only validation only -- reused, never duplicated
        from apps.products.infrastructure.selectors import ProductDetailSelector, RecommendationSelector

        card = ProductDetailSelector().get_by_slug(slug)
        cards = RecommendationSelector().for_product(uuid.UUID(card["id"]), locale=_explicit_locale(request, "filter[locale]"))
        return success_response(data=cards)


class PersonalizedRecommendationsView(APIView):
    """
    Phase 03B: closes the gap Phase 02J's own report explicitly
    disclosed as never implemented -- purchase-history-based
    recommendations. Distinct from `ProductRecommendationsView`
    (product-scoped, "what's similar to X", public) -- this endpoint
    is customer-scoped ("what should this customer see"),
    authenticated, and resolves the customer strictly from
    `request.identity.id`, never a client-supplied value, matching
    this phase's own explicit security rule.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Products"], summary="Get personalized product recommendations for the authenticated customer")
    def get(self, request):
        default_collector.counter("catalog_queries_total")
        _attach_identity(request)
        from apps.products.infrastructure import personal

        # every purchase (store tills + online), bought-together / goal / category signals, a reason per card
        cards = personal.for_customer(request.identity.id, _explicit_locale(request, "filter[locale]") or "uz")
        return success_response(data=cards)


class VariantDisplayView(APIView):
    """`GET /products/variants?ids=<uuid>,<uuid>` -- product name/photo/size per variant id, so order and cart screens can show what was bought (their lines only carry `product_variant_id`). At most 100 ids per call."""

    permission_classes = [AllowAny]

    @extend_schema(tags=["Products"], summary="Resolve display info (name, photo, size) for variant ids")
    def get(self, request):
        from apps.products.infrastructure.selectors import VariantDisplaySelector

        raw = request.query_params.get("ids", "")
        ids = [part.strip() for part in raw.split(",") if part.strip()]
        locale = resolve_locale(request, explicit=request.query_params.get("locale"))
        return success_response(data=VariantDisplaySelector().resolve(ids, locale=locale))


class ProductSearchView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Products"], summary="Full-text + faceted product search", responses={200: OpenApiResponse(description="Search results with facets"), **_responses(422)})
    def get(self, request):
        params = parse_search_params(request.query_params)
        locale = resolve_locale(request, explicit=request.query_params.get("filter[locale]"))
        with timed("products.search_duration"):
            result = composition.build_search_products().execute(query=params.query, filters=params.filters, page=params.page, page_size=params.page_size, sort=params.sort, locale=locale)
        total_pages = max((result["total_count"] + params.page_size - 1) // params.page_size, 1)
        # `record=1`: a submitted search (the catalog page, the bot) -- counted for search analytics; type-ahead previews are not.
        if params.query and params.page == 1 and request.query_params.get("record") == "1":
            from apps.search.infrastructure.repositories import record

            record(params.query, result["total_count"], locale)
        return paginated_response(
            data=result["results"],
            pagination={"strategy": "page", "page": params.page, "page_size": params.page_size, "total_pages": total_pages, "total_count": result["total_count"]},
            # "suggestion": the corrected query ("did you mean") when the smart engine matched only fuzzily; null otherwise.
            meta_extra={"facets": result["facets"], "suggestion": result.get("suggestion")},
        )


class PopularSearchesView(APIView):
    """`GET /products/search/popular` -- the most searched terms of the last 30 days that find products (storefront suggestion chips)."""

    permission_classes = [AllowAny]

    @extend_schema(tags=["Products"], summary="Popular search terms")
    def get(self, request):
        from apps.search.infrastructure.repositories import popular

        try:
            limit = max(1, min(int(request.query_params.get("limit") or 8), 20))
        except ValueError:
            limit = 8
        return success_response(data=popular(limit))


def _explicit_locale(request, param: str = "locale") -> str | None:
    """`?locale=` (or `?filter[locale]=`) > `Accept-Language` > the platform default (uz) -- a caller that forgets the param still gets the shopper's language, never silent English."""
    return resolve_locale(request, explicit=request.query_params.get(param))


class CartRecommendationsView(APIView):
    """`GET /products/recommendations/for-cart?ids=<variant or product ids>` -- "often bought together" with what's in a cart (guest or signed in)."""

    permission_classes = [AllowAny]

    @extend_schema(tags=["Products"], summary="Cross-sell for a cart: products often bought together with its items")
    def get(self, request):
        from apps.products.domain.enums import ProductStatus
        from apps.products.infrastructure import co_purchase
        from apps.products.infrastructure import models as orm
        from apps.products.infrastructure.selectors import _cards_with_price_and_rating

        ids = []
        for raw in (request.query_params.get("ids") or "").split(",")[:30]:
            try:
                ids.append(uuid.UUID(raw.strip()))
            except ValueError:
                continue
        # a cart knows variants, a product page knows products -- either works
        variant_products = dict(orm.ProductVariant.objects.filter(id__in=ids).values_list("id", "product_id"))
        product_ids = {variant_products.get(i, i) for i in ids}
        suggested = co_purchase.for_basket(product_ids, 8) if product_ids else []
        rows = {p.id: p for p in orm.Product.objects.filter(id__in=suggested, status=ProductStatus.PUBLISHED.value).prefetch_related("translations", "media", "variants")}
        ordered = [rows[pid] for pid in suggested if pid in rows]
        return success_response(data=_cards_with_price_and_rating(ordered, _explicit_locale(request, "filter[locale]")))


class CategoryListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Products"], summary="List categories (flat)")
    def get(self, request):
        return success_response(data=CategoryTreeSelector().tree(locale=_explicit_locale(request)))


class CategoryTreeView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Products"], summary="Category tree")
    def get(self, request):
        return success_response(data=CategoryTreeSelector().tree(locale=_explicit_locale(request)))


class BrandListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Products"], summary="List active brands")
    def get(self, request):
        # Names keep their long-standing default-locale behaviour; `?locale=` only picks the description language.
        return success_response(data=BrandSelector().list_active(description_locale=request.query_params.get("locale")))


class FlavourListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Products"], summary="List active flavours")
    def get(self, request):
        locale = resolve_locale(request)
        return success_response(data=FlavourSelector().list_active(locale=locale))


class GoalListView(APIView):
    """`GET /products/goals` -- the training goals ("shop by goal" cards) with how many published products serve each."""

    permission_classes = [AllowAny]

    @extend_schema(tags=["Products"], summary="Training goals with product counts")
    def get(self, request):
        from collections import Counter

        from apps.products.domain.enums import ProductStatus
        from apps.products.infrastructure import models as orm
        from apps.products.infrastructure.goals import GOALS, label

        locale = resolve_locale(request)
        counts = Counter(g for goals in orm.Product.objects.filter(status=ProductStatus.PUBLISHED.value).values_list("goals", flat=True) for g in (goals or []))
        return success_response(data=[{"code": code, "name": label(code, locale), "count": counts.get(code, 0)} for code in GOALS])


class PackageListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Products"], summary="List active package types")
    def get(self, request):
        locale = resolve_locale(request)
        return success_response(data=PackageSelector().list_active(locale=locale))


class TagListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Products"], summary="List tags")
    def get(self, request):
        tags = composition.build_tag_repository().list_all()
        return success_response(data=[{"id": str(t.id), "code": t.code, "name": t.name} for t in tags])


class CatalogFiltersView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Products"], summary="Faceted filter metadata", responses={200: FilterMetadataSerializer, **_responses(422)})
    def get(self, request):
        category_id = request.query_params.get("category_id")
        return success_response(data=FilterSelector().facets(category_id=category_id))


# ============================================================
# Admin: product lifecycle
# ============================================================


class AdminProductListCreateView(APIView):
    """
    Combined collection endpoint (`GET` list + `POST` create) at
    `/admin/products` -- a single URL, dispatched by HTTP method
    within one view class, per standard REST/DRF convention (two
    separate view classes registered on the identical path would leave
    the second unreachable, since Django's URLconf resolves by path
    pattern, not HTTP method).
    """

    def get_permissions(self):
        if self.request.method == "POST":
            return [CatalogManagePermission()]
        return [CatalogViewPermission()]

    def get_throttles(self):
        if self.request.method == "POST":
            return [CreateProductThrottle()]
        return [AdminOperationThrottle()]

    @extend_schema(tags=["Products Admin"], summary="List products (staff, any status)", responses={200: AdminProductListItemSerializer(many=True), **_responses(401, 403, 422)})
    def get(self, request):
        _attach_identity(request)
        params = parse_admin_catalog_list_params(request.query_params)
        from apps.products.infrastructure.selectors import AdminCatalogSelector

        cards, total = AdminCatalogSelector().list(status=params.status, query=params.query, page=params.page, page_size=params.page_size)
        total_pages = max((total + params.page_size - 1) // params.page_size, 1)
        return paginated_response(data=cards, pagination={"strategy": "page", "page": params.page, "page_size": params.page_size, "total_pages": total_pages, "total_count": total})

    @extend_schema(tags=["Products Admin"], summary="Create a product", request=CreateProductSerializer, responses={201: AdminProductDetailSerializer, **_responses(401, 403, 409, 422, 429)})
    def post(self, request):
        _attach_identity(request)
        serializer = CreateProductSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = composition.build_create_product(_actor_id(request)).execute(**serializer.validated_data)
        return success_response(data=_product_detail_payload(product), status_code=201)


class AdminProductDetailView(APIView):
    throttle_classes = [AdminOperationThrottle]

    def get_permissions(self):
        if self.request.method == "GET":
            return [CatalogViewPermission()]
        if self.request.method == "DELETE":
            return [CatalogArchivePermission()]
        return [CatalogManagePermission()]

    @extend_schema(tags=["Products Admin"], summary="Get a product (staff)", responses={200: AdminProductDetailSerializer, **_responses(401, 403, 404)})
    def get(self, request, product_id: str):
        _attach_identity(request)
        from common.exceptions import ResourceNotFound

        found = composition.build_product_repository().get_by_id(uuid.UUID(product_id))
        if found is None:
            raise ResourceNotFound("Product not found.")
        return success_response(data=_product_detail_payload(found))

    @extend_schema(tags=["Products Admin"], summary="Update a product", request=UpdateProductSerializer, responses={200: AdminProductDetailSerializer, **_responses(401, 403, 404, 422)})
    def patch(self, request, product_id: str):
        _attach_identity(request)
        serializer = UpdateProductSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        product = composition.build_update_product(_actor_id(request)).execute(product_id=uuid.UUID(product_id), **serializer.validated_data)
        return success_response(data=_product_detail_payload(product))

    @extend_schema(tags=["Products Admin"], summary="Delete a product (must already be archived)", responses={204: OpenApiResponse(description="Deleted"), **_responses(401, 403, 404, 409)})
    def delete(self, request, product_id: str):
        _attach_identity(request)
        composition.build_delete_product(_actor_id(request)).execute(uuid.UUID(product_id))
        return success_response(data=None, status_code=204)


class AdminProductPublishView(APIView):
    throttle_classes = [PublishProductThrottle]

    def get_permissions(self):
        return [CatalogPublishPermission()]

    @extend_schema(tags=["Products Admin"], summary="Publish a product", request=PublishProductSerializer, responses={200: AdminProductDetailSerializer, **_responses(401, 403, 404, 422)})
    def post(self, request, product_id: str):
        _attach_identity(request)
        product = composition.build_publish_product(_actor_id(request)).execute(uuid.UUID(product_id))
        return success_response(data=_product_detail_payload(product))


class AdminProductHideView(APIView):
    throttle_classes = [PublishProductThrottle]

    def get_permissions(self):
        return [CatalogPublishPermission()]

    @extend_schema(tags=["Products Admin"], summary="Hide a published product", request=HideProductSerializer, responses={200: AdminProductDetailSerializer, **_responses(401, 403, 404, 409)})
    def post(self, request, product_id: str):
        _attach_identity(request)
        product = composition.build_hide_product(_actor_id(request)).execute(uuid.UUID(product_id))
        return success_response(data=_product_detail_payload(product))


class AdminProductArchiveView(APIView):
    throttle_classes = [AdminOperationThrottle]

    def get_permissions(self):
        return [CatalogArchivePermission()]

    @extend_schema(tags=["Products Admin"], summary="Archive a product", request=ArchiveProductSerializer, responses={200: AdminProductDetailSerializer, **_responses(401, 403, 404, 409)})
    def post(self, request, product_id: str):
        _attach_identity(request)
        product = composition.build_archive_product(_actor_id(request)).execute(uuid.UUID(product_id))
        return success_response(data=_product_detail_payload(product))


class AdminProductRestoreView(APIView):
    throttle_classes = [AdminOperationThrottle]

    def get_permissions(self):
        return [CatalogArchivePermission()]

    @extend_schema(tags=["Products Admin"], summary="Restore an archived product to draft", request=RestoreProductSerializer, responses={200: AdminProductDetailSerializer, **_responses(401, 403, 404, 409)})
    def post(self, request, product_id: str):
        _attach_identity(request)
        product = composition.build_restore_product(_actor_id(request)).execute(uuid.UUID(product_id))
        return success_response(data=_product_detail_payload(product))


class AdminProductDuplicateView(APIView):
    throttle_classes = [CreateProductThrottle]

    def get_permissions(self):
        return [CatalogManagePermission()]

    @extend_schema(tags=["Products Admin"], summary="Duplicate a product as a new draft (no variants/media copied)", request=DuplicateProductSerializer, responses={201: AdminProductDetailSerializer, **_responses(401, 403, 404)})
    def post(self, request, product_id: str):
        _attach_identity(request)
        serializer = DuplicateProductSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = composition.build_duplicate_product(_actor_id(request)).execute(uuid.UUID(product_id), **serializer.validated_data)
        return success_response(data=_product_detail_payload(product), status_code=201)


class AdminProductCloneView(APIView):
    throttle_classes = [CreateProductThrottle]

    def get_permissions(self):
        return [CatalogManagePermission()]

    @extend_schema(tags=["Products Admin"], summary="Clone a product including variants and media", request=CloneProductSerializer, responses={201: AdminProductDetailSerializer, **_responses(401, 403, 404)})
    def post(self, request, product_id: str):
        _attach_identity(request)
        serializer = CloneProductSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = composition.build_clone_product(_actor_id(request)).execute(uuid.UUID(product_id), **serializer.validated_data)
        return success_response(data=_product_detail_payload(product), status_code=201)


# ============================================================
# Admin: variants
# ============================================================


class AdminVariantListCreateView(APIView):
    throttle_classes = [AdminOperationThrottle]

    def get_permissions(self):
        return [VariantPermission()]

    @extend_schema(tags=["Products Admin"], summary="Create a variant", request=CreateVariantSerializer, responses={201: AdminProductDetailSerializer, **_responses(401, 403, 404, 409, 422)})
    def post(self, request, product_id: str):
        _attach_identity(request)
        serializer = CreateVariantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = composition.build_create_variant(_actor_id(request)).execute(product_id=uuid.UUID(product_id), **serializer.validated_data)
        return success_response(data=_product_detail_payload(product), status_code=201)


class AdminVariantDetailView(APIView):
    throttle_classes = [AdminOperationThrottle]

    def get_permissions(self):
        return [VariantPermission()]

    @extend_schema(tags=["Products Admin"], summary="Update a variant", request=UpdateVariantSerializer, responses={200: AdminProductDetailSerializer, **_responses(401, 403, 404, 422)})
    def patch(self, request, product_id: str, variant_id: str):
        _attach_identity(request)
        serializer = UpdateVariantSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        product = composition.build_update_variant(_actor_id(request)).execute(product_id=uuid.UUID(product_id), variant_id=uuid.UUID(variant_id), **serializer.validated_data)
        return success_response(data=_product_detail_payload(product))

    @extend_schema(tags=["Products Admin"], summary="Delete a variant", responses={200: AdminProductDetailSerializer, **_responses(401, 403, 404, 422)})
    def delete(self, request, product_id: str, variant_id: str):
        _attach_identity(request)
        product = composition.build_delete_variant(_actor_id(request)).execute(product_id=uuid.UUID(product_id), variant_id=uuid.UUID(variant_id))
        return success_response(data=_product_detail_payload(product))


class AdminVariantSetDefaultView(APIView):
    throttle_classes = [AdminOperationThrottle]

    def get_permissions(self):
        return [VariantPermission()]

    @extend_schema(tags=["Products Admin"], summary="Set a variant as the product's default", responses={200: AdminProductDetailSerializer, **_responses(401, 403, 404)})
    def post(self, request, product_id: str, variant_id: str):
        _attach_identity(request)
        product = composition.build_set_default_variant(_actor_id(request)).execute(product_id=uuid.UUID(product_id), variant_id=uuid.UUID(variant_id))
        return success_response(data=_product_detail_payload(product))


# ============================================================
# Admin: media
# ============================================================


def _read_upload(request):
    uploaded_file = request.FILES.get("file")
    if uploaded_file is None:
        raise ValidationFailed("No file was uploaded under the 'file' field.", details={"fields": [{"field": "file", "code": "REQUIRED"}]})
    return uploaded_file.name, uploaded_file.read(), uploaded_file.content_type


class AdminImageUploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [UploadMediaThrottle]

    def get_permissions(self):
        return [CatalogMediaPermission()]

    @extend_schema(tags=["Products Admin"], summary="Upload a product image", request=UploadMediaSerializer, responses={201: AdminProductDetailSerializer, **_responses(401, 403, 404, 422)})
    def post(self, request, product_id: str):
        _attach_identity(request)
        filename, content, mime_type = _read_upload(request)
        media_role = request.data.get("media_role", "gallery")
        default_collector.counter("media_uploaded_total", media_type="image")
        product = composition.build_upload_image(_actor_id(request)).execute(product_id=uuid.UUID(product_id), filename=filename, content=content, mime_type=mime_type, media_role=media_role)
        return success_response(data=_product_detail_payload(product), status_code=201)


class AdminImageDeleteView(APIView):
    throttle_classes = [DeleteMediaThrottle]

    def get_permissions(self):
        return [CatalogMediaPermission()]

    @extend_schema(tags=["Products Admin"], summary="Delete a product image", responses={200: AdminProductDetailSerializer, **_responses(401, 403, 404)})
    def delete(self, request, product_id: str, image_id: str):
        _attach_identity(request)
        product = composition.build_delete_image(_actor_id(request)).execute(product_id=uuid.UUID(product_id), media_id=uuid.UUID(image_id))
        return success_response(data=_product_detail_payload(product))


class AdminVideoUploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [UploadMediaThrottle]

    def get_permissions(self):
        return [CatalogMediaPermission()]

    @extend_schema(tags=["Products Admin"], summary="Upload a product video", responses={201: AdminProductDetailSerializer, **_responses(401, 403, 404, 422)})
    def post(self, request, product_id: str):
        _attach_identity(request)
        filename, content, mime_type = _read_upload(request)
        duration_seconds = float(request.data.get("duration_seconds", 0) or 0)
        default_collector.counter("media_uploaded_total", media_type="video")
        product = composition.build_upload_video(_actor_id(request)).execute(product_id=uuid.UUID(product_id), filename=filename, content=content, mime_type=mime_type, duration_seconds=duration_seconds)
        return success_response(data=_product_detail_payload(product), status_code=201)


class AdminVideoDeleteView(APIView):
    throttle_classes = [DeleteMediaThrottle]

    def get_permissions(self):
        return [CatalogMediaPermission()]

    @extend_schema(tags=["Products Admin"], summary="Delete a product video", responses={200: AdminProductDetailSerializer, **_responses(401, 403, 404)})
    def delete(self, request, product_id: str, video_id: str):
        _attach_identity(request)
        product = composition.build_delete_video(_actor_id(request)).execute(product_id=uuid.UUID(product_id), media_id=uuid.UUID(video_id))
        return success_response(data=_product_detail_payload(product))


class AdminDocumentUploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [UploadMediaThrottle]

    def get_permissions(self):
        return [CatalogMediaPermission()]

    @extend_schema(tags=["Products Admin"], summary="Upload a product document (spec sheet, certificate, manual)", responses={201: AdminProductDetailSerializer, **_responses(401, 403, 404, 422)})
    def post(self, request, product_id: str):
        _attach_identity(request)
        filename, content, mime_type = _read_upload(request)
        default_collector.counter("media_uploaded_total", media_type="document")
        product = composition.build_upload_document(_actor_id(request)).execute(product_id=uuid.UUID(product_id), filename=filename, content=content, mime_type=mime_type)
        return success_response(data=_product_detail_payload(product), status_code=201)


class AdminDocumentDeleteView(APIView):
    throttle_classes = [DeleteMediaThrottle]

    def get_permissions(self):
        return [CatalogMediaPermission()]

    @extend_schema(tags=["Products Admin"], summary="Delete a product document", responses={200: AdminProductDetailSerializer, **_responses(401, 403, 404)})
    def delete(self, request, product_id: str, document_id: str):
        _attach_identity(request)
        product = composition.build_delete_document(_actor_id(request)).execute(product_id=uuid.UUID(product_id), media_id=uuid.UUID(document_id))
        return success_response(data=_product_detail_payload(product))


# ============================================================
# Admin: content
# ============================================================


class AdminNutritionView(APIView):
    throttle_classes = [AdminOperationThrottle]

    def get_permissions(self):
        return [CatalogManagePermission()]

    @extend_schema(tags=["Products Admin"], summary="Update nutrition facts", request=UpdateNutritionFactsSerializer, responses={200: AdminProductDetailSerializer, **_responses(401, 403, 404, 422)})
    def patch(self, request, product_id: str):
        _attach_identity(request)
        serializer = UpdateNutritionFactsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = composition.build_update_nutrition_facts(_actor_id(request)).execute(product_id=uuid.UUID(product_id), **serializer.validated_data)
        return success_response(data=_product_detail_payload(product))


class AdminIngredientsView(APIView):
    throttle_classes = [AdminOperationThrottle]

    def get_permissions(self):
        return [CatalogManagePermission()]

    @extend_schema(tags=["Products Admin"], summary="Update ingredients text", request=UpdateIngredientsSerializer, responses={200: AdminProductDetailSerializer, **_responses(401, 403, 404, 422)})
    def patch(self, request, product_id: str):
        _attach_identity(request)
        serializer = UpdateIngredientsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = composition.build_update_ingredients(_actor_id(request)).execute(product_id=uuid.UUID(product_id), **serializer.validated_data)
        return success_response(data=_product_detail_payload(product))


class AdminWarningsView(APIView):
    throttle_classes = [AdminOperationThrottle]

    def get_permissions(self):
        return [CatalogManagePermission()]

    @extend_schema(tags=["Products Admin"], summary="Update warnings text", request=UpdateWarningsSerializer, responses={200: AdminProductDetailSerializer, **_responses(401, 403, 404, 422)})
    def patch(self, request, product_id: str):
        _attach_identity(request)
        serializer = UpdateWarningsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = composition.build_update_warnings(_actor_id(request)).execute(product_id=uuid.UUID(product_id), **serializer.validated_data)
        return success_response(data=_product_detail_payload(product))


class AdminDirectionsView(APIView):
    throttle_classes = [AdminOperationThrottle]

    def get_permissions(self):
        return [CatalogManagePermission()]

    @extend_schema(tags=["Products Admin"], summary="Update directions text", request=UpdateDirectionsSerializer, responses={200: AdminProductDetailSerializer, **_responses(401, 403, 404, 422)})
    def patch(self, request, product_id: str):
        _attach_identity(request)
        serializer = UpdateDirectionsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = composition.build_update_directions(_actor_id(request)).execute(product_id=uuid.UUID(product_id), **serializer.validated_data)
        return success_response(data=_product_detail_payload(product))


class AdminSEOView(APIView):
    throttle_classes = [UpdateSEOThrottle]

    def get_permissions(self):
        return [CatalogSEOPermission()]

    @extend_schema(tags=["Products Admin"], summary="Update SEO metadata", request=UpdateSEOSerializer, responses={200: AdminProductDetailSerializer, **_responses(401, 403, 404, 422)})
    def patch(self, request, product_id: str):
        _attach_identity(request)
        serializer = UpdateSEOSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = composition.build_update_seo(_actor_id(request)).execute(product_id=uuid.UUID(product_id), **serializer.validated_data)
        return success_response(data=_product_detail_payload(product))


# ============================================================
# Admin: relations
# ============================================================


class AdminAssignBrandView(APIView):
    throttle_classes = [AdminOperationThrottle]

    def get_permissions(self):
        return [BrandPermission()]

    @extend_schema(tags=["Products Admin"], summary="Assign a brand", request=AssignBrandSerializer, responses={200: AdminProductDetailSerializer, **_responses(401, 403, 404, 422)})
    def patch(self, request, product_id: str):
        _attach_identity(request)
        serializer = AssignBrandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = composition.build_assign_brand(_actor_id(request)).execute(product_id=uuid.UUID(product_id), brand_id=serializer.validated_data.get("brand_id"))
        return success_response(data=_product_detail_payload(product))


class AdminAssignCategoryView(APIView):
    throttle_classes = [AdminOperationThrottle]

    def get_permissions(self):
        return [CategoryPermission()]

    @extend_schema(tags=["Products Admin"], summary="Assign a category", request=AssignCategorySerializer, responses={200: AdminProductDetailSerializer, **_responses(401, 403, 404, 422)})
    def patch(self, request, product_id: str):
        _attach_identity(request)
        serializer = AssignCategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = composition.build_assign_category(_actor_id(request)).execute(product_id=uuid.UUID(product_id), category_id=serializer.validated_data.get("category_id"))
        return success_response(data=_product_detail_payload(product))


class AdminAssignTagsView(APIView):
    throttle_classes = [AdminOperationThrottle]

    def get_permissions(self):
        return [CatalogManagePermission()]

    @extend_schema(tags=["Products Admin"], summary="Assign tags (replaces the full tag set)", request=AssignTagsSerializer, responses={200: AdminProductDetailSerializer, **_responses(401, 403, 404, 422)})
    def patch(self, request, product_id: str):
        _attach_identity(request)
        serializer = AssignTagsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = composition.build_assign_tags(_actor_id(request)).execute(product_id=uuid.UUID(product_id), tag_ids=frozenset(serializer.validated_data["tag_ids"]))
        return success_response(data=_product_detail_payload(product))


class AdminAssignFlavoursView(APIView):
    throttle_classes = [AdminOperationThrottle]

    def get_permissions(self):
        return [CatalogManagePermission()]

    @extend_schema(tags=["Products Admin"], summary="Assign flavours (replaces the full flavour set)", request=AssignFlavoursSerializer, responses={200: AdminProductDetailSerializer, **_responses(401, 403, 404, 422)})
    def patch(self, request, product_id: str):
        _attach_identity(request)
        serializer = AssignFlavoursSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = composition.build_assign_flavours(_actor_id(request)).execute(product_id=uuid.UUID(product_id), flavour_ids=frozenset(serializer.validated_data["flavour_ids"]))
        return success_response(data=_product_detail_payload(product))


class ProductStatisticsView(APIView):
    """Wires the existing, already-tested `StatisticsSelector` (counts_by_status, average_media_per_product) -- built but never exposed via HTTP, matching the same 'built but never wired' pattern found repeatedly across this project."""

    permission_classes = [CatalogManagePermission]

    @extend_schema(tags=["Products Admin"], summary="Product catalog statistics (counts by status, average media per product)")
    def get(self, request):
        _attach_identity(request)
        from apps.products.infrastructure.selectors import StatisticsSelector

        selector = StatisticsSelector()
        return success_response(data={
            "counts_by_status": selector.counts_by_status(),
            "average_media_per_product": selector.average_media_per_product(),
        })


class TopProductsView(APIView):
    """Dashboard's last remaining candidate -- wires the new StatisticsSelector.top_products()."""

    permission_classes = [CatalogManagePermission]

    @extend_schema(tags=["Products Admin"], summary="Top-selling products, ranked by quantity sold across completed orders")
    def get(self, request):
        _attach_identity(request)
        from apps.products.infrastructure.selectors import StatisticsSelector

        limit = int(request.query_params.get("limit", 10))
        return success_response(data=StatisticsSelector().top_products(limit=limit))


# --- shared payload shaping --------------------------------------------


def _product_detail_payload(product) -> dict:
    """Shapes a domain Product aggregate into the AdminProductDetailSerializer-compatible dict -- kept as one function so every admin write endpoint returns an identically-shaped response."""
    return {
        "id": str(product.id),
        "slug": product.slug.value,
        "name": product.name,
        "status": product.status.value,
        "description": product.description,
        "brand_id": str(product.brand_id) if product.brand_id else None,
        "category_id": str(product.category_id) if product.category_id else None,
        "tag_ids": [str(t) for t in product.tag_ids],
        "flavour_ids": [str(f) for f in product.flavour_ids],
        "supplement_facts_text_uz": product.supplement_facts_text_uz,
        "supplement_facts_text_ru": product.supplement_facts_text_ru,
        "supplement_facts_text_en": product.supplement_facts_text_en,
        "warnings_text_uz": product.warnings_text_uz,
        "warnings_text_ru": product.warnings_text_ru,
        "warnings_text_en": product.warnings_text_en,
        "directions_text_uz": product.directions_text_uz,
        "directions_text_ru": product.directions_text_ru,
        "directions_text_en": product.directions_text_en,
        "variants": [
            {
                "id": str(v.id), "sku": v.sku.value, "barcode": v.barcode.value if v.barcode else None, "status": v.status.value,
                "weight_value": v.weight_value, "weight_unit": v.weight_unit.value, "package_id": str(v.package_id) if v.package_id else None, "is_default": v.is_default,
            }
            for v in product.variants.values()
        ],
        "media": [{"id": str(m.id), "media_role": m.media_role.value, "sort_order": m.sort_order} for m in product.media.values()],
        "seo": {"meta_title": product.seo.meta_title, "meta_description": product.seo.meta_description},
        "created_at": product.created_at.isoformat() if product.created_at else None,
        "updated_at": None,
        "version": None,
    }
