from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import BaseModel
from core.outbox import AbstractOutboxEvent


class PaymentStatusChoices(models.TextChoices):
    CREATED = "created", _("Created")
    PENDING = "pending", _("Pending")
    SUCCEEDED = "succeeded", _("Paid")
    FAILED = "failed", _("Failed")
    CANCELLED = "cancelled", _("Cancelled")
    REFUNDED = "refunded", _("Refunded")


class PaymentProvider(models.TextChoices):
    """Every way a customer can pay. Uzcard / Humo are card brands routed through one of the acquirers."""

    CASH = "cash", _("Naqd pul")
    PAYME = "payme", "Payme"
    CLICK = "click", "Click"
    UZUM = "uzum", "Uzum Bank"
    UZCARD = "uzcard", "Uzcard"
    HUMO = "humo", "Humo"


class PaymentModel(BaseModel):
    """
    One payment attempt for one order. `provider_reference` is the provider's own transaction id
    (Payme `id`, Click `click_trans_id`, Uzum `transId`), unique so a transaction can never belong
    to two payments. Amounts are so'm; provider-specific units (tiyin) are converted at the edge.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_id = models.UUIDField(db_index=True)
    customer_id = models.UUIDField(db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3)
    provider = models.CharField(max_length=32)
    status = models.CharField(max_length=16, choices=PaymentStatusChoices.choices, default=PaymentStatusChoices.CREATED)
    provider_reference = models.CharField(max_length=128, null=True, blank=True, unique=True)
    failure_reason = models.CharField(max_length=255, null=True, blank=True)

    # --- online acquiring (Payme / Click / Uzum), all nullable so the original API keeps working
    order_number = models.CharField(_("Order"), max_length=30, blank=True, default="", db_index=True)
    method = models.CharField(_("Method"), max_length=16, blank=True, default="", help_text=_("What the customer picked (uzcard/humo route through an acquirer)."))
    is_test = models.BooleanField(_("Test mode"), default=False)
    provider_state = models.IntegerField(_("Provider state"), null=True, blank=True, help_text=_("Payme state 1/2/-1/-2, Click/Uzum mapped the same way."))
    provider_created_at = models.BigIntegerField(null=True, blank=True, help_text=_("Payme create_time (ms)."))
    provider_performed_at = models.BigIntegerField(null=True, blank=True, help_text=_("Payme perform_time (ms)."))
    provider_cancelled_at = models.BigIntegerField(null=True, blank=True, help_text=_("Payme cancel_time (ms)."))
    cancel_reason = models.IntegerField(null=True, blank=True)
    prepare_id = models.BigIntegerField(null=True, blank=True, unique=True, help_text=_("Click merchant_prepare_id."))
    paid_at = models.DateTimeField(_("Paid at"), null=True, blank=True)
    cancelled_at = models.DateTimeField(_("Cancelled at"), null=True, blank=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "payment_payments"
        verbose_name = _("Tranzaksiya")
        verbose_name_plural = _("Tranzaksiyalar")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["order_id"]), models.Index(fields=["customer_id"]), models.Index(fields=["provider", "status"])]

    def __str__(self) -> str:
        return f"{self.order_number or self.order_id} · {self.provider} · {self.status}"


class PaymentProviderConfig(models.Model):
    """
    Dashboard-managed settings of one payment method. Secrets live encrypted in `secrets_encrypted`
    (see crypto.py) and are never rendered back -- the dashboard only shows a masked hint.
    """

    provider = models.CharField(_("Provider"), max_length=16, choices=PaymentProvider.choices, unique=True)
    is_enabled = models.BooleanField(_("Enabled"), default=False, help_text=_("Shown to customers at checkout only when enabled AND fully configured."))
    is_test_mode = models.BooleanField(_("Test mode"), default=True)
    sort_order = models.PositiveSmallIntegerField(_("Order"), default=0)
    settings_public = models.JSONField(_("Settings"), default=dict, blank=True, help_text=_("Non-secret settings (merchant / service ids, account field, route)."))
    secrets_encrypted = models.TextField(blank=True, default="")
    min_amount = models.DecimalField(_("Minimum amount"), max_digits=14, decimal_places=2, default=1000)
    max_amount = models.DecimalField(_("Maximum amount"), max_digits=14, decimal_places=2, null=True, blank=True)
    last_callback_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=255, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        db_table = "payment_provider_configs"
        verbose_name = _("To'lov tizimi")
        verbose_name_plural = _("To'lov tizimlari")
        ordering = ["sort_order", "provider"]

    def __str__(self) -> str:
        return self.get_provider_display()


class PaymentCallbackLog(models.Model):
    """Every request a provider sent us (and our answer) -- the audit trail behind each transaction. Secrets are redacted before saving."""

    id = models.BigAutoField(primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    provider = models.CharField(max_length=16, db_index=True)
    method = models.CharField(max_length=48, blank=True, default="")
    payment = models.ForeignKey(PaymentModel, null=True, blank=True, on_delete=models.SET_NULL, related_name="callbacks")
    order_number = models.CharField(max_length=30, blank=True, default="", db_index=True)
    request = models.JSONField(default=dict, blank=True)
    response = models.JSONField(default=dict, blank=True)
    http_status = models.PositiveSmallIntegerField(default=200)
    error_code = models.IntegerField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "payment_callback_logs"
        verbose_name = _("Callback")
        verbose_name_plural = _("Callback jurnali")
        ordering = ["-created_at"]


class PaymentOutboxEvent(AbstractOutboxEvent):
    class Meta:
        db_table = "payment_outbox_events"
        ordering = ["created_at"]


class PaymentSettings(models.Model):
    """Dashboard-managed automation for online payments (singleton, pk=1)."""

    reminder_enabled = models.BooleanField(_("To'lov eslatmasi"), default=True)
    reminder_after_minutes = models.PositiveIntegerField(_("Eslatma (daqiqadan keyin)"), default=30)
    auto_cancel_enabled = models.BooleanField(_("Avtomatik bekor qilish"), default=True)
    auto_cancel_after_hours = models.PositiveIntegerField(_("Bekor qilish (soatdan keyin)"), default=24)
    reconcile_enabled = models.BooleanField(_("Kunlik solishtirish"), default=True)
    last_reconciled_at = models.DateTimeField(null=True, blank=True)
    last_reconcile_summary = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payment_settings"
        verbose_name = _("To'lov sozlamalari")
        verbose_name_plural = _("To'lov sozlamalari")

    @classmethod
    def load(cls) -> "PaymentSettings":
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


class ReconciliationSeverity(models.TextChoices):
    CRITICAL = "critical", _("Muhim")
    WARNING = "warning", _("Ogohlantirish")
    INFO = "info", _("Ma'lumot")


class ReconciliationStatus(models.TextChoices):
    OPEN = "open", _("Ochiq")
    RESOLVED = "resolved", _("Hal qilindi")
    IGNORED = "ignored", _("E'tiborsiz")


class PaymentReconciliationIssue(models.Model):
    """
    One discrepancy found by the daily reconciliation (our payments vs orders vs the provider). `dedupe_key`
    keeps one row per problem; a run that no longer sees the problem closes it automatically.
    """

    id = models.BigAutoField(primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    kind = models.CharField(_("Turi"), max_length=40, db_index=True)
    severity = models.CharField(_("Darajasi"), max_length=10, choices=ReconciliationSeverity.choices, default=ReconciliationSeverity.WARNING)
    status = models.CharField(_("Holat"), max_length=10, choices=ReconciliationStatus.choices, default=ReconciliationStatus.OPEN, db_index=True)
    provider = models.CharField(max_length=16, blank=True, default="")
    payment = models.ForeignKey(PaymentModel, null=True, blank=True, on_delete=models.SET_NULL, related_name="reconciliation_issues")
    order_number = models.CharField(max_length=30, blank=True, default="", db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)
    dedupe_key = models.CharField(max_length=160, unique=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    resolution_note = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "payment_reconciliation_issues"
        verbose_name = _("Solishtirish")
        verbose_name_plural = _("Solishtirish")
        ordering = ["status", "-created_at"]
