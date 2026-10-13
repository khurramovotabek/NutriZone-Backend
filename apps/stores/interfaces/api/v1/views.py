from __future__ import annotations

from django.db.models import Avg, Count, Prefetch, Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.identity.interfaces.api.v1.permissions import IsAuthenticatedIdentityUser
from apps.stores.infrastructure.models import Store, StoreProductStock, StoreRating, StoreStatus
from apps.stores.interfaces.api.v1.serializers import (
    MyStoreProductCreateSerializer, MyStoreProductUpdateSerializer, MyStoreUpdateSerializer, StoreDetailSerializer,
    StoreListSerializer, StoreRatingInputSerializer,
)
from common.exceptions import ValidationFailed
from common.responses import success_response


def _media_url(storage_path: str, thumbnail_paths: dict, size: str = "medium") -> str | None:
    if not storage_path:
        return None
    return f"/media/{(thumbnail_paths or {}).get(size) or storage_path}"


def _rating_fields(store: Store) -> dict:
    """
    Real, closed gap: stores had no rating concept at all. Reads the
    two aggregate fields off `store` if the caller's queryset already
    annotated them (StoreListView does this in bulk to avoid an N+1
    across a whole page of stores); falls back to one direct
    aggregate query for a single-object fetch (StoreDetailView,
    MyStoreView, StoreRatingView) where annotating a throwaway
    queryset for one row would be no cheaper.
    """
    count = getattr(store, "rating_count", None)
    if count is None:
        agg = store.ratings.aggregate(avg=Avg("rating"), count=Count("id"))
        avg, count = agg["avg"], agg["count"] or 0
    else:
        avg = getattr(store, "rating_average", None)
    return {"rating_average": round(avg, 1) if avg is not None else None, "rating_count": count}


def _store_list_payload(store: Store, distance_meters: float | None = None) -> dict:
    return {
        "id": store.id, "name": store.name, "slug": store.slug, "status": store.status,
        "logo_url": _media_url(store.logo_storage_path, store.logo_thumbnail_paths, "small"),
        "cover_image_url": _media_url(store.cover_image_storage_path, store.cover_image_thumbnail_paths),
        "address": store.address, "city": store.city, "district": store.district,
        "latitude": store.latitude, "longitude": store.longitude,
        "is_open_now": store.is_open_now(),
        "distance_meters": distance_meters,
        **_rating_fields(store),
        "color": store.color or "",
        "phone": (store.phone_numbers or [None])[0],
        "today_hours": store.today_hours(),
        "product_count": getattr(store, "product_count", None) if getattr(store, "product_count", None) is not None else store.stock_entries.filter(quantity__gt=0).count(),
        "tagline": store.tagline, "amenities": store.amenities or [], "landmark": store.landmark, "pickup_enabled": store.pickup_enabled,
    }


class StoreListPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50


