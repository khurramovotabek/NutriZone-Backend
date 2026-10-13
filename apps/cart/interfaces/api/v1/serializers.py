"""
Cart API serializers.

Structural validation only -- format checks delegate to the same
domain value objects used elsewhere (CartCode-equivalent formats,
Quantity), per MIC §6's "one place" rule. Matches every prior module's
`interfaces/api/v1/serializers.py` pattern.
"""
from __future__ import annotations

from rest_framework import serializers

from apps.cart.domain.enums import (
    CartItemStatus,
    CartLockReason,
    CartSource,
    CartType,
    CartValidationSeverity,
    MergeStrategy,
)
from apps.cart.domain.value_objects import CartNote, GiftMessage, Quantity
from common.exceptions import ValidationFailed


def _validate_quantity(value: int) -> int:
    try:
        Quantity(value)
    except ValidationFailed as exc:
        raise serializers.ValidationError(exc.message) from exc
    return value


def _validate_note(value: str) -> str:
    try:
        CartNote(value)
    except ValidationFailed as exc:
        raise serializers.ValidationError(exc.message) from exc
    return value


def _validate_gift_message(value: str) -> str:
    try:
        GiftMessage(value)
    except ValidationFailed as exc:
        raise serializers.ValidationError(exc.message) from exc
    return value


# --- Read shapes -----------------------------------------------------


class PriceSnapshotReferenceSerializer(serializers.Serializer):
    price_snapshot_id = serializers.CharField()
    unit_amount = serializers.CharField()
    currency = serializers.CharField()
    applied_at = serializers.DateTimeField()


class ReservationReferenceSerializer(serializers.Serializer):
    reservation_id = serializers.CharField()
    reserved_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField(allow_null=True, required=False)


class CartItemSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    product_variant_id = serializers.CharField()
    quantity = serializers.IntegerField()
    status = serializers.ChoiceField(choices=CartItemStatus.values(), read_only=True)
    price_reference = PriceSnapshotReferenceSerializer(allow_null=True, required=False)
    reservation_reference = ReservationReferenceSerializer(allow_null=True, required=False)
    note = serializers.CharField(allow_null=True, required=False)


class CartSnapshotSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    token = serializers.CharField(read_only=True)
    version_at_capture = serializers.IntegerField(read_only=True)
    captured_at = serializers.DateTimeField(read_only=True)
    items_snapshot = serializers.ListField(child=serializers.DictField(), read_only=True)


class CartAuditEntrySerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    action = serializers.CharField(read_only=True)
    actor_id = serializers.CharField(allow_null=True, read_only=True)
    occurred_at = serializers.DateTimeField(read_only=True)
    details = serializers.DictField(read_only=True)


class ValidationIssueSerializer(serializers.Serializer):
    severity = serializers.ChoiceField(choices=CartValidationSeverity.values(), read_only=True)
    code = serializers.CharField(read_only=True)
    message = serializers.CharField(read_only=True)
    item_id = serializers.CharField(allow_null=True, read_only=True)


class CartSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    code = serializers.CharField(read_only=True)
    token = serializers.CharField(read_only=True)
    version = serializers.IntegerField(read_only=True)
    currency = serializers.CharField(read_only=True)
    cart_type = serializers.ChoiceField(choices=CartType.values(), read_only=True)
    status = serializers.CharField(read_only=True)
    customer_id = serializers.CharField(allow_null=True, read_only=True)
    region = serializers.CharField(allow_null=True, read_only=True)
    channel = serializers.CharField(allow_null=True, read_only=True)
    items = CartItemSerializer(many=True, read_only=True)
    coupon_ids = serializers.ListField(child=serializers.CharField(), read_only=True)
    note = serializers.CharField(allow_null=True, read_only=True)
    gift_message = serializers.CharField(allow_null=True, read_only=True)
    expires_at = serializers.DateTimeField(allow_null=True, read_only=True)
    is_locked = serializers.BooleanField(read_only=True)


# --- Response shapes ---------------------------------------------------


class CartSummarySerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    code = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    cart_type = serializers.CharField(read_only=True)
    item_count = serializers.IntegerField(read_only=True)


class CartCalculationSerializer(serializers.Serializer):
    """Reserved response shape for a future cart-level price calculation summary -- Cart itself never calculates prices (that's Pricing's job, called by a future orchestration layer); this shape exists so `GET /cart/{code}/` can eventually report a total without Cart performing the arithmetic itself. Not yet populated by any view in this phase (no Application Service computes cart totals), included per this phase's explicit serializer list."""

    item_count = serializers.IntegerField(read_only=True)
    priced_item_count = serializers.IntegerField(read_only=True)
    currency = serializers.CharField(read_only=True)


