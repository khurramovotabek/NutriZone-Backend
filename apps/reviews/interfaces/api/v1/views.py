"""
Reviews API views.

Thin per Django Implementation Blueprint §3: each view deserializes,
calls a real repository/selector (resolved via infrastructure/
composition.py), and returns through the standard response envelope.
No view instantiates a repository directly, imports infrastructure.
models, or constructs a domain aggregate.

**Every mutation endpoint in this file returns an honest HTTP 501.**
This is the direct, disclosed consequence of this phase's own Step 1
re-verification: `composition.py` exposes zero Application Service
factories (only a repository accessor, 3 selector accessors, and 2
gateway accessors), because zero Application Services exist for
Reviews. `Review` has 9 public mutation methods (create, submit,
approve, reject, publish, hide, withdraw, edit_content, attach_media)
and every single one requires the same orchestration shape (load via
repository, call the aggregate method, persist via repository, stage
the resulting event) that only an Application Service can legitimately
own. Calling any of these directly from a view -- even though the
repository to do so is technically reachable via composition.py --
would be exactly the "business logic in Interfaces" violation this
build has treated as a real architecture mistake in every prior
module. Every 501 response states precisely which capability is
missing, matching this phase's explicit "no vague messages" rule.
"""
from __future__ import annotations

import uuid

from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.reviews.interfaces.api.v1.filters import (
    parse_admin_review_list_params, parse_customer_review_list_params, parse_product_review_list_params,
)
from apps.reviews.interfaces.api.v1.pagination import AdminReviewPagination, ReviewPagination
from apps.reviews.interfaces.api.v1.permissions import (
    AdminReviews, CreateReview, EditReview, ManageReviewMedia, ModerateReview, ViewOwnReviews, ViewStatistics,
)
from apps.reviews.interfaces.api.v1.serializers import (
    ApproveReviewSerializer, AttachReviewMediaSerializer, CreateReviewSerializer, EditReviewSerializer,
    HideReviewSerializer, PublishReviewSerializer, RejectReviewSerializer, SubmitReviewSerializer,
    WithdrawReviewSerializer,
)
from apps.reviews.infrastructure import composition
from common.exceptions import ResourceNotFound
from common.exceptions import PermissionDenied as DomainPermissionDenied
from common.responses import paginated_response, success_response
from core.openapi import STANDARD_ERROR_RESPONSES
from core.ratelimit import ScopedRateLimitThrottle


def _responses(*codes: int) -> dict:
    return {code: STANDARD_ERROR_RESPONSES[code] for code in codes}


def _attach_identity(request) -> None:
    request.identity = request.user


def _actor_id(request):
    return getattr(getattr(request, "user", None), "id", None)


class ReviewsThrottle(ScopedRateLimitThrottle):
    scope = "reviews.operation"
    limit = 3000
    window_seconds = 3600
    identifier_source = "user"


def _review_card_payload(row: dict) -> dict:
    return {"id": row["id"], "product_id": row["product_id"], "customer_id": row["customer_id"], "rating": row["rating"], "title": row.get("title"), "body": row.get("body"), "status": row["status"], "verified_purchase": row["verified_purchase"]}


def _review_to_payload(review) -> dict:
    return {
        "id": str(review.id), "product_id": str(review.product_id), "customer_id": str(review.customer_id),
        "rating": review.rating.value, "title": review.title.value if review.title else None,
        "body": review.body.value, "status": review.status.value, "verified_purchase": review.verified_purchase,
    }


def _review_detail_payload(review) -> dict:
    return {
        "id": str(review.id), "product_id": str(review.product_id), "customer_id": str(review.customer_id), "rating": review.rating.value,
        "title": review.title.value if review.title else None, "status": review.status.value, "verified_purchase": review.verified_purchase,
        "body": review.body.value,
        "media": [{"id": str(m.id), "media_type": m.media_type.value, "url": m.url, "uploaded_at": m.uploaded_at.isoformat()} for m in sorted(review.media.values(), key=lambda m: m.uploaded_at)],
    }


def _load_review_or_404(review_id: str):
    review = composition.build_review_repository().get_by_id(uuid.UUID(review_id))
    if review is None:
        raise ResourceNotFound("Review not found.")
    return review


_MISSING_APPLICATION_SERVICE = "This operation requires an Application Service that is not yet implemented. Zero Application Services currently exist for the Reviews module (see apps/reviews/application/services/); orchestrating this transition (load -> mutate -> persist -> stage event) cannot be done safely from the Interfaces layer without one."