class StoreListView(APIView):
    """
    `GET /stores` -- real, public (AllowAny) storefront store directory.
    Never exposes INACTIVE stores (a store that hasn't launched yet or
    was retired). Filters:
      - city, district: exact, case-insensitive match
      - open_now=true: only stores whose real is_open_now() is True right now
      - lat & lng (+ optional radius_km, default 50): "near me" -- sorted by real haversine distance (GeoDistanceCalculator, the same one geo/ already uses for nearest-match ranking)
    """

    permission_classes = [AllowAny]
    pagination_class = StoreListPagination

    @extend_schema(
        tags=["Stores"], summary="List public stores",
        parameters=[
            OpenApiParameter("city", str, description="Filter by city"),
            OpenApiParameter("district", str, description="Filter by district"),
            OpenApiParameter("open_now", bool, description="Only stores open right now"),
            OpenApiParameter("lat", float, description="Latitude for 'near me' sorting"),
            OpenApiParameter("lng", float, description="Longitude for 'near me' sorting"),
            OpenApiParameter("radius_km", float, description="Max distance in km when lat/lng given (default 50)"),
        ],
        responses={200: OpenApiResponse(description="Paginated store list")},
    )
    def get(self, request):
        # rating_average/rating_count annotated in bulk here (rather
        # than each row doing its own store.ratings.aggregate() call
        # inside _rating_fields()) specifically to avoid an N+1 across
        # a whole page of stores -- distinct=True on Count guards
        # against a future join added to this same queryset silently
        # inflating the count via a fan-out, even though nothing here
        # causes that today.
        qs = Store.objects.exclude(status=StoreStatus.INACTIVE).filter(kind="store").annotate(
            rating_average=Avg("ratings__rating"), rating_count=Count("ratings", distinct=True),
            product_count=Count("stock_entries", filter=Q(stock_entries__quantity__gt=0), distinct=True),
        )

        city = request.GET.get("city")
        if city:
            qs = qs.filter(city__iexact=city)
        district = request.GET.get("district")
        if district:
            qs = qs.filter(district__iexact=district)

        stores = list(qs)

        lat = request.GET.get("lat")
        lng = request.GET.get("lng")
        distances: dict = {}
        if lat and lng:
            from apps.geo.domain.services import GeoDistanceCalculator
            from apps.geo.domain.value_objects import Coordinate

            try:
                origin = Coordinate.of(float(lat), float(lng))
                radius_km = float(request.GET.get("radius_km", 50))
            except (TypeError, ValueError):
                origin, radius_km = None, None

            if origin is not None:
                nearby = []
                for store in stores:
                    if store.latitude is None or store.longitude is None:
                        continue
                    distance_m = GeoDistanceCalculator.distance_meters(origin, Coordinate.of(store.latitude, store.longitude))
                    if distance_m <= radius_km * 1000:
                        distances[store.id] = distance_m
                        nearby.append(store)
                stores = sorted(nearby, key=lambda s: distances[s.id])

        if request.GET.get("open_now", "").lower() == "true":
            stores = [s for s in stores if s.is_open_now()]

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(stores, request, view=self)
        payload = [_store_list_payload(store, distances.get(store.id)) for store in page]
        serializer = StoreListSerializer(payload, many=True)
        response = paginator.get_paginated_response(serializer.data)
        # facets for the filter chips -- every public store, not just this page
        public = Store.objects.exclude(status=StoreStatus.INACTIVE).filter(kind="store")
        response.data["cities"] = sorted({c for c in public.values_list("city", flat=True) if c})
        response.data["open_now_count"] = sum(1 for st in public if st.is_open_now())
        return response


def _build_store_detail_payload(store: Store, request) -> dict:
    media = [
        {"id": m.id, "url": _media_url(m.storage_path, m.thumbnail_paths), "is_video": m.is_video, "sort_order": m.sort_order}
        for m in store.media.all().order_by("sort_order")
    ]

    from apps.products.infrastructure.selectors import _discount_fields, bulk_variant_prices

    stock_entries = list(
        StoreProductStock.objects.filter(store=store, quantity__gt=0)
        .select_related("product_variant", "product_variant__product")
        .prefetch_related("product_variant__product__media", "product_variant__product__translations")
    )
    prices = bulk_variant_prices([e.product_variant_id for e in stock_entries])
    locale = request.headers.get("X-Locale", "uz")
    products = []
    for entry in stock_entries:
        variant = entry.product_variant
        product = variant.product
        product_media = sorted(product.media.all(), key=lambda m: m.sort_order)
        first_media = next((m for m in product_media if m.media_role == "primary"), product_media[0] if product_media else None)
        translations = sorted(product.translations.all(), key=lambda tr: tr.locale_code)
        translation = next((tr for tr in translations if tr.locale_code == locale), translations[0] if translations else None)
        price = prices.get(variant.id)
        products.append({
            "id": entry.id, "product_variant_id": variant.id, "product_id": variant.product_id,
            # Requested locale first, then any translation the product has -- never a raw UUID when a real name exists.
            "name": (translation.name if translation else None) or variant.sku,
            # Only a published product has a page to link to.
            "product_slug": translation.slug if translation and product.status == "published" else None,
            "sku": variant.sku,
            "image_url": _media_url(first_media.storage_path, first_media.thumbnail_paths, "small") if first_media else None,
            "quantity": max(0, entry.quantity - entry.reserved_quantity),
            "weight_value": variant.weight_value, "weight_unit": variant.weight_unit,
            "price": price["amount"] if price else None, "currency": price["currency"] if price else None,
            **_discount_fields(price),
        })

    return {
        **_store_list_payload(store),
        # Real, closed gap: the detail page's own hero banner renders
        # full-bleed up to ~1536px wide (page.tsx's `w-full` hero
        # section), but `_store_list_payload`'s own cover_image_url
        # (reused above) is deliberately capped at the "medium"
        # thumbnail for small list/card use -- confirmed the real
        # cause of the hero looking soft on anything wider than that
        # thumbnail. The single-view hero can afford the real,
        # already-optimized original (no thumbnail_paths lookup),
        # exactly like the product gallery's own detail-view image.
        "cover_image_url": _media_url(store.cover_image_storage_path, {}),
        "description": store.description, "phone_numbers": store.phone_numbers,
        "email": store.email, "telegram_username": store.telegram_username, "instagram_username": store.instagram_username,
        "working_hours": store.working_hours, "special_hours": store.special_hours,
        "media": media, "products": products,
        # Real, existing relation (Store.owner -> identity.User) that had
        # no API surface on the public detail page at all -- the
        # storefront's own product requirement is that a shopper can see
        # who actually runs this store, exactly like every other real
        # contact field already exposed here (phone/email/Telegram).
        "owner_full_name": (store.owner.full_name or None) if store.owner_id else None,
        "upcoming_special_days": store.upcoming_special_days(),
        "pickup_note": store.pickup_note,
    }


