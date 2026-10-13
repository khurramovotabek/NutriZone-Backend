"""
Ordering API serializers.

Structural validation only -- format/enum checks delegate to the same
domain value objects and enums used elsewhere, per MIC §6's "one
place" rule. Matches every prior module's `interfaces/api/v1/
serializers.py` pattern. `product_variant_id`, `customer_id`,
`cart_id`, `payment_id`, `fulfillment_id`, `price_snapshot_id`,
`reservation_id` are always plain `UUIDField`s -- never a nested
serializer for a foreign aggregate, per this module's "reference only
UUIDs" rule.
"""
from __future__ import annotations

from rest_framework import serializers

from apps.ordering.domain.enums import (
    CancellationReason,
    CancellationStatus,
    FulfillmentReferenceStatus,
    InvoiceStatus,
    OrderChannel,
    OrderFailureReason,
    OrderLineItemStatus,
    OrderLockReason,
    OrderStatus,
    OrderType,
    PaymentReferenceStatus,
    ReturnReason,
    ReturnStatus,
)
from apps.ordering.domain.value_objects import OrderNote
from common.exceptions import ValidationFailed


def _validate_note(value: str) -> str:
    try:
        OrderNote(value)
    except ValidationFailed as exc:
        raise serializers.ValidationError(exc.message) from exc
    return value


# --- Read shapes -----------------------------------------------------


class MoneySerializer(serializers.Serializer):
    """Every monetary field in this module renders through this exact shape -- amount as a string (never a float, to avoid precision loss) plus currency, matching every prior module's Money serialization convention."""

    amount = serializers.CharField(read_only=True)
    currency = serializers.CharField(read_only=True)


class AddressSnapshotSerializer(serializers.Serializer):
    """Immutable once the order exists -- read-only in this shape; changes go exclusively through UpdateAddressSerializer / the dedicated /address/ endpoint, never through a generic PATCH of the order itself."""

    recipient_name = serializers.CharField(read_only=True)
    line1 = serializers.CharField(read_only=True)
    line2 = serializers.CharField(read_only=True, allow_null=True)
    city = serializers.CharField(read_only=True)
    region = serializers.CharField(read_only=True, allow_null=True)
    postal_code = serializers.CharField(read_only=True, allow_null=True)
    country_code = serializers.CharField(read_only=True)
    phone = serializers.CharField(read_only=True, allow_null=True)


class OrderLineSerializer(serializers.Serializer):
    """Immutable once the order exists -- order lines are frozen at creation time (`Order._assert_modifiable()`), so every field here is read-only; there is no 'update a line' endpoint by design."""

    id = serializers.CharField(read_only=True)
    product_variant_id = serializers.CharField(read_only=True)
    quantity = serializers.IntegerField(read_only=True)
    unit_price = MoneySerializer(read_only=True)
    discount_amount = MoneySerializer(read_only=True)
    tax_amount = MoneySerializer(read_only=True)
    line_total = MoneySerializer(read_only=True)
    status = serializers.ChoiceField(choices=OrderLineItemStatus.values(), read_only=True)
    price_snapshot_id = serializers.CharField(read_only=True, allow_null=True)
    reservation_id = serializers.CharField(read_only=True, allow_null=True)


class StatusHistorySerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    from_status = serializers.CharField(read_only=True, allow_null=True)
    to_status = serializers.CharField(read_only=True)
    reason = serializers.CharField(read_only=True, allow_null=True)
    changed_at = serializers.DateTimeField(read_only=True)
    actor_id = serializers.CharField(read_only=True, allow_null=True)


class PaymentReferenceSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    payment_id = serializers.CharField(read_only=True)
    amount = MoneySerializer(read_only=True)
    status = serializers.ChoiceField(choices=PaymentReferenceStatus.values(), read_only=True)
    processed_at = serializers.DateTimeField(read_only=True, allow_null=True)


class FulfillmentReferenceSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    fulfillment_id = serializers.CharField(read_only=True)
    status = serializers.ChoiceField(choices=FulfillmentReferenceStatus.values(), read_only=True)
    tracking_number = serializers.CharField(read_only=True, allow_null=True)
    shipped_at = serializers.DateTimeField(read_only=True, allow_null=True)
    delivered_at = serializers.DateTimeField(read_only=True, allow_null=True)


class InvoiceSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    invoice_number = serializers.CharField(read_only=True)
    total_amount = MoneySerializer(read_only=True)
    status = serializers.ChoiceField(choices=InvoiceStatus.values(), read_only=True)
    issued_at = serializers.DateTimeField(read_only=True, allow_null=True)


class FailureSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    reason = serializers.ChoiceField(choices=OrderFailureReason.values(), read_only=True)
    detail = serializers.CharField(read_only=True)
    occurred_at = serializers.DateTimeField(read_only=True)


class OrderSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    order_number = serializers.CharField(read_only=True)
    customer_id = serializers.CharField(read_only=True, allow_null=True)
    cart_id = serializers.CharField(read_only=True, allow_null=True)
    currency = serializers.CharField(read_only=True)
    order_type = serializers.ChoiceField(choices=OrderType.values(), read_only=True)
    channel = serializers.ChoiceField(choices=OrderChannel.values(), read_only=True)
    status = serializers.ChoiceField(choices=OrderStatus.values(), read_only=True)
    version = serializers.IntegerField(read_only=True)
    is_locked = serializers.BooleanField(read_only=True)
    lock_reason = serializers.CharField(read_only=True, allow_null=True)
    is_archived = serializers.BooleanField(read_only=True)
    lines = OrderLineSerializer(many=True, read_only=True)
    coupon_ids = serializers.ListField(child=serializers.CharField(), read_only=True)
    payment_references = PaymentReferenceSerializer(many=True, read_only=True)
    fulfillment_references = FulfillmentReferenceSerializer(many=True, read_only=True)
    invoice = InvoiceSerializer(read_only=True, allow_null=True)
    shipping_address = AddressSnapshotSerializer(read_only=True)
    billing_address = AddressSnapshotSerializer(read_only=True)
    note = serializers.CharField(read_only=True, allow_null=True)
    customer_comment = serializers.CharField(read_only=True, allow_null=True)
    placed_at = serializers.DateTimeField(read_only=True, allow_null=True)


class ReturnLineSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    order_line_item_id = serializers.CharField(read_only=True)
    quantity = serializers.IntegerField(read_only=True)


class ReturnSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    return_number = serializers.CharField(read_only=True)
    order_id = serializers.CharField(read_only=True)
    status = serializers.ChoiceField(choices=ReturnStatus.values(), read_only=True)
    reason = serializers.ChoiceField(choices=ReturnReason.values(), read_only=True)
    lines = ReturnLineSerializer(many=True, read_only=True)
    refund_amount = MoneySerializer(read_only=True, allow_null=True)
    requested_at = serializers.DateTimeField(read_only=True, allow_null=True)
    approved_at = serializers.DateTimeField(read_only=True, allow_null=True)
    received_at = serializers.DateTimeField(read_only=True, allow_null=True)
    refunded_at = serializers.DateTimeField(read_only=True, allow_null=True)


class CancellationLineSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    order_line_item_id = serializers.CharField(read_only=True)
    quantity = serializers.IntegerField(read_only=True)


class CancellationSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    order_id = serializers.CharField(read_only=True)
    status = serializers.ChoiceField(choices=CancellationStatus.values(), read_only=True)
    reason = serializers.ChoiceField(choices=CancellationReason.values(), read_only=True)
    lines = CancellationLineSerializer(many=True, read_only=True)
    refund_amount = MoneySerializer(read_only=True, allow_null=True)
    requested_at = serializers.DateTimeField(read_only=True, allow_null=True)
    approved_at = serializers.DateTimeField(read_only=True, allow_null=True)
    completed_at = serializers.DateTimeField(read_only=True, allow_null=True)


# --- Command / request DTOs ------------------------------------------


class AddressInputSerializer(serializers.Serializer):
    """Write-side shape for shipping/billing address input -- structurally identical to AddressSnapshotSerializer's fields but writable, used by CreateOrderSerializer and UpdateAddressSerializer."""

    recipient_name = serializers.CharField(max_length=255)
    line1 = serializers.CharField(max_length=255)
    line2 = serializers.CharField(max_length=255, required=False, allow_null=True, allow_blank=True)
    city = serializers.CharField(max_length=120)
    region = serializers.CharField(max_length=120, required=False, allow_null=True, allow_blank=True)
    postal_code = serializers.CharField(max_length=32, required=False, allow_null=True, allow_blank=True)
    country_code = serializers.CharField(min_length=2, max_length=2)
    phone = serializers.CharField(max_length=32, required=False, allow_null=True, allow_blank=True)

    def validate_country_code(self, value: str) -> str:
        if not value.isupper():
            raise serializers.ValidationError("country_code must be a 2-letter uppercase ISO code.")
        return value