# ============================================================
# Reviews -- read (real) and mutation (honest 501) endpoints
# ============================================================


class ProductReviewListView(APIView):
    """Public read -- any authenticated user may view a product's reviews; no ownership check applies, unlike the customer's-own-reviews endpoint below."""

    permission_classes = [ViewOwnReviews]

    @extend_schema(tags=["Reviews"], summary="List reviews for a product", description="Supports filter[status]. Backed by ReviewSelector.list_for_product -- no other filter parameter is exposed because no other parameter is supported by that selector.", responses={200: OpenApiResponse(description="Review collection"), **_responses(401, 403, 422)})
    def get(self, request, product_id: str):
        _attach_identity(request)
        params = parse_product_review_list_params(request.query_params)
        pagination = ReviewPagination.from_query_params(request.query_params)
        rows, total = composition.build_review_selector().list_for_product(product_id=uuid.UUID(product_id), status=params.status, page=pagination.page, page_size=pagination.page_size)
        total_pages = max((total + pagination.page_size - 1) // pagination.page_size, 1)
        return paginated_response(data=[_review_card_payload(r) for r in rows], pagination={"strategy": "page", "page": pagination.page, "page_size": pagination.page_size, "total_pages": total_pages, "total_count": total})


class PublicProductReviewListView(APIView):
    """
    The real, genuinely public review-read path for a product detail
    page -- unlike `ProductReviewListView` above (whose docstring
    claims public read access but is actually gated by `ViewOwnReviews`,
    which fails closed for an anonymous visitor), this endpoint is
    `AllowAny` and forces PUBLISHED-only (never a client-supplied status
    filter, so a visitor can never see a draft/pending/rejected
    review). Returns an author display name and attached media per
    review -- see `ReviewSelector.list_published_for_product`'s own
    docstring for exactly what's exposed and why.
    """

    permission_classes = [AllowAny]

    @extend_schema(tags=["Reviews"], summary="List a product's published reviews (public)", responses={200: OpenApiResponse(description="Published review collection"), **_responses(422)})
    def get(self, request, product_id: str):
        pagination = ReviewPagination.from_query_params(request.query_params)
        rows, total = composition.build_review_selector().list_published_for_product(product_id=uuid.UUID(product_id), page=pagination.page, page_size=pagination.page_size)
        total_pages = max((total + pagination.page_size - 1) // pagination.page_size, 1)
        return paginated_response(data=rows, pagination={"strategy": "page", "page": pagination.page, "page_size": pagination.page_size, "total_pages": total_pages, "total_count": total})


class FeaturedReviewsView(APIView):
    """`GET /reviews/featured` -- public: the best published reviews (4-5 stars, with a comment) for the home page."""

    permission_classes = [AllowAny]

    @extend_schema(tags=["Reviews"], summary="Best published reviews for the home page (public)")
    def get(self, request):
        from apps.reviews.infrastructure.selectors import featured_reviews
        from common.utils.localization import resolve_locale

        try:
            limit = min(max(int(request.query_params.get("limit", 6)), 1), 12)
        except ValueError:
            limit = 6
        return success_response(data=featured_reviews(limit, resolve_locale(request)))


class CustomerReviewListView(APIView):
    permission_classes = [ViewOwnReviews]

    @extend_schema(tags=["Reviews"], summary="List a customer's own reviews", responses={200: OpenApiResponse(description="Review collection"), **_responses(401, 403, 422)})
    def get(self, request, customer_id: str):
        _attach_identity(request)
        if uuid.UUID(customer_id) != getattr(request.user, "id", None):
            raise DomainPermissionDenied("You do not have permission to view this customer's reviews.")
        parse_customer_review_list_params(request.query_params)
        pagination = ReviewPagination.from_query_params(request.query_params)
        rows, total = composition.build_review_selector().list_for_customer(customer_id=uuid.UUID(customer_id), page=pagination.page, page_size=pagination.page_size)
        total_pages = max((total + pagination.page_size - 1) // pagination.page_size, 1)
        return paginated_response(data=[_review_card_payload(r) for r in rows], pagination={"strategy": "page", "page": pagination.page, "page_size": pagination.page_size, "total_pages": total_pages, "total_count": total})


class AdminReviewListView(APIView):
    permission_classes = [AdminReviews]

    @extend_schema(tags=["Reviews Admin"], summary="List all reviews (admin)", description="Supports filter[status]. Backed by DjangoReviewRepository.list_for_admin.", responses={200: OpenApiResponse(description="Review collection"), **_responses(401, 403, 422)})
    def get(self, request):
        _attach_identity(request)
        params = parse_admin_review_list_params(request.query_params)
        pagination = AdminReviewPagination.from_query_params(request.query_params)
        reviews, total = composition.build_review_repository().list_for_admin(status=params.status, page=pagination.page, page_size=pagination.page_size)
        total_pages = max((total + pagination.page_size - 1) // pagination.page_size, 1)
        return paginated_response(data=[_review_detail_payload(r) for r in reviews], pagination={"strategy": "page", "page": pagination.page, "page_size": pagination.page_size, "total_pages": total_pages, "total_count": total})


class ReviewDetailView(APIView):
    permission_classes = [ViewOwnReviews]

    @extend_schema(tags=["Reviews"], summary="Get a review by id", responses={200: OpenApiResponse(description="Review detail"), **_responses(401, 403, 404)})
    def get(self, request, review_id: str):
        _attach_identity(request)
        review = _load_review_or_404(review_id)
        if review.customer_id != getattr(request.user, "id", None):
            raise DomainPermissionDenied("You do not have permission to view this review.")
        return success_response(data=_review_detail_payload(review))


class CreateReviewView(APIView):
    """POST is an honest 501 -- see this module's own docstring. There is no GET/list at this collection path; product- and customer-scoped listing live at their own dedicated paths above, matching the actual selector capabilities rather than a generic collection-list assumption."""

    throttle_classes = [ReviewsThrottle]
    permission_classes = [CreateReview]

    @extend_schema(tags=["Reviews"], summary="Create a review", request=CreateReviewSerializer, responses={201: OpenApiResponse(description="Review created"), **_responses(401, 403, 422)})
    def post(self, request):
        _attach_identity(request)
        serializer = CreateReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        review = composition.build_create_review(actor_id=request.user.id).execute(
            customer_id=request.user.id, product_id=data["product_id"], rating=data["rating"],
            body=data["body"], title=data.get("title"), at=timezone.now(),
        )
        return success_response(data=_review_to_payload(review), status_code=201)


class SubmitReviewView(APIView):
    throttle_classes = [ReviewsThrottle]
    permission_classes = [EditReview]

    @extend_schema(tags=["Reviews"], summary="Submit a draft review for moderation", request=SubmitReviewSerializer, responses={200: OpenApiResponse(description="Review submitted"), **_responses(401, 403, 404)})
    def post(self, request, review_id: str):
        _attach_identity(request)
        _load_review_or_404(review_id)
        review = composition.build_submit_review(actor_id=request.user.id).execute(uuid.UUID(review_id), timezone.now())
        return success_response(data=_review_to_payload(review))


class EditReviewView(APIView):
    throttle_classes = [ReviewsThrottle]
    permission_classes = [EditReview]

    @extend_schema(tags=["Reviews"], summary="Edit a review's content", request=EditReviewSerializer, responses={200: OpenApiResponse(description="Review edited"), **_responses(401, 403, 404, 422)})
    def patch(self, request, review_id: str):
        _attach_identity(request)
        serializer = EditReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        existing = _load_review_or_404(review_id)
        data = serializer.validated_data
        new_body = data.get("body") if data.get("body") else existing.body.value
        review = composition.build_edit_review(actor_id=request.user.id).execute(uuid.UUID(review_id), body=new_body, at=timezone.now(), title=data.get("title"))
        return success_response(data=_review_to_payload(review))


class ApproveReviewView(APIView):
    throttle_classes = [ReviewsThrottle]
    permission_classes = [ModerateReview]

    @extend_schema(tags=["Reviews Admin"], summary="Approve a review", request=ApproveReviewSerializer, responses={200: OpenApiResponse(description="Review approved"), **_responses(401, 403, 404)})
    def post(self, request, review_id: str):
        _attach_identity(request)
        _load_review_or_404(review_id)
        review = composition.build_approve_review(actor_id=request.user.id).execute(uuid.UUID(review_id), timezone.now())
        return success_response(data=_review_to_payload(review))


class RejectReviewView(APIView):
    throttle_classes = [ReviewsThrottle]
    permission_classes = [ModerateReview]

    @extend_schema(tags=["Reviews Admin"], summary="Reject a review", request=RejectReviewSerializer, responses={200: OpenApiResponse(description="Review rejected"), **_responses(401, 403, 404, 422)})
    def post(self, request, review_id: str):
        _attach_identity(request)
        serializer = RejectReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _load_review_or_404(review_id)
        review = composition.build_reject_review(actor_id=request.user.id).execute(uuid.UUID(review_id), reason=serializer.validated_data["reason"], at=timezone.now())
        return success_response(data=_review_to_payload(review))


class PublishReviewView(APIView):
    throttle_classes = [ReviewsThrottle]
    permission_classes = [ModerateReview]

    @extend_schema(tags=["Reviews Admin"], summary="Publish an approved review", request=PublishReviewSerializer, responses={200: OpenApiResponse(description="Review published"), **_responses(401, 403, 404, 409)})
    def post(self, request, review_id: str):
        _attach_identity(request)
        _load_review_or_404(review_id)
        review = composition.build_publish_review(actor_id=request.user.id).execute(uuid.UUID(review_id), timezone.now())
        return success_response(data=_review_to_payload(review))


class HideReviewView(APIView):
    throttle_classes = [ReviewsThrottle]
    permission_classes = [ModerateReview]

    @extend_schema(tags=["Reviews Admin"], summary="Hide a published review", request=HideReviewSerializer, responses={200: OpenApiResponse(description="Review hidden"), **_responses(401, 403, 404, 422)})
    def post(self, request, review_id: str):
        _attach_identity(request)
        serializer = HideReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _load_review_or_404(review_id)
        review = composition.build_hide_review(actor_id=request.user.id).execute(uuid.UUID(review_id), reason=serializer.validated_data["reason"])
        return success_response(data=_review_to_payload(review))


class WithdrawReviewView(APIView):
    throttle_classes = [ReviewsThrottle]
    permission_classes = [EditReview]

    @extend_schema(tags=["Reviews"], summary="Withdraw a review", request=WithdrawReviewSerializer, responses={200: OpenApiResponse(description="Review withdrawn"), **_responses(401, 403, 404, 409)})
    def post(self, request, review_id: str):
        _attach_identity(request)
        _load_review_or_404(review_id)
        review = composition.build_withdraw_review(actor_id=request.user.id).execute(uuid.UUID(review_id))
        return success_response(data=_review_to_payload(review))


class AttachReviewMediaView(APIView):
    """Both GET (backed by `ReviewMediaSelector`) and POST (real file upload, via `AttachReviewMedia` -> core.media.MediaPipeline) are fully implemented."""

    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [ReviewsThrottle]

    def get_permissions(self):
        return [ManageReviewMedia()] if self.request.method == "POST" else [ViewOwnReviews()]

    @extend_schema(tags=["Reviews"], summary="List a review's media", responses={200: OpenApiResponse(description="Media collection"), **_responses(401, 403, 404)})
    def get(self, request, review_id: str):
        _attach_identity(request)
        _load_review_or_404(review_id)
        items = composition.build_review_media_selector().list_for_review(uuid.UUID(review_id))
        return success_response(data=items)

    @extend_schema(tags=["Reviews"], summary="Attach media to a review", request=AttachReviewMediaSerializer, responses={200: OpenApiResponse(description="Media attached"), **_responses(401, 403, 404, 422)})
    def post(self, request, review_id: str):
        _attach_identity(request)
        serializer = AttachReviewMediaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _load_review_or_404(review_id)
        data = serializer.validated_data
        uploaded = data["file_upload"]
        review = composition.build_attach_review_media(actor_id=request.user.id).execute(
            uuid.UUID(review_id), media_type=data["media_type"], filename=uploaded.name, content=uploaded.read(), mime_type=uploaded.content_type, at=timezone.now(),
        )
        return success_response(data=_review_to_payload(review))


class ReviewStatisticsView(APIView):
    permission_classes = [ViewStatistics]

    @extend_schema(tags=["Reviews Admin"], summary="Review statistics (counts by status)", responses={200: OpenApiResponse(description="Statistics"), **_responses(401, 403)})
    def get(self, request):
        _attach_identity(request)
        selector = composition.build_review_statistics_selector()
        return success_response(data={"counts_by_status": selector.counts_by_status()})
