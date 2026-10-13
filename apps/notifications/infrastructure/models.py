"""
Notifications ORM models.

Mirrors Phase 1's 2 aggregates (`Notification`, `NotificationPreference`)
plus the 1 owned entity (`NotificationDelivery`) exactly -- 3 base
tables + 1 Outbox table.

**A disclosed, deliberate absence, not an oversight**: neither
`NotificationModel` nor `NotificationPreferenceModel` exposes or maps
a Domain-level `version` field, because neither certified aggregate
has one (re-verified fresh from live source during this phase's own
Step 1 -- a real departure from every other module in this build).
Both still inherit `SoftDeleteModel`, which composes in
`OptimisticLockMixin`'s own `version` column purely as an
Infrastructure-internal database concurrency-control mechanism --
that column exists and is maintained automatically by the ORM base
class, but the repository never reads or writes it against Domain
state, since Domain never certified such a field.

`NotificationDeliveryModel` uses a plain `Model` (not `SoftDeleteModel`),
matching `ParticipantModel`'s precedent from Chat -- both are
genuinely owned, small-cardinality entities, never independently
soft-deleted.

`disabled_combinations` is a `JSONField`, matching the real,
established precedent for sparse/flexible persistence already used
elsewhere in this repository (e.g. `WalletModel.metadata`) -- not a
fully-normalized one-row-per-combination table, preserving Domain's
own sparse opt-out model exactly rather than inventing a denser
persistence shape.
"""
from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.notifications.domain.enums import DeliveryStatus, NotificationChannel, NotificationPriority, NotificationStatus, NotificationType
from common.models import BaseModel, SoftDeleteModel
from common.utils import enum_field_kwargs
from core.outbox import AbstractOutboxEvent