class StoreDetailView(APIView):
    """`GET /stores/{slug}` -- real, public (AllowAny) store detail: contact, working hours, media gallery, and the real products this store carries (via StoreProductStock, quantity > 0 only)."""

    permission_classes = [AllowAny]

    @extend_schema(tags=["Stores"], summary="Get store detail by slug", responses={200: OpenApiResponse(description="Store detail"), 404: OpenApiResponse(description="Not found")})
    def get(self, request, slug: str):
        store = get_object_or_404(Store.objects.exclude(status=StoreStatus.INACTIVE).filter(kind="store").select_related("owner"), slug=slug)
        payload = _build_store_detail_payload(store, request)
        serializer = StoreDetailSerializer(payload)
        return success_response(data=serializer.data)


class MyStoreView(APIView):
    """
    `GET/PATCH /my-store` -- real, authenticated (identity.User, JWT)
    self-service store management. A customer with no store gets a
    real 404 (not a silently-empty payload) -- there is no "create
    your own store" endpoint; only Dashboard staff assign a store to a
    customer (see StoreAdmin.owner autocomplete). PATCH updates only
    the customer-editable fields -- ownership, slug, and status remain
    staff-only (never present in MyStoreUpdateSerializer).
    """

    permission_classes = [IsAuthenticatedIdentityUser]

    @extend_schema(tags=["Stores"], summary="Get my own store", responses={200: OpenApiResponse(description="My store detail"), 404: OpenApiResponse(description="No store owned by this customer")})
    def get(self, request):
        # The owner manages the whole store; a linked cashier gets the same store with my_role="cashier" (the storefront
        # then shows only the POS pages). Everything that edits the store stays owner-only (PATCH / uploads below).
        from django.http import Http404

        from apps.stores.infrastructure import pos_cashiers

        store, role = pos_cashiers.store_for_user(request.user.id)
        if store is None:
            raise Http404
        payload = _build_store_detail_payload(store, request)
        return success_response(data={**StoreDetailSerializer(payload).data, "my_role": role, "kassa_name": pos_cashiers.kassa_name(store)})

    @extend_schema(tags=["Stores"], summary="Update my own store", request=MyStoreUpdateSerializer, responses={200: OpenApiResponse(description="Updated store")})
    def patch(self, request):
        store = get_object_or_404(Store, owner_id=request.user.id)
        serializer = MyStoreUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(store, field, value)
        store.save()
        payload = _build_store_detail_payload(store, request)
        return success_response(data=StoreDetailSerializer(payload).data)



def _stock_is_staff_managed():
    """
    Business rule: a store owner never changes stock by hand -- stock arrives via
    NutriZone staff (Dashboard: Store → products / inter-branch transfers) and
    leaves only through POS sales. The owner's stock view is read-only.
    """
    from common.exceptions import PermissionDenied as DomainPermissionDenied

    err = DomainPermissionDenied("Stock is managed by NutriZone staff.")
    err.code = "STOCK_MANAGED_BY_STAFF"
    return err


