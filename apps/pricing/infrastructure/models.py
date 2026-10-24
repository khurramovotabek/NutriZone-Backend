"""
Pricing ORM models.

Infrastructure adapts to Domain, never the reverse: every field here
exists because a domain aggregate/entity field needs somewhere to
persist, not because it seemed convenient.

Cross-module references (PriceListEntry.product_variant_id ->
products.ProductVariant, CampaignTarget.target_id,
CouponRedemption.redeemed_by) are plain UUIDField columns, never a
ForeignKey across schemas -- the same modular-monolith rule already
applied consistently in every prior module.
"""
from __future__ import annotations

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.pricing.domain.enums import (
    CampaignStatus,
    CampaignType,
    CouponStatus,
    CouponType,
    DiscountValueType,
    PriceChangeReason,
    PriceListStatus,
    PriceSnapshotStatus,
    PriceType,
    PricingRuleStatus,
    PricingRuleType,
    StackingMode,
)
from common.models import AllObjectsManager, BaseModel, SoftDeleteModel
from common.utils import enum_field_kwargs
from core.outbox import AbstractOutboxEvent


class PriceListModel(SoftDeleteModel):
    code = models.CharField(max_length=42, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    currency = models.CharField(max_length=3, default="UZS")
    status = models.CharField(default=PriceListStatus.DRAFT.value, db_index=True, **enum_field_kwargs(PriceListStatus))
    region = models.CharField(max_length=16, null=True, blank=True, db_index=True)

    class Meta:
        db_table = "pricing_price_lists"
        verbose_name=_("Price List")
        verbose_name_plural = _("Price Lists")
        indexes = [models.Index(fields=["status", "region"])]

    def __str__(self) -> str:  # pragma: no cover
        return self.code


class PriceListEntryModel(BaseModel):
    price_list = models.ForeignKey(PriceListModel, on_delete=models.CASCADE, related_name="entries")
    product_variant_id = models.UUIDField(db_index=True)
    base_price_amount = models.DecimalField(max_digits=14, decimal_places=2)
    cost_price_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    sale_price_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    compare_at_price_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = "pricing_price_list_entries"
        verbose_name=_("Price List Entry")
        verbose_name_plural = _("Price List Entries")
        constraints = [
            models.UniqueConstraint(fields=["price_list", "product_variant_id"], name="uq_price_list_entries_list_variant"),
            models.CheckConstraint(condition=models.Q(sale_price_amount__isnull=True) | models.Q(sale_price_amount__lte=models.F("base_price_amount")), name="ck_price_list_entries_sale_le_base"),
            models.CheckConstraint(condition=models.Q(compare_at_price_amount__isnull=True) | models.Q(compare_at_price_amount__gte=models.F("base_price_amount")), name="ck_price_list_entries_compare_at_ge_base"),
            models.CheckConstraint(condition=models.Q(base_price_amount__gte=0), name="ck_price_list_entries_base_non_negative"),
        ]
        indexes = [models.Index(fields=["price_list", "product_variant_id"])]


class PriceHistoryEntryModel(models.Model):
    """Append-only -- no update/delete path is exposed by its repository, matching Database Blueprint §3's append-only discipline (same pattern as `apps.inventory.infrastructure.models.InventoryLedgerModel`)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    price_list = models.ForeignKey(PriceListModel, on_delete=models.CASCADE, related_name="history")
    product_variant_id = models.UUIDField(db_index=True)
    price_type = models.CharField(**enum_field_kwargs(PriceType))
    old_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    new_amount = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.CharField(**enum_field_kwargs(PriceChangeReason))
    changed_at = models.DateTimeField(db_index=True)

    objects = AllObjectsManager()

    class Meta:
        db_table = "pricing_price_history_entries"
        verbose_name=_("Price History Entry")
        verbose_name_plural = _("Price History Entries")
        indexes = [models.Index(fields=["price_list", "product_variant_id", "changed_at"])]


class PricingRuleModel(SoftDeleteModel):
    rule_type = models.CharField(db_index=True, **enum_field_kwargs(PricingRuleType))
    status = models.CharField(default=PricingRuleStatus.DRAFT.value, db_index=True, **enum_field_kwargs(PricingRuleStatus))
    discount_value_type = models.CharField(**enum_field_kwargs(DiscountValueType))
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    discount_fixed_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="UZS")
    validity_starts_at = models.DateTimeField(null=True, blank=True)
    validity_ends_at = models.DateTimeField(null=True, blank=True)
    region = models.CharField(max_length=16, null=True, blank=True)
    membership_tier_code = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    priority = models.PositiveIntegerField(default=100)

    class Meta:
        db_table = "pricing_rules"
        verbose_name=_("Pricing Rule")
        verbose_name_plural = _("Pricing Rules")
        indexes = [models.Index(fields=["status", "rule_type"]), models.Index(fields=["validity_starts_at", "validity_ends_at"])]
        constraints = [
            models.CheckConstraint(condition=models.Q(validity_ends_at__isnull=True) | models.Q(validity_ends_at__gt=models.F("validity_starts_at")), name="ck_pricing_rules_ends_after_starts"),
        ]


class QuantityTierModel(models.Model):
    """Non-root, owned by PricingRule -- backs `PricingRule.quantity_tiers`."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    pricing_rule = models.ForeignKey(PricingRuleModel, on_delete=models.CASCADE, related_name="quantity_tiers")
    minimum_quantity = models.PositiveIntegerField()
    discount_value_type = models.CharField(**enum_field_kwargs(DiscountValueType))
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    discount_fixed_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="UZS")

    objects = AllObjectsManager()

    class Meta:
        db_table = "pricing_quantity_tiers"
        constraints = [models.UniqueConstraint(fields=["pricing_rule", "minimum_quantity"], name="uq_quantity_tiers_rule_min_qty")]
        indexes = [models.Index(fields=["pricing_rule", "minimum_quantity"])]


