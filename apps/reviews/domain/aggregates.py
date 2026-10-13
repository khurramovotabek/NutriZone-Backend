"""
Reviews aggregates.

One aggregate root: `Review`. Owns an append-only `media: dict[UUID,
ReviewMedia]` collection (attached only in DRAFT, per this module's
disclosed design). `product_id`/`customer_id` are plain `uuid.UUID`
fields -- never an import of `apps.products` or `apps.identity`
Domain objects (verified by direct grep after this file was written,
not just declared as an intention). `verified_purchase: bool` is
supplied externally at creation time; this aggregate never queries
Ordering or any other bounded context to determine it (see this
module's own `create()` docstring for the full rationale).

Every mutation happens through a public method; the Application layer
never reaches into a private (underscore-prefixed) method or field --
a lesson applied directly from a real bug found and fixed in Wallet
Phase 2 (`Wallet._idempotency_index` had to be removed because
Infrastructure could only reconstruct it by reaching into the
aggregate from outside). `Review` stores no field that isn't either a
plain public attribute or a plain dict keyed by entity id, safely
reconstructible by any repository the same way every other module's
owned-entity collections already are.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from apps.reviews.domain.entities import ReviewMedia
from apps.reviews.domain.enums import ReviewHideReason, ReviewMediaType, ReviewRejectionReason, ReviewStatus
from apps.reviews.domain.events import (
    ReviewApproved, ReviewCreated, ReviewEdited, ReviewHidden, ReviewMediaAttached, ReviewPublished, ReviewRejected,
    ReviewSubmitted, ReviewWithdrawn,
)
from apps.reviews.domain.exceptions import (
    InvalidReviewLifecycleTransition, MediaAttachmentNotAllowed, MediaLimitExceeded, ReviewAlreadyPublished,
    ReviewAlreadyWithdrawn, ReviewNotEditable,
)
from apps.reviews.domain.services import MAX_IMAGE_MEDIA_ITEMS, MAX_VIDEO_MEDIA_ITEMS, ReviewEditPolicy
from apps.reviews.domain.value_objects import Rating, ReviewBody, ReviewTitle, ReviewVersion


@dataclass(slots=True)
class Review:
    """Aggregate root -- the sole Reviews aggregate."""

    id: uuid.UUID
    product_id: uuid.UUID
    customer_id: uuid.UUID
    rating: Rating
    body: ReviewBody
    verified_purchase: bool
    title: ReviewTitle | None = None
    status: ReviewStatus = ReviewStatus.DRAFT
    version: ReviewVersion = field(default_factory=lambda: ReviewVersion(1))
    media: dict[uuid.UUID, ReviewMedia] = field(default_factory=dict)
    created_at: datetime | None = None
    submitted_at: datetime | None = None
    moderated_at: datetime | None = None
    published_at: datetime | None = None

    # --- Internal helpers ------------------------------------------------

    def _bump_version(self) -> None:
        self.version = self.version.next()

    # --- Creation ----------------------------------------------------------

    @staticmethod
    def create(review_id: uuid.UUID, product_id: uuid.UUID, customer_id: uuid.UUID, rating: Rating, body: ReviewBody, verified_purchase: bool, at: datetime, title: ReviewTitle | None = None) -> tuple["Review", ReviewCreated]:
        """
        `verified_purchase` is a plain externally-supplied flag, per
        this module's explicit "verified purchase" boundary: the
        Application layer will, in a later phase, ask Ordering's own
        certified query service for the real answer and pass it in
        here -- this aggregate never queries Ordering itself.
        """
        review = Review(id=review_id, product_id=product_id, customer_id=customer_id, rating=rating, body=body, verified_purchase=verified_purchase, title=title, created_at=at)
        event = ReviewCreated(review_id=review.id, product_id=product_id, customer_id=customer_id)
        return review, event

    # --- Lifecycle -----------------------------------------------------------

    def submit(self, at: datetime) -> ReviewSubmitted:
        if self.status != ReviewStatus.DRAFT:
            raise InvalidReviewLifecycleTransition(f"Cannot submit a review in status {self.status.value}; only DRAFT reviews can be submitted.")
        self.status = ReviewStatus.PENDING_MODERATION
        self.submitted_at = at
        self._bump_version()
        return ReviewSubmitted(review_id=self.id, product_id=self.product_id)

    def approve(self, at: datetime) -> ReviewApproved:
        if self.status != ReviewStatus.PENDING_MODERATION:
            raise InvalidReviewLifecycleTransition(f"Cannot approve a review in status {self.status.value}; only PENDING_MODERATION reviews can be approved.")
        self.status = ReviewStatus.APPROVED
        self.moderated_at = at
        self._bump_version()
        return ReviewApproved(review_id=self.id)

    def reject(self, reason: ReviewRejectionReason, at: datetime) -> ReviewRejected:
        if self.status != ReviewStatus.PENDING_MODERATION:
            raise InvalidReviewLifecycleTransition(f"Cannot reject a review in status {self.status.value}; only PENDING_MODERATION reviews can be rejected.")
        self.status = ReviewStatus.REJECTED
        self.moderated_at = at
        self._bump_version()
        return ReviewRejected(review_id=self.id, reason=reason.value)

    def publish(self, at: datetime) -> ReviewPublished:
        if self.status == ReviewStatus.PUBLISHED:
            raise ReviewAlreadyPublished("This review is already published.")
        if self.status != ReviewStatus.APPROVED:
            raise InvalidReviewLifecycleTransition(f"Cannot publish a review in status {self.status.value}; only APPROVED reviews can be published.")
        self.status = ReviewStatus.PUBLISHED
        self.published_at = at
        self._bump_version()
        return ReviewPublished(review_id=self.id, product_id=self.product_id, rating=self.rating.value)

    def hide(self, reason: ReviewHideReason) -> ReviewHidden:
        if self.status != ReviewStatus.PUBLISHED:
            raise InvalidReviewLifecycleTransition(f"Cannot hide a review in status {self.status.value}; only PUBLISHED reviews can be hidden.")
        self.status = ReviewStatus.HIDDEN
        self._bump_version()
        return ReviewHidden(review_id=self.id, reason=reason.value)

    def withdraw(self) -> ReviewWithdrawn:
        """Customer-initiated. A soft, terminal status change -- never a hard delete, matching this build's append-only/soft-deletion conventions (see events.py's own module docstring for why this is `ReviewWithdrawn`, not `ReviewDeleted`)."""
        if self.status == ReviewStatus.WITHDRAWN:
            raise ReviewAlreadyWithdrawn("This review has already been withdrawn.")
        self.status = ReviewStatus.WITHDRAWN
        self._bump_version()
        return ReviewWithdrawn(review_id=self.id)

    # --- Editing -----------------------------------------------------------

    def edit_content(self, body: ReviewBody, at: datetime, title: ReviewTitle | None = None) -> ReviewEdited:
        """
        Editing a DRAFT review is a free edit. Editing a PUBLISHED
        review is allowed but resets status to PENDING_MODERATION --
        the content changed, so it must be re-moderated before it is
        visible again, per this module's disclosed design. Every
        other status raises ReviewNotEditable.
        """
        if not ReviewEditPolicy.can_edit(self.status):
            raise ReviewNotEditable(f"A review in status {self.status.value} cannot be edited.")

        requires_remoderation = ReviewEditPolicy.requires_remoderation(self.status)
        self.body = body
        self.title = title
        if requires_remoderation:
            self.status = ReviewStatus.PENDING_MODERATION
            self.submitted_at = at
        self._bump_version()
        return ReviewEdited(review_id=self.id, reset_to_pending_moderation=requires_remoderation)

    # --- Media -----------------------------------------------------------

    def attach_media(self, media_type: ReviewMediaType, url: str, at: datetime) -> ReviewMediaAttached:
        """Media is finalized at submission time -- only allowed while the review is still DRAFT, per this module's disclosed design (see value_objects.py's module docstring for the full boundary rationale). Images and videos have separate limits (4/3) per explicit product decision, rather than one shared cap."""
        if self.status != ReviewStatus.DRAFT:
            raise MediaAttachmentNotAllowed(f"Cannot attach media to a review in status {self.status.value}; media may only be attached while still DRAFT.")
        same_type_count = sum(1 for m in self.media.values() if m.media_type == media_type)
        limit = MAX_IMAGE_MEDIA_ITEMS if media_type == ReviewMediaType.IMAGE else MAX_VIDEO_MEDIA_ITEMS
        if same_type_count >= limit:
            raise MediaLimitExceeded(f"A review may not have more than {limit} {media_type.value} item(s) attached.")
        item = ReviewMedia(id=uuid.uuid4(), media_type=media_type, url=url, uploaded_at=at)
        self.media[item.id] = item
        self._bump_version()
        return ReviewMediaAttached(review_id=self.id, media_id=item.id, media_type=media_type.value)
