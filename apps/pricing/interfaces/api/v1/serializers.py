"""
Pricing API serializers.

Structural validation only -- format checks delegate to the same
domain value objects used elsewhere (PriceListCode, CouponCode,
RegionCode), per MIC §6's "one place" rule. Matches every prior
module's `interfaces/api/v1/serializers.py` pattern.
"""
from __future__ import annotations

from rest_framework import serializers

from apps.pricing.domain.enums import (
    CampaignStatus,
    CampaignType,
    CouponStatus,
    CouponType,
    DiscountValueType,
    PriceChangeReason,
    PriceListStatus,
    PriceSnapshotStatus,
    PricingRuleStatus,
    PricingRuleType,
    StackingMode,
)
from apps.pricing.domain.value_objects import CouponCode, PriceListCode, RegionCode
from common.exceptions import ValidationFailed


def _validate_price_list_code(value: str) -> str:
    try:
        PriceListCode(value)
    except ValidationFailed as exc:
        raise serializers.ValidationError(exc.message) from exc
    return value


def _validate_coupon_code(value: str) -> str:
    try:
        CouponCode(value)
    except ValidationFailed as exc:
        raise serializers.ValidationError(exc.message) from exc
    return value


def _validate_region_code(value: str) -> str:
    try:
        RegionCode(value)
    except ValidationFailed as exc:
        raise serializers.ValidationError(exc.message) from exc
    return value


# --- Read shapes -----------------------------------------------------


class PriceListEntrySerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    product_variant_id = serializers.CharField()
    base_price_amount = serializers.DecimalField(max_digits=14, decimal_places=2, source="base_price.amount")
    cost_price_amount = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True, required=False)
    sale_price_amount = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True, required=False)
    compare_at_price_amount = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True, required=False)


class PriceHistoryEntrySerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    price_type = serializers.CharField(read_only=True)
    old_amount = serializers.CharField(allow_null=True, read_only=True)
    new_amount = serializers.CharField(read_only=True)
    reason = serializers.CharField(read_only=True)
    changed_at = serializers.DateTimeField(read_only=True)


class PriceListSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    code = serializers.CharField()
    name = serializers.CharField()
    currency = serializers.CharField(max_length=3)
    status = serializers.CharField(read_only=True)
    region = serializers.CharField(allow_null=True, required=False)


class QuantityTierSerializer(serializers.Serializer):
    minimum_quantity = serializers.IntegerField(min_value=1)
    discount_value_type = serializers.ChoiceField(choices=DiscountValueType.values())
    discount_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    discount_fixed_amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)


class PricingRuleSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    rule_type = serializers.ChoiceField(choices=PricingRuleType.values())
    status = serializers.CharField(read_only=True)
    priority = serializers.IntegerField(default=100)
    region = serializers.CharField(allow_null=True, required=False)
    membership_tier_code = serializers.CharField(allow_null=True, required=False)


class CampaignTargetSerializer(serializers.Serializer):
    target_type = serializers.ChoiceField(choices=["variant", "category", "bundle"])
    target_id = serializers.UUIDField()


class CampaignSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    campaign_type = serializers.ChoiceField(choices=CampaignType.values())
    name = serializers.CharField(max_length=255)
    status = serializers.CharField(read_only=True)
    stacking_mode = serializers.ChoiceField(choices=StackingMode.values(), default=StackingMode.EXCLUSIVE.value)


class CouponRedemptionSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    redeemed_by = serializers.CharField(read_only=True)
    order_reference = serializers.CharField(read_only=True)
    redeemed_at = serializers.DateTimeField(read_only=True)


class CouponSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    code = serializers.CharField(validators=[_validate_coupon_code])
    coupon_type = serializers.ChoiceField(choices=CouponType.values())
    status = serializers.CharField(read_only=True)
    max_redemptions = serializers.IntegerField(required=False, allow_null=True, min_value=1)


class PriceSnapshotSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    token = serializers.CharField(read_only=True)
    product_variant_id = serializers.CharField(read_only=True)
    locked_price_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    expires_at = serializers.DateTimeField(read_only=True)
    status = serializers.CharField(read_only=True)


class DiscountLineSerializer(serializers.Serializer):
    source_type = serializers.CharField(read_only=True)
    label = serializers.CharField(read_only=True)
    amount_deducted = serializers.CharField(read_only=True)