class CampaignModel(SoftDeleteModel):
    campaign_type = models.CharField(db_index=True, **enum_field_kwargs(CampaignType))
    name = models.CharField(max_length=255)
    status = models.CharField(default=CampaignStatus.DRAFT.value, db_index=True, **enum_field_kwargs(CampaignStatus))
    discount_value_type = models.CharField(**enum_field_kwargs(DiscountValueType))
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    discount_fixed_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="UZS")
    validity_starts_at = models.DateTimeField()
    validity_ends_at = models.DateTimeField(null=True, blank=True)
    stacking_mode = models.CharField(default=StackingMode.EXCLUSIVE.value, **enum_field_kwargs(StackingMode))

    def __str__(self) -> str:  # pragma: no cover
        return self.name or str(self.id)

    class Meta:
        db_table = "pricing_campaigns"
        verbose_name=_("Campaign")
        verbose_name_plural = _("Campaigns")
        indexes = [models.Index(fields=["status", "validity_starts_at", "validity_ends_at"])]
        constraints = [
            models.CheckConstraint(condition=models.Q(validity_ends_at__isnull=True) | models.Q(validity_ends_at__gt=models.F("validity_starts_at")), name="ck_campaigns_ends_after_starts"),
        ]


class CampaignTargetModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    campaign = models.ForeignKey(CampaignModel, on_delete=models.CASCADE, related_name="targets")
    target_type = models.CharField(max_length=16)
    target_id = models.UUIDField(db_index=True)

    objects = AllObjectsManager()

    class Meta:
        db_table = "pricing_campaign_targets"
        constraints = [models.UniqueConstraint(fields=["campaign", "target_type", "target_id"], name="uq_campaign_targets_campaign_target")]
        indexes = [models.Index(fields=["target_type", "target_id"])]


class CouponModel(SoftDeleteModel):
    code = models.CharField(max_length=24, unique=True, db_index=True)
    coupon_type = models.CharField(**enum_field_kwargs(CouponType))
    status = models.CharField(default=CouponStatus.DRAFT.value, db_index=True, **enum_field_kwargs(CouponStatus))
    discount_value_type = models.CharField(**enum_field_kwargs(DiscountValueType))
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    discount_fixed_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="UZS")
    validity_starts_at = models.DateTimeField(null=True, blank=True)
    validity_ends_at = models.DateTimeField(null=True, blank=True)
    max_redemptions = models.PositiveIntegerField(null=True, blank=True)
    stacking_mode = models.CharField(default=StackingMode.EXCLUSIVE.value, **enum_field_kwargs(StackingMode))
    # business rules checked at the cart / checkout (apps/pricing/infrastructure/coupon_rules.py)
    title = models.CharField(max_length=120, blank=True, verbose_name=_("Internal name"), help_text=_("Where the code is used, e.g. “Telegram channel, October”."))
    min_order_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name=_("Minimum order"))
    max_per_customer = models.PositiveIntegerField(null=True, blank=True, verbose_name=_("Uses per customer"))

    def __str__(self) -> str:  # pragma: no cover
        return self.code or str(self.id)

    class Meta:
        db_table = "pricing_coupons"
        verbose_name=_("Coupon")
        verbose_name_plural = _("Coupons")
        indexes = [models.Index(fields=["status"])]


class CouponRedemptionModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    coupon = models.ForeignKey(CouponModel, on_delete=models.CASCADE, related_name="redemptions")
    redeemed_by = models.UUIDField(db_index=True)
    order_reference = models.CharField(max_length=64)
    redeemed_at = models.DateTimeField(db_index=True)

    objects = AllObjectsManager()

    class Meta:
        db_table = "pricing_coupon_redemptions"
        constraints = [models.UniqueConstraint(fields=["coupon", "order_reference"], name="uq_coupon_redemptions_coupon_order")]
        indexes = [models.Index(fields=["redeemed_by"])]


class PriceSnapshotModel(BaseModel):
    token = models.UUIDField(unique=True, db_index=True, default=uuid.uuid4)
    product_variant_id = models.UUIDField(db_index=True)
    locked_price_amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="UZS")
    expires_at = models.DateTimeField(db_index=True)
    status = models.CharField(default=PriceSnapshotStatus.LOCKED.value, db_index=True, **enum_field_kwargs(PriceSnapshotStatus))

    class Meta:
        db_table = "pricing_price_snapshots"
        verbose_name=_("Price Snapshot")
        verbose_name_plural = _("Price Snapshots")
        indexes = [models.Index(fields=["status", "expires_at"])]
        constraints = [models.CheckConstraint(condition=models.Q(locked_price_amount__gte=0), name="ck_price_snapshots_amount_non_negative")]


class PricingOutboxEvent(AbstractOutboxEvent):
    class Meta:
        db_table = "pricing_outbox_events"
        ordering = ["created_at"]


# ---------------------------------------------------------------------------
# Repricing documents (Narxlarni qayta baholash -- apps/pricing/infrastructure/repricing.py)
# ---------------------------------------------------------------------------


class RepricingModel(models.Model):
    """A batch price change: which variants, the rule used, every old -> new price; applied now or at a set time, revertible."""

    STATUS_CHOICES = (("draft", _("Qoralama")), ("scheduled", _("Rejalashtirilgan")), ("applied", _("Qo'llangan")), ("cancelled", _("Bekor qilingan")))

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.CharField(_("Raqam"), max_length=20, unique=True)
    title = models.CharField(_("Nomi"), max_length=160)
    note = models.CharField(_("Izoh"), max_length=255, blank=True, default="")
    status = models.CharField(_("Holat"), max_length=10, choices=STATUS_CHOICES, default="draft", db_index=True)
    rule = models.JSONField(default=dict, blank=True)  # {"mode", "value", "rounding", "compare", "filters"} as the builder had it
    scheduled_for = models.DateTimeField(_("Kuchga kirish vaqti"), null=True, blank=True, db_index=True)
    reverts = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="reverted_by", verbose_name=_("Qaytariladigan hujjat"))
    created_by = models.CharField(max_length=150, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    applied_by = models.CharField(max_length=150, blank=True, default="")
    applied_at = models.DateTimeField(null=True, blank=True)
    lines_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "pricing_repricings"
        ordering = ("-created_at",)
        verbose_name = _("Narxlarni qayta baholash")
        verbose_name_plural = _("Narxlarni qayta baholash")
        permissions = [("apply_repricing", "Can apply repricing documents")]

    def __str__(self) -> str:
        return f"{self.number} · {self.title}"


class RepricingLineModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    repricing = models.ForeignKey(RepricingModel, on_delete=models.CASCADE, related_name="lines")
    product_variant_id = models.UUIDField(db_index=True)
    old_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    new_price = models.DecimalField(max_digits=14, decimal_places=2)
    old_compare_at = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    new_compare_at = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    applied = models.BooleanField(default=False)
    error = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "pricing_repricing_lines"
        constraints = [models.UniqueConstraint(fields=["repricing", "product_variant_id"], name="uniq_repricing_line_variant")]
