"""
Reviews API serializers.

Every field name and shape below is traced directly to `apps.reviews.
domain.aggregates.Review`'s actual fields (re-verified fresh this
phase, not assumed from Phase 1's report). `verified_purchase` is
never a client-writable input field on the create serializer -- it is
a server-controlled value (per the certified Domain boundary: it
would ultimately come from an Application-layer cross-context lookup,
not from a client-submitted flag a customer could set to true
themselves).

**Command serializers exist and validate structurally even though
every one of their backing endpoints returns an honest HTTP 501** --
matching the exact precedent established by Wallet's
`TransferSerializer` and Loyalty's original `EnrollMembershipSerializer`:
the serializer validates shape before the view explains why the
operation can't complete yet, per this phase's own explicit
instruction ("Serializer validation must occur BEFORE a 501
response").
"""
from __future__ import annotations

from rest_framework import serializers

from apps.reviews.domain.enums import ReviewHideReason, ReviewMediaType, ReviewRejectionReason, ReviewStatus
from apps.reviews.domain.value_objects import MAX_BODY_LENGTH, MAX_RATING, MAX_TITLE_LENGTH, MIN_RATING

# --- Read shapes -----------------------------------------------------


class ReviewMediaSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    media_type = serializers.ChoiceField(choices=ReviewMediaType.values(), read_only=True)
    url = serializers.URLField(read_only=True)
    uploaded_at = serializers.DateTimeField(read_only=True)


class ReviewSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    product_id = serializers.CharField(read_only=True)
    customer_id = serializers.CharField(read_only=True)
    rating = serializers.IntegerField(read_only=True)
    title = serializers.CharField(read_only=True, allow_null=True)
    status = serializers.ChoiceField(choices=ReviewStatus.values(), read_only=True)
    verified_purchase = serializers.BooleanField(read_only=True)


class ReviewDetailSerializer(ReviewSerializer):
    """Adds the full body and media list -- used by the single-review detail endpoint, not the list endpoints (which stay lightweight, matching every prior module's card-vs-detail split)."""

    body = serializers.CharField(read_only=True)
    media = ReviewMediaSerializer(many=True, read_only=True)


class ReviewStatisticsSerializer(serializers.Serializer):
    counts_by_status = serializers.DictField(read_only=True)


# --- Command / request DTOs ------------------------------------------


class CreateReviewSerializer(serializers.Serializer):
    """`verified_purchase` is intentionally absent -- see this module's own docstring."""

    product_id = serializers.UUIDField()
    rating = serializers.IntegerField(min_value=MIN_RATING, max_value=MAX_RATING)
    title = serializers.CharField(max_length=MAX_TITLE_LENGTH, required=False, allow_null=True, allow_blank=False)
    body = serializers.CharField(max_length=MAX_BODY_LENGTH, allow_blank=False)


class SubmitReviewSerializer(serializers.Serializer):
    """No fields -- a pure state-transition command; kept as its own empty serializer so its OpenAPI schema is self-documenting, matching the identical pattern already used for Wallet's/Loyalty's own zero-field command serializers."""


class EditReviewSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=MIN_RATING, max_value=MAX_RATING, required=False)
    title = serializers.CharField(max_length=MAX_TITLE_LENGTH, required=False, allow_null=True, allow_blank=False)
    body = serializers.CharField(max_length=MAX_BODY_LENGTH, required=False, allow_blank=False)


class ApproveReviewSerializer(serializers.Serializer):
    """No fields -- matches `SubmitReviewSerializer`'s rationale."""


class RejectReviewSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=ReviewRejectionReason.values())


class PublishReviewSerializer(serializers.Serializer):
    """No fields -- matches `SubmitReviewSerializer`'s rationale."""


class HideReviewSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=ReviewHideReason.values())


class WithdrawReviewSerializer(serializers.Serializer):
    """No fields -- matches `SubmitReviewSerializer`'s rationale."""


class AttachReviewMediaSerializer(serializers.Serializer):
    media_type = serializers.ChoiceField(choices=ReviewMediaType.values())
    file_upload = serializers.FileField()
