"""
apps/platform/infrastructure/models.py

Database Blueprint §4.18 `platform.feature_flags`. This phase
implements Feature Flags only -- `config_values`/`config_value_history`/
`locales` remain unimplemented, disclosed in this phase's certification
report.
"""
from __future__ import annotations

import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import AllObjectsManager, BaseModel, SoftDeleteModel
from core.outbox import AbstractOutboxEvent


class FeatureFlagModel(SoftDeleteModel):
    key = models.CharField(max_length=128, unique=True, db_index=True)
    is_globally_enabled = models.BooleanField(default=False)
    rollout_percentage = models.PositiveSmallIntegerField(null=True, blank=True)
    rollout_scope = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "platform_feature_flags"
        verbose_name=_("Feature Flag")
        verbose_name_plural = _("Feature Flags")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(rollout_percentage__isnull=True) | (models.Q(rollout_percentage__gte=0) & models.Q(rollout_percentage__lte=100)),
                name="ck_feature_flags_rollout_percentage_range",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return self.key


class PlatformOutboxEvent(AbstractOutboxEvent):
    class Meta:
        db_table = "platform_outbox_events"
        ordering = ["created_at"]


class IdempotencyRecordStatus(models.TextChoices):
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class IdempotencyRecord(BaseModel):
    """
    Phase 02B's request-level idempotency foundation (Domain Architecture
    Specification's own cross-cutting-infrastructure framing, matching
    exactly how Feature Flags above already lives here rather than in a
    new `apps/idempotency`).

    Genuinely PostgreSQL-backed, per this phase's own explicit rule that
    Redis must never be the sole source of truth for a financial/
    inventory/order-affecting idempotency guarantee -- unlike the
    pre-existing `core/idempotency/decorators.py`, confirmed to have
    zero real callers and zero tests before this phase, which was
    Redis-only with no actor boundary and a genuine read-then-write
    race (no database-level locking or uniqueness enforcement).

    Uniqueness boundary is `(created_by, operation_scope, key)`, not
    `key` alone -- two different authenticated actors must be free to
    reuse the same client-generated key without colliding, and the
    same actor's key must not collide across genuinely different
    operations. `created_by` is `BaseModel`'s own existing actor
    column (via `ActorTrackedMixin`), reused deliberately rather than
    adding a duplicate field -- but populated explicitly by this
    module's own repository code, not relied upon to be set by any
    automatic request-boundary middleware, since this value is load-
    bearing for the uniqueness constraint itself and must never be
    ambiguous about whether it was actually set.
    """

    key = models.CharField(max_length=255, db_index=True)
    operation_scope = models.CharField(max_length=128, db_index=True)
    request_fingerprint = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=IdempotencyRecordStatus.choices, default=IdempotencyRecordStatus.PROCESSING, db_index=True)
    response_status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "platform_idempotency_records"
        constraints = [
            models.UniqueConstraint(fields=["created_by", "operation_scope", "key"], name="uq_idempotency_actor_scope_key"),
        ]
        indexes = [
            models.Index(fields=["status", "expires_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.operation_scope}:{self.key} ({self.status})"


class SiteSettings(models.Model):
    """
    Phase 16.2: confirmed genuine gap from Phase 16.1's own
    reconnaissance (no SiteSettings/branding model existed anywhere,
    confirmed via direct search). Directly requested by the project
    owner ("sayt logosi va nomini dinamik o'zgartirish mumkin bo'lsin").

    Singleton safety: a fixed primary key (id=1), the same "let a real
    PostgreSQL constraint decide" pattern already established by
    TelegramOrdersChannelCursor/TelegramDispatchCursor (Phase 15/15E).

    No secrets are stored here (confirmed absent from every field
    below) -- bot tokens, database passwords, and other credentials
    remain environment-variable-based, per this phase's own explicit
    instruction.
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)

    # --- General ---
    site_name = models.CharField(max_length=100, default="NutriZone")
    short_name = models.CharField(max_length=30, blank=True, default="NutriZone")
    logo = models.ImageField(upload_to="branding/", blank=True, null=True)
    favicon = models.ImageField(upload_to="branding/", blank=True, null=True)
    default_language = models.CharField(max_length=8, default="uz")

    # --- Branding ---
    primary_color = models.CharField(max_length=7, default="#1d4ed8", help_text="Hex color, e.g. #1d4ed8")
    secondary_color = models.CharField(max_length=7, blank=True, default="")
    accent_color = models.CharField(max_length=7, blank=True, default="")

    # --- Contact (only fields with a confirmed, real business need) ---
    support_phone = models.CharField(max_length=32, blank=True, default="")
    support_email = models.EmailField(blank=True, default="", verbose_name=_("Support email"))
    address = models.CharField(max_length=255, blank=True, default="", verbose_name=_("Address"), help_text=_("Shown on the public Contact page. Leave blank to hide."))
    working_hours = models.CharField(max_length=100, blank=True, default="", verbose_name=_("Working hours"), help_text=_("Free text, e.g. 'Mon-Sat 09:00-18:00'. Leave blank to hide."))
    telegram_username = models.CharField(max_length=64, blank=True, default="")
    telegram_channel_url = models.URLField(blank=True, default="")
    instagram_url = models.URLField(blank=True, default="")

    # --- Search engines (site ownership codes; the storefront renders them as <meta> verification tags) ---
    google_site_verification = models.CharField(max_length=128, blank=True, default="", verbose_name=_("Google Search Console code"))
    yandex_verification = models.CharField(max_length=128, blank=True, default="", verbose_name=_("Yandex Webmaster code"))
    bing_verification = models.CharField(max_length=128, blank=True, default="", verbose_name=_("Bing Webmaster code"))

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "platform_site_settings"
        verbose_name=_("Site Settings")
        verbose_name_plural=_("Site Settings")

    def save(self, *args, **kwargs):
        # Belt-and-suspenders alongside the fixed-PK constraint itself --
        # forces every save to target the single real row regardless of
        # how the instance was constructed.
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self) -> str:  # pragma: no cover
        return self.site_name


class Banner(models.Model):
    """
    Homepage hero slider banner -- a real, admin-managed content type
    that was confirmed missing entirely from the project before this
    phase (no Banner/HeroSlide/Promotion model existed anywhere).
    Deliberately a simple, standalone model (not a full DDD aggregate,
    matching this build's own established convention for low-business-
    rule, CRUD-heavy content like Wishlist) -- a banner has no lifecycle
    state machine, only visibility (is_active) and ordering.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=300, blank=True, default="")
    cta_text = models.CharField(max_length=60, blank=True, default="")
    # title/subtitle/cta_text above are the Uzbek (primary) texts; these are the optional other storefront
    # languages -- an empty one falls back to Uzbek (localized()).
    title_ru = models.CharField(max_length=200, blank=True, default="")
    title_en = models.CharField(max_length=200, blank=True, default="")
    subtitle_ru = models.CharField(max_length=300, blank=True, default="")
    subtitle_en = models.CharField(max_length=300, blank=True, default="")
    cta_text_ru = models.CharField(max_length=60, blank=True, default="")
    cta_text_en = models.CharField(max_length=60, blank=True, default="")
    cta_url = models.CharField(max_length=500, blank=True, default="")
    # Media Asset architecture removed per explicit product decision --
    # direct file storage fields (same pattern as Brand/Category).
    image_storage_path = models.CharField(max_length=500, blank=True, default="")
    image_thumbnail_paths = models.JSONField(default=dict, blank=True)
    # How long this banner stays active in the storefront hero slider before
    # auto-advancing. Bounds (3-300s) are a sanity guard, not a product rule.
    duration_seconds = models.PositiveIntegerField(default=45, validators=[MinValueValidator(3), MaxValueValidator(300)])
    sort_order = models.PositiveIntegerField(default=0, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = AllObjectsManager()

    def localized(self, field: str, locale: str) -> str:
        """`field` in `locale` ("uz" is the base field), falling back to Uzbek when that translation is empty."""
        return (getattr(self, f"{field}_{locale}", "") if locale in ("ru", "en") else "") or getattr(self, field)

    class Meta:
        db_table = "platform_banners"
        verbose_name = _("Banner")
        verbose_name_plural = _("Banners")
        ordering = ["sort_order", "-created_at"]

    def __str__(self) -> str:  # pragma: no cover
        return self.title


class ContactMessageStatus(models.TextChoices):
    NEW = "new", _("New")
    READ = "read", _("Read")
    REPLIED = "replied", _("Replied")


class ContactMessage(models.Model):
    """
    Real, product-required capability: stores public Contact page form
    submissions so an admin can view/manage them from the Dashboard --
    closing a confirmed gap where no such backend capability existed
    at all (the storefront's Contact page previously had no working
    form because there was nowhere to send it). Deliberately a simple,
    standalone model (same convention as Banner) -- a contact message
    has no lifecycle state machine, only a simple status an admin can
    update while triaging.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150)
    email = models.EmailField()
    subject = models.CharField(max_length=200, blank=True, default="")
    message = models.TextField()
    status = models.CharField(max_length=16, choices=ContactMessageStatus.choices, default=ContactMessageStatus.NEW, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "platform_contact_messages"
        verbose_name = _("Contact Message")
        verbose_name_plural = _("Contact Messages")
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.name} <{self.email}>"


# ======================================================================== control centre (Nazorat markazi)


class ControlSettings(models.Model):
    """Singleton (pk=1): the thresholds of the control centre's rules (control_center.py). Editable on the Nazorat page."""

    enabled = models.BooleanField(_("Nazorat yoqilgan"), default=True)
    telegram_enabled = models.BooleanField(_("Telegram'ga yuborish"), default=True)
    discount_percent = models.PositiveSmallIntegerField(_("Katta chegirma (%)"), default=15, validators=[MinValueValidator(1), MaxValueValidator(100)])
    discount_amount = models.DecimalField(_("Katta chegirma (so'm)"), max_digits=14, decimal_places=2, default=200000)
    quick_refund_minutes = models.PositiveSmallIntegerField(_("Tezkor qaytarish (daqiqa)"), default=30, validators=[MinValueValidator(1)])
    refunds_per_cashier = models.PositiveSmallIntegerField(_("Kassir qaytarishlari (kuniga)"), default=3, validators=[MinValueValidator(1)])
    voids_per_cashier = models.PositiveSmallIntegerField(_("Bekor qilingan cheklar (kuniga)"), default=3, validators=[MinValueValidator(1)])
    cash_difference = models.DecimalField(_("Kassa farqi (so'm)"), max_digits=14, decimal_places=2, default=50000)
    shift_max_hours = models.PositiveSmallIntegerField(_("Smena maksimal davomiyligi (soat)"), default=14, validators=[MinValueValidator(1), MaxValueValidator(48)])
    shift_open_grace_minutes = models.PositiveSmallIntegerField(_("Smena ochilmagan (daqiqa)"), default=45)
    payment_errors = models.PositiveSmallIntegerField(_("To'lov xatolari (30 daqiqada)"), default=3, validators=[MinValueValidator(1)])
    stock_alerts = models.BooleanField(_("Ombor ogohlantirishlari"), default=True)
    forecast_days = models.PositiveSmallIntegerField(_("Tugash prognozi (kun)"), default=7, validators=[MinValueValidator(1), MaxValueValidator(60)])
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "platform_control_settings"
        verbose_name = _("Nazorat sozlamalari")
        verbose_name_plural = _("Nazorat sozlamalari")

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "ControlSettings":
        obj, created = cls.objects.get_or_create(pk=1)
        if created:
            obj.refresh_from_db()
        return obj


class ControlAlertSeverity(models.TextChoices):
    CRITICAL = "critical", _("Jiddiy")
    WARNING = "warning", _("Diqqat")


class ControlAlert(models.Model):
    """
    One finding of the control centre: a suspicious till operation (big discount, quick refund, many refunds / voided
    receipts by one cashier, cash difference) or an operational incident (shift not opened / left open, late online
    orders, payment provider errors). `key` makes every finding exactly-once; the scan never edits the facts later.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=160, unique=True)
    kind = models.CharField(_("Turi"), max_length=32, db_index=True)
    severity = models.CharField(_("Darajasi"), max_length=12, choices=ControlAlertSeverity.choices, default=ControlAlertSeverity.WARNING, db_index=True)
    store = models.ForeignKey("stores.Store", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name=_("Filial"))
    title = models.CharField(_("Sarlavha"), max_length=200)
    facts = models.JSONField(default=list, blank=True)  # [[label, value], ...] -- shown as a table on the page and in Telegram
    link = models.CharField(max_length=300, blank=True, default="")  # admin path of the evidence (receipt, shift, order list)
    actor_name = models.CharField(_("Mas'ul"), max_length=150, blank=True, default="")
    happened_at = models.DateTimeField(_("Vaqti"), db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    notified_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(_("Yopilgan"), null=True, blank=True, db_index=True)
    resolved_by_name = models.CharField(max_length=150, blank=True, default="")
    resolution_note = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "platform_control_alerts"
        ordering = ["-happened_at"]
        verbose_name = _("Nazorat ogohlantirishi")
        verbose_name_plural = _("Nazorat ogohlantirishlari")
        indexes = [models.Index(fields=["resolved_at", "severity"])]

    def __str__(self) -> str:  # pragma: no cover
        return self.title


# ======================================================================== sales plan (Sotuv rejasi)


class SalesTarget(models.Model):
    """A month's revenue target for one branch (store) or, with no store, for the whole company."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey("stores.Store", null=True, blank=True, on_delete=models.CASCADE, related_name="+", verbose_name=_("Filial"))
    month = models.DateField(_("Oy"), db_index=True)  # always the 1st of the month
    revenue_target = models.DecimalField(_("Tushum rejasi"), max_digits=16, decimal_places=2, validators=[MinValueValidator(0)])
    note = models.CharField(_("Izoh"), max_length=255, blank=True, default="")
    updated_by = models.CharField(max_length=150, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "platform_sales_targets"
        ordering = ["-month"]
        verbose_name = _("Sotuv rejasi")
        verbose_name_plural = _("Sotuv rejalari")
        constraints = [
            models.UniqueConstraint(fields=["store", "month"], name="uq_sales_target_store_month"),
            models.UniqueConstraint(fields=["month"], condition=models.Q(store__isnull=True), name="uq_sales_target_company_month"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.month:%Y-%m} {self.store_id or 'company'}"