class MyStoreProductsView(APIView):
    """`POST /my-store/products` -- closed: stock is managed by NutriZone staff (see `_stock_is_staff_managed`). The owner's read-only stock list is `GET /my-store/pos/stock`."""

    permission_classes = [IsAuthenticatedIdentityUser]

    @extend_schema(tags=["Stores"], summary="(Closed) Owners can't add stock", responses={403: OpenApiResponse(description="STOCK_MANAGED_BY_STAFF")})
    def post(self, request):
        raise _stock_is_staff_managed()


class MyStoreProductDetailView(APIView):
    """`PATCH/DELETE /my-store/products/{id}` -- closed for the same reason."""

    permission_classes = [IsAuthenticatedIdentityUser]

    @extend_schema(tags=["Stores"], summary="(Closed) Owners can't change stock", responses={403: OpenApiResponse(description="STOCK_MANAGED_BY_STAFF")})
    def patch(self, request, entry_id: int):
        raise _stock_is_staff_managed()

    @extend_schema(tags=["Stores"], summary="(Closed) Owners can't remove products", responses={403: OpenApiResponse(description="STOCK_MANAGED_BY_STAFF")})
    def delete(self, request, entry_id: int):
        raise _stock_is_staff_managed()


def _process_uploaded_image(uploaded):
    from apps.products.infrastructure.composition import build_media_pipeline
    from core.media import MediaType, MediaUploadRequest

    result = build_media_pipeline().process(MediaUploadRequest(filename=uploaded.name, content=uploaded.read(), mime_type=uploaded.content_type, media_type=MediaType.IMAGE))
    if result.is_failure:
        from common.exceptions import ValidationFailed

        raise ValidationFailed(result.errors[0].message)
    return result.value


class MyStoreLogoUploadView(APIView):
    """`POST /my-store/logo` -- real, authenticated media upload through the same, existing media pipeline the Dashboard's own StoreAdminForm._process_image uses. No second image-processing path."""

    permission_classes = [IsAuthenticatedIdentityUser]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(tags=["Stores"], summary="Upload my store's logo", responses={201: OpenApiResponse(description="Logo processed and set")})
    def post(self, request):
        store = get_object_or_404(Store, owner_id=request.user.id)
        uploaded = request.FILES.get("logo")
        if uploaded is None:
            raise ValidationFailed("No file was uploaded under the 'logo' field.", details={"fields": [{"field": "logo", "code": "REQUIRED"}]})

        processed = _process_uploaded_image(uploaded)
        store.logo_storage_path = processed.storage_path
        store.logo_thumbnail_paths = processed.thumbnail_paths
        store.save(update_fields=["logo_storage_path", "logo_thumbnail_paths"])
        return success_response(data={"logo_url": _media_url(store.logo_storage_path, store.logo_thumbnail_paths, "small")}, status_code=201)


class MyStoreCoverUploadView(APIView):
    """`POST /my-store/cover-image` -- same real media pipeline, for the store's single cover image."""

    permission_classes = [IsAuthenticatedIdentityUser]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(tags=["Stores"], summary="Upload my store's cover image", responses={201: OpenApiResponse(description="Cover image processed and set")})
    def post(self, request):
        store = get_object_or_404(Store, owner_id=request.user.id)
        uploaded = request.FILES.get("cover_image")
        if uploaded is None:
            raise ValidationFailed("No file was uploaded under the 'cover_image' field.", details={"fields": [{"field": "cover_image", "code": "REQUIRED"}]})

        processed = _process_uploaded_image(uploaded)
        store.cover_image_storage_path = processed.storage_path
        store.cover_image_thumbnail_paths = processed.thumbnail_paths
        store.save(update_fields=["cover_image_storage_path", "cover_image_thumbnail_paths"])
        return success_response(data={"cover_image_url": _media_url(store.cover_image_storage_path, store.cover_image_thumbnail_paths)}, status_code=201)


