"""
Reviews domain exceptions.
"""
from __future__ import annotations

from common.exceptions import BusinessRuleViolation, ConflictError, ValidationFailed


class InvalidReviewLifecycleTransition(ConflictError):
    """The general fallback for any wrong-state transition attempt (e.g. approving a DRAFT review) that doesn't warrant its own more specific exception below."""

    code = "INVALID_REVIEW_LIFECYCLE_TRANSITION"


class ReviewAlreadyPublished(ConflictError):
    """The single most idempotency-sensitive 'already done' case -- publish is externally consequential (visible to shoppers), so a caller re-triggering it deserves a precise, distinct error rather than the generic transition fallback."""

    code = "REVIEW_ALREADY_PUBLISHED"


class ReviewAlreadyWithdrawn(ConflictError):
    code = "REVIEW_ALREADY_WITHDRAWN"


class ReviewNotEditable(BusinessRuleViolation):
    code = "REVIEW_NOT_EDITABLE"


class MediaAttachmentNotAllowed(BusinessRuleViolation):
    """Raised when `attach_media()` is called outside DRAFT -- media is finalized at submission time, per this module's disclosed design (see aggregates.py)."""

    code = "MEDIA_ATTACHMENT_NOT_ALLOWED"


class MediaLimitExceeded(BusinessRuleViolation):
    code = "MEDIA_LIMIT_EXCEEDED"


class InvalidRating(ValidationFailed):
    code = "INVALID_RATING"


class ReviewContentTooLong(ValidationFailed):
    code = "REVIEW_CONTENT_TOO_LONG"