class ValidationResultSerializer(serializers.Serializer):
    is_valid = serializers.BooleanField(read_only=True)
    issues = ValidationIssueSerializer(many=True, read_only=True)


# --- Command / request DTOs ------------------------------------------


class CreateCartSerializer(serializers.Serializer):
    currency = serializers.CharField(max_length=3, default="UZS")
    cart_type = serializers.ChoiceField(choices=CartType.values(), default=CartType.GUEST.value)
    source = serializers.ChoiceField(choices=CartSource.values(), default=CartSource.WEB.value)
    region = serializers.CharField(required=False, allow_null=True)
    channel = serializers.CharField(required=False, allow_null=True)


class UpdateCartSerializer(serializers.Serializer):
    """Backs PATCH /cart/{code}/ -- note/gift_message are the only customer-mutable top-level fields; status/version/items are managed through their own dedicated endpoints, never through a generic PATCH."""

    note = serializers.CharField(required=False, allow_null=True, allow_blank=True, validators=[_validate_note])
    gift_message = serializers.CharField(required=False, allow_null=True, allow_blank=True, validators=[_validate_gift_message])


class AddItemSerializer(serializers.Serializer):
    product_variant_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, validators=[_validate_quantity])


class UpdateItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1, validators=[_validate_quantity])


class ApplyCouponSerializer(serializers.Serializer):
    coupon_id = serializers.UUIDField()


class ApplyCheckoutCouponByCodeSerializer(serializers.Serializer):
    """Real, closed gap: the storefront customer types a human-readable coupon code (e.g. "SUMMER20"), never a UUID -- resolved server-side against the real, existing CouponModel. Deliberately separate from ApplyCouponSerializer/CouponReferenceView, which is a pre-existing, staff-only endpoint whose established repricing behavior (overwriting each item's own locked price) is left completely untouched."""

    coupon_code = serializers.CharField(max_length=24)


class AttachReservationSerializer(serializers.Serializer):
    item_id = serializers.UUIDField()
    reservation_id = serializers.UUIDField()
    expires_at = serializers.DateTimeField(required=False, allow_null=True)


class DetachReservationSerializer(serializers.Serializer):
    item_id = serializers.UUIDField()


class AttachPriceSnapshotSerializer(serializers.Serializer):
    item_id = serializers.UUIDField()
    price_snapshot_id = serializers.UUIDField()
    unit_amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    currency = serializers.CharField(max_length=3, default="UZS")


class PriceItemSerializer(serializers.Serializer):
    """Phase 09.4: the customer-safe counterpart to AttachPriceSnapshotSerializer -- no price_snapshot_id, no unit_amount, no currency. item_id comes from the URL path; only an optional coupon code is accepted in the body."""

    coupon_code = serializers.CharField(required=False, allow_null=True)


class DetachPriceSnapshotSerializer(serializers.Serializer):
    item_id = serializers.UUIDField()


class MergeGuestCartSerializer(serializers.Serializer):
    guest_cart_id = serializers.UUIDField()
    strategy = serializers.ChoiceField(choices=MergeStrategy.values(), required=False, allow_null=True)


class LockCartSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=CartLockReason.values(), default=CartLockReason.CHECKOUT_IN_PROGRESS.value)


class CheckoutCartSerializer(serializers.Serializer):
    """Phase 09.7: contextual inputs only -- shipping/billing address IDs (ownership-checked against the real geo.Address aggregate). No monetary field of any kind."""

    # delivery: a saved address of the customer. pickup: the branch (pickup_store_id) -- no address needed.
    fulfilment_method = serializers.ChoiceField(choices=("delivery", "pickup"), required=False, default="delivery")
    pickup_store_id = serializers.UUIDField(required=False)
    shipping_address_id = serializers.UUIDField(required=False)
    billing_address_id = serializers.UUIDField(required=False)
    # Loyalty: coins to pay with (1 coin = 1 so'm). Validated server-side against the
    # customer's real balance and the programme's max-share rule -- never trusted as money.
    coins_to_redeem = serializers.IntegerField(required=False, min_value=0, default=0)

    def validate(self, attrs):
        if attrs.get("fulfilment_method") == "pickup":
            if not attrs.get("pickup_store_id"):
                raise serializers.ValidationError({"pickup_store_id": "Choose the store to pick the order up from."})
        elif not attrs.get("shipping_address_id"):
            raise serializers.ValidationError({"shipping_address_id": "This field is required."})
        return attrs