class MyStoreMediaView(APIView):
    """`POST /my-store/media` -- adds one image or video to the store's gallery (multiple images/video, per the real product requirement)."""

    permission_classes = [IsAuthenticatedIdentityUser]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(tags=["Stores"], summary="Add a media item (image or video) to my store's gallery", responses={201: OpenApiResponse(description="Media added")})
    def post(self, request):
        from apps.stores.infrastructure.models import StoreMedia

        store = get_object_or_404(Store, owner_id=request.user.id)
        uploaded = request.FILES.get("media")
        if uploaded is None:
            raise ValidationFailed("No file was uploaded under the 'media' field.", details={"fields": [{"field": "media", "code": "REQUIRED"}]})

        is_video = bool(uploaded.content_type and uploaded.content_type.startswith("video/"))
        from apps.products.infrastructure.composition import build_media_pipeline
        from core.media import MediaType, MediaUploadRequest

        media_type = MediaType.VIDEO if is_video else MediaType.IMAGE
        result = build_media_pipeline().process(MediaUploadRequest(filename=uploaded.name, content=uploaded.read(), mime_type=uploaded.content_type, media_type=media_type))
        if result.is_failure:
            raise ValidationFailed(result.errors[0].message)
        processed = result.value
        next_sort_order = store.media.count()
        item = StoreMedia.objects.create(
            store=store, storage_path=processed.storage_path, thumbnail_paths=getattr(processed, "thumbnail_paths", {}) or {},
            is_video=is_video, duration_seconds=getattr(processed, "duration_seconds", None), sort_order=next_sort_order,
        )
        return success_response(data={"id": item.id, "url": _media_url(item.storage_path, item.thumbnail_paths), "is_video": item.is_video}, status_code=201)


class MyStoreMediaDetailView(APIView):
    """`DELETE /my-store/media/{id}` -- removes one gallery item. Ownership always re-checked via the real Store row, never trusted from the URL alone."""

    permission_classes = [IsAuthenticatedIdentityUser]

    @extend_schema(tags=["Stores"], summary="Remove a media item from my store's gallery", responses={204: OpenApiResponse(description="Removed")})
    def delete(self, request, media_id: int):
        from apps.stores.infrastructure.models import StoreMedia

        store = get_object_or_404(Store, owner_id=request.user.id)
        item = get_object_or_404(StoreMedia, id=media_id, store=store)
        item.delete()
        from rest_framework.response import Response
        from rest_framework import status

        return Response(status=status.HTTP_204_NO_CONTENT)


class StoreRatingView(APIView):
    """
    `GET /stores/{slug}/rating` -- the current customer's own rating
    for this store (`rating: null` if they haven't rated it yet).
    `POST /stores/{slug}/rating` -- submit or update the current
    customer's own rating (1-5). Upsert by design (one row per
    (store, customer), see StoreRating's own docstring) -- rating a
    store a second time updates the existing rating rather than
    creating a duplicate that would double-count in the average.
    A store owner may not rate their own store.
    """

    permission_classes = [IsAuthenticatedIdentityUser]

    def _get_store(self, slug: str) -> Store:
        return get_object_or_404(Store.objects.exclude(status=StoreStatus.INACTIVE).filter(kind="store"), slug=slug)

    @extend_schema(tags=["Stores"], summary="Get my own rating for a store", responses={200: OpenApiResponse(description="My rating (null if none yet)")})
    def get(self, request, slug: str):
        store = self._get_store(slug)
        existing = StoreRating.objects.filter(store=store, customer_id=request.user.id).first()
        # the customer sees only their OWN review text; other customers' comments are never exposed
        return success_response(data={"rating": existing.rating if existing else None, "comment": existing.comment if existing else ""})

    @extend_schema(tags=["Stores"], summary="Rate a store (1-5 stars)", request=StoreRatingInputSerializer, responses={200: OpenApiResponse(description="My updated rating plus the store's new aggregate")})
    def post(self, request, slug: str):
        store = self._get_store(slug)
        if store.owner_id == request.user.id:
            raise ValidationFailed("You cannot rate your own store.", details={"fields": [{"field": "rating", "code": "CANNOT_RATE_OWN_STORE"}]})

        serializer = StoreRatingInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from django.utils import timezone

        data = serializer.validated_data
        row, _created = StoreRating.objects.get_or_create(store=store, customer_id=request.user.id, defaults={"rating": data["rating"]})
        row.rating = data["rating"]
        fields = ["rating", "updated_at"]
        if "comment" in data and data["comment"] != row.comment:
            row.comment = data["comment"]
            row.commented_at = timezone.now() if data["comment"] else None
            row.is_read = not data["comment"]  # a new / changed review lands as unread for management
            fields += ["comment", "commented_at", "is_read"]
        row.save(update_fields=fields)

        return success_response(data={"rating": row.rating, "comment": row.comment, **_rating_fields(store)})
