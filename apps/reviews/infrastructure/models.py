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

from django.core.validators import MaxValueValidator, MinValueValidator
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
    # The store's public answer, shown under the review on the site. Store-side only: the customer's review aggregate
    # (repositories.ReviewRepository.save) never writes these, so editing a review keeps the answer and vice versa.
    store_reply = models.TextField("Do'kon javobi", blank=True, default="")
    store_reply_at = models.DateTimeField(null=True, blank=True)
    store_reply_by = models.CharField(max_length=150, blank=True, default="")

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
        # breadcrumbs / history / delete pages: the customer's own headline, never an id
        title = (self.title or self.body or "").strip().splitlines()[0][:60] if (self.title or self.body or "").strip() else "Sharh"
        return f"{title} · {self.rating}★"


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


class ReviewRequestSettings(models.Model):
    """Singleton (pk=1): the "how was it?" message a few days after a purchase (ordering/review_requests.py). Editable in Dashboard → Sharhlar."""

    enabled = models.BooleanField(_("Sharh so'rovi yoqilgan"), default=True)
    ask_after_days = models.PositiveSmallIntegerField(_("Necha kundan keyin so'ralsin"), default=5, validators=[MinValueValidator(1), MaxValueValidator(60)])
    ask_until_days = models.PositiveSmallIntegerField(_("Necha kungacha so'ralsin"), default=14, validators=[MinValueValidator(2), MaxValueValidator(90)])
    # Coins for a review written AFTER the customer received the product (rewards.py) -- one reward per product.
    reward_enabled = models.BooleanField(_("Sharh uchun coin berilsin"), default=True)
    reward_coins = models.PositiveIntegerField(_("Coin miqdori"), default=1000, validators=[MaxValueValidator(100000)])
    reward_min_rating = models.PositiveSmallIntegerField(_("Eng kam yulduz"), default=4, validators=[MinValueValidator(1), MaxValueValidator(5)])
    reward_min_chars = models.PositiveSmallIntegerField(_("Matn kamida (belgi)"), default=30, validators=[MaxValueValidator(500)])
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "reviews_request_settings"
        verbose_name = _("Sharh so'rovi sozlamalari")
        verbose_name_plural = _("Sharh so'rovi sozlamalari")

    def __str__(self) -> str:
        return "Sharh so'rovi sozlamalari"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> ReviewRequestSettings:
        obj, created = cls.objects.get_or_create(pk=1)
        if created:
            obj.refresh_from_db()
        return obj


class ReviewRewardModel(models.Model):
    """One coin reward per (customer, product): written by rewards.award() in the same transaction as the wallet credit."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    review_id = models.UUIDField(unique=True)
    customer_id = models.UUIDField(db_index=True)
    product_id = models.UUIDField()
    coins = models.PositiveIntegerField()
    rating = models.PositiveSmallIntegerField()
    received_ref = models.CharField(max_length=60, blank=True, default="")  # "order:<id>" / "sale:<id>" -- the purchase that qualified
    transaction_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "reviews_review_rewards"
        verbose_name = _("Sharh mukofoti")
        verbose_name_plural = _("Sharh mukofotlari")
        constraints = [models.UniqueConstraint(fields=["customer_id", "product_id"], name="uq_review_reward_customer_product")]

    def __str__(self) -> str:
        return f"+{self.coins} coin · {self.rating}★"


class ProductQuestionModel(models.Model):
    """
    "Savol-javob" on the product page: a signed-in customer asks, the store answers in Dashboard → Sharhlar →
    Savollar. Only answered, not hidden questions are public; the asker is told once when the answer is written.
    """

    STATUS_CHOICES = (("pending", _("Javob kutilmoqda")), ("answered", _("Javob berilgan")), ("hidden", _("Yashirilgan")))

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product_id = models.UUIDField(db_index=True)
    customer_id = models.UUIDField(db_index=True)
    author_name = models.CharField(_("Muallif"), max_length=80, blank=True, default="")
    question = models.TextField(_("Savol"), max_length=600)
    answer = models.TextField(_("Javob"), blank=True, default="")
    answered_at = models.DateTimeField(null=True, blank=True)
    answered_by = models.CharField(max_length=150, blank=True, default="")
    status = models.CharField(_("Holat"), max_length=16, choices=STATUS_CHOICES, default="pending", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "reviews_product_questions"
        verbose_name = _("Mahsulot savoli")
        verbose_name_plural = _("Mahsulot savollari")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["product_id", "status"])]

    def __str__(self) -> str:  # pragma: no cover
        return (self.question or "Savol").strip().splitlines()[0][:60] if (self.question or "").strip() else "Savol"


class ReviewOutboxEvent(AbstractOutboxEvent):
    class Meta:
        db_table = "reviews_outbox_events"
        ordering = ["created_at"]
