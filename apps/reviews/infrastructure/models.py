"""
Reviews ORM models.

Mirrors Phase 1's 1 aggregate (`Review`) plus its 1 owned entity
(`ReviewMedia`) exactly -- 2 base tables + 1 Outbox table.

`ReviewModel` uses `SoftDeleteModel`, matching the established
convention for aggregate-root tables across every prior module
(`WalletModel`, `LoyaltyMembershipModel`). `ReviewMediaModel` is
append-only-at-the-model-layer in the sense that it is only ever
inserted, never updated, matching `TierChangeEntryModel`'s/
`WalletLedgerEntryModel`'s convention for owned, non-root rows --
though per the certified Domain contract, media can currently only be
*attached* (never individually removed) while a Review is DRAFT, so
this table is genuinely never updated or deleted at the application
level.

`product_id`/`customer_id` are plain `UUIDField` columns -- never a
`ForeignKey` to `apps.products`/`apps.identity`, per the certified
Phase 1 boundary (no cross-schema FK, matching the modular-monolith
rule already applied consistently in every prior module).
"""
from __future__ import annotations

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.reviews.domain.enums import ReviewMediaType, ReviewStatus
from common.models import SoftDeleteModel
from common.utils import enum_field_kwargs
from core.outbox import AbstractOutboxEvent


class ReviewModel(SoftDeleteModel):
    product_id = models.UUIDField(db_index=True)
    customer_id = models.UUIDField(db_index=True)
    rating = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=150, null=True, blank=True)
    body = models.TextField()
    verified_purchase = models.BooleanField(default=False)
    status = models.CharField(default=ReviewStatus.DRAFT.value, db_index=True, **enum_field_kwargs(ReviewStatus))
    version = models.PositiveIntegerField(default=1)
    submitted_at = models.DateTimeField(null=True, blank=True)
    moderated_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "reviews_reviews"
        verbose_name=_("Review")
        verbose_name_plural = _("Reviews")
        indexes = [
            models.Index(fields=["product_id", "status"]),
            models.Index(fields=["customer_id", "status"]),
            models.Index(fields=["status", "submitted_at"]),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(rating__gte=1) & models.Q(rating__lte=5), name="ck_reviews_rating_1_to_5"),
            models.CheckConstraint(condition=models.Q(version__gte=1), name="ck_reviews_version_at_least_one"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        """Uses this row's own id, never `product_id` -- the Dashboard admin no longer shows the cross-module product UUID anywhere (see apps/reviews/infrastructure/admin.py's own module docstring), including here, since Django renders this string into the changelist's per-row accessibility label."""
        return f"Review({self.id}, {self.rating}★)"


class ReviewMediaModel(models.Model):
    """Owned, non-root row -- see this module's own docstring for why this is never updated or deleted at the application level."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    review = models.ForeignKey(ReviewModel, on_delete=models.CASCADE, related_name="media_items")
    media_type = models.CharField(**enum_field_kwargs(ReviewMediaType))
    url = models.CharField(max_length=500)  # holds a real internal storage_path from core.media.MediaPipeline (field name kept as-is, see AttachReviewMedia's own docstring)
    uploaded_at = models.DateTimeField()

    class Meta:
        db_table = "reviews_review_media"
        verbose_name = _("Review media")
        verbose_name_plural = _("Review media")
        indexes = [models.Index(fields=["review"])]


class ReviewOutboxEvent(AbstractOutboxEvent):
    class Meta:
        db_table = "reviews_outbox_events"
        ordering = ["created_at"]
