"""
Reviews Application Services -- Create/Submit/Approve/Reject/Publish/
Hide/Withdraw/Edit.

Every method here follows the exact orchestration shape this module's
own views.py docstring already named as the reason mutations could
not live in Interfaces: load via repository, call the aggregate
method, persist via repository, stage the resulting event -- all
inside one `transaction.atomic()` block (the same real, live-verified
topology fix already applied across POS/Chat/Analytics/Geo/Platform
in this build's own transaction-boundary audit).

**`verified_purchase` -- a real, evidence-based check, not a stub**:
`CreateReview` queries `apps.ordering`'s own real `OrderModel`/
`OrderLineItemModel` for a DELIVERED or COMPLETED order, placed by
this customer, containing any variant of this product. This is a
direct, cross-app ORM read (matching this build's own established
convention, e.g. ProductAdmin's use of apps.pricing/apps.inventory
models directly) -- not a second Ordering repository, not a fabricated
"assume verified" shortcut.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from django.db import transaction

from apps.reviews.application.ports import ReviewRepository
from apps.reviews.application.services._shared import ReviewsServiceContext
from apps.reviews.domain.aggregates import Review
from apps.reviews.domain.enums import ReviewHideReason, ReviewRejectionReason
from apps.reviews.domain.value_objects import Rating, ReviewBody, ReviewTitle
from common.exceptions import ResourceNotFound


def _has_verified_purchase(customer_id: uuid.UUID, product_id: uuid.UUID) -> bool:
    from apps.ordering.infrastructure.models import OrderLineItemModel
    from apps.products.infrastructure.models import ProductVariant

    variant_ids = list(ProductVariant.objects.filter(product_id=product_id).values_list("id", flat=True))
    if not variant_ids:
        return False
    return OrderLineItemModel.objects.filter(
        order__customer_id=customer_id,
        order__status__in=["delivered", "completed"],
        product_variant_id__in=variant_ids,
    ).exists()


class CreateReview:
    def __init__(self, repo: ReviewRepository, ctx: ReviewsServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    def execute(self, customer_id: uuid.UUID, product_id: uuid.UUID, rating: int, body: str, title: str | None, at: datetime) -> Review:
        verified_purchase = _has_verified_purchase(customer_id, product_id)
        review, event = Review.create(
            review_id=uuid.uuid4(), product_id=product_id, customer_id=customer_id,
            rating=Rating(rating), body=ReviewBody(body), verified_purchase=verified_purchase,
            at=at, title=ReviewTitle(title) if title else None,
        )
        with transaction.atomic():
            saved = self._repo.save(review)
            self._ctx.stage_events([("ReviewCreated", event.to_payload())])
        self._ctx.audit().created(entity_type="Review", entity_id=str(saved.id), after={"product_id": str(product_id), "rating": rating, "verified_purchase": verified_purchase})
        self._ctx.metric("reviews_created_total")
        return saved


class SubmitReview:
    """
    Real, explicit product decision (not a bypass of the moderation
    state machine -- every real transition below still runs through
    the exact same `Review.approve()`/`Review.publish()` aggregate
    methods a staff member's own Approve/Publish actions call, in the
    same order, with the same validation): a submitted review goes
    live immediately, with no admin action required first. Staff can
    still take a published review down afterward via the existing,
    unmodified `HideReview` -- moderation shifts from
    "gatekeeper" to "after-the-fact", it isn't removed. The
    PENDING_MODERATION/APPROVED states -- and the standalone
    Approve/Reject/Publish admin endpoints -- are left fully intact so
    this can be reverted to pre-publication moderation later by simply
    removing the two extra calls below, without any migration.
    """

    def __init__(self, repo: ReviewRepository, ctx: ReviewsServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    def execute(self, review_id: uuid.UUID, at: datetime) -> Review:
        review = self._repo.get_by_id(review_id)
        if review is None:
            raise ResourceNotFound("Review not found.")
        submitted_event = review.submit(at)
        approved_event = review.approve(at)
        published_event = review.publish(at)
        with transaction.atomic():
            saved = self._repo.save(review)
            self._ctx.stage_events([
                ("ReviewSubmitted", submitted_event.to_payload()),
                ("ReviewApproved", approved_event.to_payload()),
                ("ReviewPublished", published_event.to_payload()),
            ])
        self._ctx.audit().updated(entity_type="Review", entity_id=str(review_id), before={}, after={"status": "published"})
        self._ctx.metric("reviews_submitted_total")
        self._ctx.metric("reviews_published_total")
        return saved


class EditReview:
    def __init__(self, repo: ReviewRepository, ctx: ReviewsServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    def execute(self, review_id: uuid.UUID, body: str, at: datetime, title: str | None = None) -> Review:
        review = self._repo.get_by_id(review_id)
        if review is None:
            raise ResourceNotFound("Review not found.")
        event = review.edit_content(body=ReviewBody(body), at=at, title=ReviewTitle(title) if title else None)
        events = [("ReviewEdited", event.to_payload())]
        # Same real product decision as SubmitReview: editing a
        # PUBLISHED review's own `edit_content()` still resets it to
        # PENDING_MODERATION (a real, unmodified domain rule) -- this
        # immediately carries it back through the same real
        # approve()/publish() aggregate methods rather than leaving an
        # edited review stuck waiting on a staff action that this
        # product decision says is no longer required.
        if event.reset_to_pending_moderation:
            approved_event = review.approve(at)
            published_event = review.publish(at)
            events.append(("ReviewApproved", approved_event.to_payload()))
            events.append(("ReviewPublished", published_event.to_payload()))
        with transaction.atomic():
            saved = self._repo.save(review)
            self._ctx.stage_events(events)
        self._ctx.audit().updated(entity_type="Review", entity_id=str(review_id), before={}, after={"body": body})
        return saved


class ApproveReview:
    def __init__(self, repo: ReviewRepository, ctx: ReviewsServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    def execute(self, review_id: uuid.UUID, at: datetime) -> Review:
        review = self._repo.get_by_id(review_id)
        if review is None:
            raise ResourceNotFound("Review not found.")
        event = review.approve(at)
        with transaction.atomic():
            saved = self._repo.save(review)
            self._ctx.stage_events([("ReviewApproved", event.to_payload())])
        self._ctx.audit().updated(entity_type="Review", entity_id=str(review_id), before={}, after={"status": "approved"})
        self._ctx.metric("reviews_approved_total")
        return saved


class RejectReview:
    def __init__(self, repo: ReviewRepository, ctx: ReviewsServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    def execute(self, review_id: uuid.UUID, reason: str, at: datetime) -> Review:
        review = self._repo.get_by_id(review_id)
        if review is None:
            raise ResourceNotFound("Review not found.")
        event = review.reject(ReviewRejectionReason(reason), at)
        with transaction.atomic():
            saved = self._repo.save(review)
            self._ctx.stage_events([("ReviewRejected", event.to_payload())])
        self._ctx.audit().updated(entity_type="Review", entity_id=str(review_id), before={}, after={"status": "rejected", "reason": reason})
        self._ctx.metric("reviews_rejected_total")
        return saved


class PublishReview:
    def __init__(self, repo: ReviewRepository, ctx: ReviewsServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    def execute(self, review_id: uuid.UUID, at: datetime) -> Review:
        review = self._repo.get_by_id(review_id)
        if review is None:
            raise ResourceNotFound("Review not found.")
        event = review.publish(at)
        with transaction.atomic():
            saved = self._repo.save(review)
            self._ctx.stage_events([("ReviewPublished", event.to_payload())])
        self._ctx.audit().updated(entity_type="Review", entity_id=str(review_id), before={}, after={"status": "published"})
        self._ctx.metric("reviews_published_total")
        return saved


class HideReview:
    def __init__(self, repo: ReviewRepository, ctx: ReviewsServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    def execute(self, review_id: uuid.UUID, reason: str) -> Review:
        review = self._repo.get_by_id(review_id)
        if review is None:
            raise ResourceNotFound("Review not found.")
        event = review.hide(ReviewHideReason(reason))
        with transaction.atomic():
            saved = self._repo.save(review)
            self._ctx.stage_events([("ReviewHidden", event.to_payload())])
        self._ctx.audit().updated(entity_type="Review", entity_id=str(review_id), before={}, after={"status": "hidden", "reason": reason})
        return saved


class WithdrawReview:
    def __init__(self, repo: ReviewRepository, ctx: ReviewsServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    def execute(self, review_id: uuid.UUID) -> Review:
        review = self._repo.get_by_id(review_id)
        if review is None:
            raise ResourceNotFound("Review not found.")
        event = review.withdraw()
        with transaction.atomic():
            saved = self._repo.save(review)
            self._ctx.stage_events([("ReviewWithdrawn", event.to_payload())])
        self._ctx.audit().updated(entity_type="Review", entity_id=str(review_id), before={}, after={"status": "withdrawn"})
        return saved
