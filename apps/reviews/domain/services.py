"""
Reviews domain services -- pure business rules with no I/O, per MIC
§4, matching every prior module's domain/services.py pattern.

**A deliberate scope decision**: no `RatingPolicy` is defined. Rating
bounds validation is already fully owned by the `Rating` value
object's own `__post_init__` (value_objects.py); a separate policy
class would only move that one check elsewhere, which this phase's
own rules explicitly forbid ("Do NOT create a service merely to move
one aggregate method elsewhere" -- the same reasoning applies to
value object validation).
"""
from __future__ import annotations

from datetime import timedelta

from apps.reviews.domain.enums import ReviewStatus

DEFAULT_MODERATION_SLA = timedelta(hours=48)
MAX_IMAGE_MEDIA_ITEMS = 4
MAX_VIDEO_MEDIA_ITEMS = 3


class ReviewEligibilityPolicy:
    """Pure decision: given what the Application layer already knows about this customer/product pair, is submitting a review currently allowed? Kept independently testable rather than inlined into the aggregate, since eligibility is plausibly a multi-factor decision (today: verified purchase only; a future phase could add review-count limits or account-standing checks without touching the aggregate)."""

    @staticmethod
    def can_submit(verified_purchase: bool) -> bool:
        return verified_purchase is True


class ReviewEditPolicy:
    """Pure decision: given the review's current status, is editing currently allowed, and does editing require resetting moderation? Used both by the aggregate's own `edit_content()` and potentially by a future Application-layer permission pre-check, so it is kept as an independently testable unit rather than inlined."""

    _EDITABLE_STATUSES = (ReviewStatus.DRAFT, ReviewStatus.PUBLISHED)

    @staticmethod
    def can_edit(status: ReviewStatus) -> bool:
        return status in ReviewEditPolicy._EDITABLE_STATUSES

    @staticmethod
    def requires_remoderation(status: ReviewStatus) -> bool:
        return status == ReviewStatus.PUBLISHED


class ReviewModerationSLACalculator:
    """Governs how long a review may sit in PENDING_MODERATION before it's considered overdue for a moderator to act on -- same duration-based-policy shape as `apps.fulfillment.domain.services.PackingSLAPolicy`/`apps.wallet.domain.services.HoldExpirationCalculator`."""

    @staticmethod
    def is_overdue(submitted_at, at, sla: timedelta = DEFAULT_MODERATION_SLA) -> bool:
        return at >= submitted_at + sla