class OrderLineInputSerializer(serializers.Serializer):
    product_variant_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)
    unit_price = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    discount_amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, default="0")
    tax_amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, default="0")
    price_snapshot_id = serializers.UUIDField(required=False, allow_null=True)
    reservation_id = serializers.UUIDField(required=False, allow_null=True)


class CreateOrderSerializer(serializers.Serializer):
    cart_id = serializers.UUIDField(required=False, allow_null=True)
    customer_id = serializers.UUIDField(required=False, allow_null=True)
    currency = serializers.CharField(max_length=3, default="UZS")
    channel = serializers.ChoiceField(choices=OrderChannel.values(), default=OrderChannel.WEB.value)
    shipping_address = AddressInputSerializer()
    billing_address = AddressInputSerializer()
    line_items = OrderLineInputSerializer(many=True)
    coupon_ids = serializers.ListField(child=serializers.UUIDField(), required=False)

    def validate_line_items(self, value: list) -> list:
        if not value:
            raise serializers.ValidationError("An order must have at least one line item.")
        return value


class UpdateAddressSerializer(serializers.Serializer):
    shipping_address = AddressInputSerializer(required=False, allow_null=True)
    billing_address = AddressInputSerializer(required=False, allow_null=True)


class CancelOrderSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


class LockOrderSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=OrderLockReason.values())


class AttachShipmentSerializer(serializers.Serializer):
    fulfillment_id = serializers.UUIDField()


class AttachPaymentSerializer(serializers.Serializer):
    payment_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)


class PaymentWebhookSerializer(serializers.Serializer):
    """
    The internal, provider-agnostic webhook contract (Phase 02E) --
    matches `apps.ordering.infrastructure.gateways.payment_gateway.
    PaymentGateway`'s own documented design: a future, real payment
    provider's adapter would translate its own native webhook shape
    into this one before it ever reaches Ordering.
    """

    provider = serializers.CharField(max_length=64)
    provider_transaction_id = serializers.CharField(max_length=255)
    order_id = serializers.UUIDField()
    payment_id = serializers.UUIDField()
    event_type = serializers.ChoiceField(choices=["authorized", "captured", "failed", "refunded", "partially_refunded"])
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    currency = serializers.CharField(max_length=3, min_length=3)


class AttachCouponSerializer(serializers.Serializer):
    coupon_id = serializers.UUIDField()


class AttachReservationSerializer(serializers.Serializer):
    line_item_id = serializers.UUIDField()
    reservation_id = serializers.UUIDField()


class AttachPriceSnapshotSerializer(serializers.Serializer):
    line_item_id = serializers.UUIDField()
    price_snapshot_id = serializers.UUIDField()


class RequestReturnSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=ReturnReason.values())
    lines = serializers.ListField(child=serializers.DictField())

    def validate_lines(self, value: list) -> list:
        if not value:
            raise serializers.ValidationError("A return request must include at least one line item.")
        for entry in value:
            if "order_line_item_id" not in entry or "quantity" not in entry:
                raise serializers.ValidationError("Each return line must include order_line_item_id and quantity.")
        return value


class RejectReturnSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


class RefundReturnSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    currency = serializers.CharField(max_length=3, default="UZS")


class RequestCancellationSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=CancellationReason.values())
    lines = serializers.ListField(child=serializers.DictField())

    def validate_lines(self, value: list) -> list:
        if not value:
            raise serializers.ValidationError("A cancellation request must include at least one line item.")
        for entry in value:
            if "order_line_item_id" not in entry or "quantity" not in entry:
                raise serializers.ValidationError("Each cancellation line must include order_line_item_id and quantity.")
        return value


class RejectCancellationSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


class CompleteCancellationSerializer(serializers.Serializer):
    refund_amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False, allow_null=True)
    currency = serializers.CharField(max_length=3, default="UZS")


class IssueInvoiceSerializer(serializers.Serializer):
    sequence = serializers.IntegerField(min_value=1)
