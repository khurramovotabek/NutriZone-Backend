"""
Ordering domain entities (non-root members of Order/OrderReturn/
OrderCancellation).

Every cross-module reference here (OrderLineItem.product_variant_id,
.price_snapshot_id, .reservation_id, OrderPaymentReference.payment_id,
OrderFulfillmentReference.fulfillment_id) is a plain `uuid.UUID` field
-- never a type imported from Products/Pricing/Inventory/a future
Payments or Fulfillment module. This is the concrete mechanism behind
this module's "Ordering never imports Cart/Pricing/Inventory/Wallet/
Loyalty/Fulfillment/Payments domain" rule.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from apps.ordering.domain.enums import (
    FulfillmentReferenceStatus, InvoiceStatus, OrderFailureReason, OrderLineItemStatus, PaymentReferenceStatus,
)
from apps.ordering.domain.value_objects import Money, TrackingNumber


@dataclass(slots=True)
class OrderLineItem:
    """Non-root entity, owned by Order -- one product variant line item, frozen at order-confirmation time."""

    id: uuid.UUID
    product_variant_id: uuid.UUID
    quantity: int
    unit_price: Money
    discount_amount: Money
    tax_amount: Money
    status: OrderLineItemStatus = OrderLineItemStatus.ACTIVE
    price_snapshot_id: uuid.UUID | None = None
    reservation_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        from common.exceptions import ValidationFailed

        if self.quantity <= 0:
            raise ValidationFailed("Order line item quantity must be positive.")

    def line_total(self) -> Money:
        gross = self.unit_price.amount * self.quantity
        net = gross - self.discount_amount.amount + self.tax_amount.amount
        return Money(amount=net, currency=self.unit_price.currency)


@dataclass(slots=True)
class OrderStatusHistoryEntry:
    """Non-root entity, owned by Order -- an append-only record of every status transition, backing 'Order Status History'."""

    id: uuid.UUID
    from_status: str | None
    to_status: str
    reason: str | None
    changed_at: datetime
    actor_id: uuid.UUID | None = None


@dataclass(slots=True)
class OrderPaymentReference:
    """Non-root entity, owned by Order -- a cross-module reference to a payment attempt tracked by a future Payments/Wallet module. Ordering records what it was told, never executes payment itself."""

    id: uuid.UUID
    payment_id: uuid.UUID
    amount: Money
    status: PaymentReferenceStatus = PaymentReferenceStatus.PENDING
    processed_at: datetime | None = None


@dataclass(slots=True)
class OrderFulfillmentReference:
    """Non-root entity, owned by Order -- a cross-module reference to a fulfillment/shipment tracked by a future Fulfillment module. Supports multiple entries per order (partial/split shipments)."""

    id: uuid.UUID
    fulfillment_id: uuid.UUID
    status: FulfillmentReferenceStatus = FulfillmentReferenceStatus.PENDING
    tracking_number: TrackingNumber | None = None
    shipped_at: datetime | None = None
    delivered_at: datetime | None = None


@dataclass(slots=True)
class OrderInvoice:
    """Non-root entity, owned by Order (at most one) -- a generated, immutable-once-issued invoice record."""

    id: uuid.UUID
    invoice_number: str
    total_amount: Money
    status: InvoiceStatus = InvoiceStatus.DRAFT
    issued_at: datetime | None = None


@dataclass(slots=True)
class OrderFailure:
    """Non-root entity, owned by Order -- a structured record of a failed checkout attempt (distinct from Cancellation, which applies to an already-successful order)."""

    id: uuid.UUID
    reason: OrderFailureReason
    detail: str
    occurred_at: datetime


@dataclass(slots=True)
class ReturnLineItem:
    """Non-root entity, owned by OrderReturn -- which order line item (and how much of it) is being returned."""

    id: uuid.UUID
    order_line_item_id: uuid.UUID
    quantity: int

    def __post_init__(self) -> None:
        from common.exceptions import ValidationFailed

        if self.quantity <= 0:
            raise ValidationFailed("Return line item quantity must be positive.")


@dataclass(slots=True)
class CancellationLineItem:
    """Non-root entity, owned by OrderCancellation -- which order line item (and how much of it) is being cancelled, supporting partial cancellation."""

    id: uuid.UUID
    order_line_item_id: uuid.UUID
    quantity: int

    def __post_init__(self) -> None:
        from common.exceptions import ValidationFailed

        if self.quantity <= 0:
            raise ValidationFailed("Cancellation line item quantity must be positive.")