class CalculationResultSerializer(serializers.Serializer):
    base_price = serializers.DictField(read_only=True)
    final_price = serializers.DictField(read_only=True)
    total_discount = serializers.DictField(read_only=True)
    applied_discounts = DiscountLineSerializer(many=True, read_only=True)


# --- Request / command DTOs ------------------------------------------


class CreatePriceListSerializer(serializers.Serializer):
    code = serializers.CharField(validators=[_validate_price_list_code])
    name = serializers.CharField(max_length=255)
    currency = serializers.CharField(max_length=3, default="UZS")
    region = serializers.CharField(required=False, allow_null=True, validators=[_validate_region_code])


class SetPriceSerializer(serializers.Serializer):
    product_variant_id = serializers.UUIDField()
    base_amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    currency = serializers.CharField(max_length=3, default="UZS")
    cost_amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)
    sale_amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)
    compare_at_amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)
    reason = serializers.ChoiceField(choices=PriceChangeReason.values(), default=PriceChangeReason.MANUAL.value)


class CreatePricingRuleSerializer(serializers.Serializer):
    rule_type = serializers.ChoiceField(choices=PricingRuleType.values())
    discount_value_type = serializers.ChoiceField(choices=DiscountValueType.values())
    discount_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    discount_fixed_amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)
    currency = serializers.CharField(max_length=3, default="UZS")
    region = serializers.CharField(required=False, allow_null=True)
    membership_tier_code = serializers.CharField(required=False, allow_null=True)
    priority = serializers.IntegerField(default=100)


class CreateCampaignSerializer(serializers.Serializer):
    campaign_type = serializers.ChoiceField(choices=CampaignType.values())
    name = serializers.CharField(max_length=255)
    discount_value_type = serializers.ChoiceField(choices=DiscountValueType.values())
    discount_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    discount_fixed_amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)
    currency = serializers.CharField(max_length=3, default="UZS")
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField(required=False, allow_null=True)
    stacking_mode = serializers.ChoiceField(choices=StackingMode.values(), default=StackingMode.EXCLUSIVE.value)
    target_variant_ids = serializers.ListField(child=serializers.UUIDField(), required=False)


class CreateCouponSerializer(serializers.Serializer):
    code = serializers.CharField(validators=[_validate_coupon_code])
    coupon_type = serializers.ChoiceField(choices=CouponType.values())
    discount_value_type = serializers.ChoiceField(choices=DiscountValueType.values())
    discount_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    discount_fixed_amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)
    currency = serializers.CharField(max_length=3, default="UZS")
    starts_at = serializers.DateTimeField(required=False, allow_null=True)
    ends_at = serializers.DateTimeField(required=False, allow_null=True)
    max_redemptions = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    stacking_mode = serializers.ChoiceField(choices=StackingMode.values(), default=StackingMode.EXCLUSIVE.value)


class RedeemCouponSerializer(serializers.Serializer):
    redeemed_by = serializers.UUIDField()
    order_reference = serializers.CharField(max_length=64)


class LockPriceSerializer(serializers.Serializer):
    product_variant_id = serializers.UUIDField()
    locked_amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    currency = serializers.CharField(max_length=3, default="UZS")
    ttl_minutes = serializers.IntegerField(default=15, min_value=1, max_value=1440)


class CalculatePriceRequestSerializer(serializers.Serializer):
    price_list_id = serializers.UUIDField()
    product_variant_id = serializers.UUIDField()
    quantity = serializers.IntegerField(default=1, min_value=1)
    coupon_code = serializers.CharField(required=False, allow_null=True)
    region = serializers.CharField(required=False, allow_null=True)
    membership_tier_code = serializers.CharField(required=False, allow_null=True)


class IssueVariantPriceSnapshotSerializer(serializers.Serializer):
    """Phase 09.4: contextual inputs only -- no price_list_id (resolved server-side via get_active_for_region), no price field of any kind. This is the customer-safe counterpart to LockPriceSerializer, which accepts a direct locked_amount and is deliberately kept admin-only."""

    product_variant_id = serializers.UUIDField()
    quantity = serializers.IntegerField(default=1, min_value=1)
    coupon_code = serializers.CharField(required=False, allow_null=True)
    region = serializers.CharField(required=False, allow_null=True)