class NotificationModel(SoftDeleteModel):
    recipient_id = models.UUIDField(db_index=True)
    notification_type = models.CharField(**enum_field_kwargs(NotificationType))
    priority = models.CharField(default=NotificationPriority.NORMAL.value, **enum_field_kwargs(NotificationPriority))
    title = models.CharField(max_length=150)
    body = models.TextField()
    template_key = models.CharField(max_length=100, null=True, blank=True)
    status = models.CharField(default=NotificationStatus.UNSEEN.value, db_index=True, **enum_field_kwargs(NotificationStatus))
    seen_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    # Customer inbox presentation (Infrastructure-only, never mapped to the Domain aggregate -- the repository's
    # update_or_create leaves these columns untouched): a semantic kind (icon/colour), a deep link, the text in every
    # storefront language (the inbox renders the locale the site is open in), and an idempotency key so the same
    # business event can never notify twice.
    kind = models.CharField(_("Kind"), max_length=40, blank=True, default="", db_index=True)
    link = models.CharField(_("Link"), max_length=255, blank=True, default="")
    i18n = models.JSONField(default=dict, blank=True)
    dedupe_key = models.CharField(max_length=160, null=True, blank=True, unique=True)
    broadcast = models.ForeignKey("notifications.NotificationBroadcast", null=True, blank=True, on_delete=models.SET_NULL, related_name="notifications")

    class Meta:
        db_table = "notifications_notifications"
        verbose_name=_("Notification")
        verbose_name_plural = _("Notifications")
        indexes = [
            models.Index(fields=["recipient_id", "status"]),
            models.Index(fields=["recipient_id", "created_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Notification({self.id}, {self.notification_type})"


class BroadcastAudience(models.TextChoices):
    ALL = "all", _("All customers")
    ACTIVE = "active", _("Active customers")
    TELEGRAM = "telegram", _("Telegram linked customers")
    BUYERS = "buyers", _("Customers with purchases")
    TIER = "tier", _("Loyalty tier")
    SUBSCRIBERS = "subscribers", _("News subscribers (Telegram)")
    NEW = "new", _("New customers (last 30 days)")
    SEGMENT = "segment", _("Customer segment")
    PHONE = "phone", _("One customer (by phone)")


class BroadcastStatus(models.TextChoices):
    QUEUED = "queued", _("Queued")
    SENDING = "sending", _("Sending")
    SENT = "sent", _("Sent")
    FAILED = "failed", _("Failed")


class NotificationBroadcast(models.Model):
    """One announcement from the dashboard to many customers at once: in-app for everyone in the audience, and optionally Telegram for those who linked the bot."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    kind = models.CharField(_("Kind"), max_length=40, default="announcement")
    title = models.CharField(_("Title"), max_length=150)
    body = models.TextField(_("Message"))
    i18n = models.JSONField(default=dict, blank=True)
    link = models.CharField(_("Link"), max_length=255, blank=True, default="")
    audience = models.CharField(_("Audience"), max_length=16, choices=BroadcastAudience.choices, default=BroadcastAudience.ALL)
    target = models.CharField(max_length=64, blank=True, default="")  # tier slug (TIER) or phone number (PHONE)
    priority = models.CharField(max_length=16, default=NotificationPriority.NORMAL.value)
    send_in_app = models.BooleanField(_("In-app"), default=True)
    send_telegram = models.BooleanField(_("Telegram"), default=False)
    status = models.CharField(_("Status"), max_length=16, choices=BroadcastStatus.choices, default=BroadcastStatus.QUEUED)
    recipients = models.PositiveIntegerField(_("Recipients"), default=0)
    telegram_sent = models.PositiveIntegerField(default=0)
    telegram_failed = models.PositiveIntegerField(default=0)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_by = models.CharField(max_length=150, blank=True, default="")
    source = models.CharField(max_length=40, blank=True, default="dashboard")  # dashboard / coupon / campaign
    source_ref = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "notifications_broadcasts"
        ordering = ["-created_at"]
        verbose_name = _("Broadcast")
        verbose_name_plural = _("Broadcasts")

    def __str__(self) -> str:  # pragma: no cover
        return self.title


class NotificationDeliveryModel(models.Model):
    """Owned, non-root entity -- see this module's own docstring for why this (not Notification) gets the plain-Model treatment."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    notification = models.ForeignKey(NotificationModel, on_delete=models.CASCADE, related_name="deliveries")
    channel = models.CharField(**enum_field_kwargs(NotificationChannel))
    status = models.CharField(**enum_field_kwargs(DeliveryStatus))
    attempted_at = models.DateTimeField()
    delivered_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(null=True, blank=True)
    provider_reference = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "notifications_deliveries"
        indexes = [models.Index(fields=["notification"])]


class NotificationPreferenceModel(SoftDeleteModel):
    user_id = models.UUIDField(unique=True, db_index=True)
    disabled_combinations = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "notifications_preferences"
        verbose_name=_("Notification Preference")
        verbose_name_plural = _("Notification Preferences")

    def __str__(self) -> str:  # pragma: no cover
        return f"NotificationPreference({self.user_id})"


class NotificationOutboxEvent(AbstractOutboxEvent):
    class Meta:
        db_table = "notifications_outbox_events"
        ordering = ["created_at"]


class OrderConfirmedNotificationCursor(models.Model):
    """
    Phase 02G's independent progress marker through Ordering's own
    outbox, filtered to `OrderConfirmed` -- mirrors the exact,
    proven pattern already established by `OrderRewardCursor`
    (Phase 02C) and `ReturnRewardReversalCursor` (Phase 02D): a
    plain, singleton-row keyset cursor, never touching
    `published_at` (still `OutboxRelay`'s own single-consumer
    field). A new, Notifications-owned model rather than reusing
    Audit's private `SubscriberCursor`, per this phase's own
    explicit instruction not to touch Audit's certified
    infrastructure.
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    last_processed_created_at = models.DateTimeField(null=True, blank=True)
    last_processed_id = models.UUIDField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notifications_order_confirmed_cursor"


class OrderConfirmedNotificationRecord(BaseModel):
    """
    The database-level "exactly one order-confirmation notification
    per order" invariant -- the same "let a real PostgreSQL
    constraint decide the race" discipline already proven correct
    by every prior subscriber built in Phases 02C/02D/02F.
    `order_id` is the correct uniqueness boundary: `OrderConfirmed`
    fires at most once per order (confirmed by `Order.confirm()`'s
    own precondition, which requires `PENDING_PAYMENT` status and
    transitions away from it), so one notification per order is the
    correct invariant, not per-event-delivery.
    """

    order_id = models.UUIDField(unique=True, db_index=True)
    notification_id = models.UUIDField()

    class Meta:
        db_table = "notifications_order_confirmed_records"

    def __str__(self) -> str:  # pragma: no cover
        return f"OrderConfirmedNotificationRecord(order_id={self.order_id})"


class TelegramDispatchCursor(models.Model):
    """
    Independent progress marker through Notifications' own outbox,
    filtered to `NotificationCreated` -- mirrors the exact, proven
    pattern already established by `OrderConfirmedNotificationCursor`
    above. Exactly-once delivery per notification is enforced not by
    this cursor (a cursor alone cannot prevent a duplicate replay from
    re-sending) but by checking `notification.deliveries` for an
    existing TELEGRAM-channel attempt before ever calling the gateway
    -- see telegram_dispatch_subscriber.py's own module docstring.
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    last_processed_created_at = models.DateTimeField(null=True, blank=True)
    last_processed_id = models.UUIDField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notifications_telegram_dispatch_cursor"


class OrderChannelNotificationRecord(BaseModel):
    """
    The database-level "exactly one Orders-Channel notification per
    order" invariant -- the same "let a real PostgreSQL constraint
    decide the race" discipline already proven correct by
    OrderConfirmedNotificationRecord above. This is deliberately NOT
    a `Notification` aggregate: the Orders Channel is a single, fixed
    staff destination (a chat_id), not a per-recipient User, so there
    is no recipient_id to attach a Notification to.
    """

    order_id = models.UUIDField(unique=True, db_index=True)

    class Meta:
        db_table = "notifications_order_channel_records"

    def __str__(self) -> str:  # pragma: no cover
        return f"OrderChannelNotificationRecord(order_id={self.order_id})"


class NewsSubscription(models.Model):
    """
    A customer who subscribed to news & promotions in the Telegram bot. Broadcasts can target exactly these people,
    and their first purchase after subscribing earns a one-time coin gift (LoyaltySettings.subscribe_gift_coins).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField("identity.User", on_delete=models.CASCADE, related_name="news_subscription", verbose_name=_("Customer"))
    is_active = models.BooleanField(_("Subscribed"), default=True, db_index=True)
    source = models.CharField(_("Source"), max_length=32, blank=True, default="bot")  # bot menu / site deep link
    subscribed_at = models.DateTimeField(_("Subscribed at"), default=timezone.now)
    unsubscribed_at = models.DateTimeField(_("Unsubscribed at"), null=True, blank=True)
    gift_coins = models.PositiveIntegerField(_("Gift coins"), default=0)
    gift_granted_at = models.DateTimeField(_("Gift granted at"), null=True, blank=True)
    gift_purchase = models.CharField(_("Gift purchase"), max_length=40, blank=True, default="")

    class Meta:
        db_table = "notifications_news_subscriptions"
        verbose_name = _("News subscription")
        verbose_name_plural = _("News subscriptions")

    def __str__(self) -> str:
        return f"{self.user} ({'on' if self.is_active else 'off'})"
