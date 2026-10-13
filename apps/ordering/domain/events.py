"""
Ordering domain events.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class OrderCreated:
    order_id: uuid.UUID
    order_number: str
    cart_id: uuid.UUID | None
    customer_id: uuid.UUID | None

    def to_payload(self) -> dict:
        return {**asdict(self), "order_id": str(self.order_id), "cart_id": str(self.cart_id) if self.cart_id else None, "customer_id": str(self.customer_id) if self.customer_id else None}


@dataclass(frozen=True, slots=True)
class OrderConfirmed:
    order_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"order_id": str(self.order_id)}


@dataclass(frozen=True, slots=True)
class OrderProcessingStarted:
    order_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"order_id": str(self.order_id)}


@dataclass(frozen=True, slots=True)
class OrderShipped:
    order_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"order_id": str(self.order_id)}


@dataclass(frozen=True, slots=True)
class OrderDelivered:
    order_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"order_id": str(self.order_id)}


@dataclass(frozen=True, slots=True)
class OrderCompleted:
    order_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"order_id": str(self.order_id)}


@dataclass(frozen=True, slots=True)
class OrderCancelled:
    order_id: uuid.UUID
    reason: str

    def to_payload(self) -> dict:
        return {**asdict(self), "order_id": str(self.order_id)}


@dataclass(frozen=True, slots=True)
class OrderFailedEvent:
    order_id: uuid.UUID
    reason: str

    def to_payload(self) -> dict:
        return {**asdict(self), "order_id": str(self.order_id)}


@dataclass(frozen=True, slots=True)
class LineItemCancelled:
    order_id: uuid.UUID
    line_item_id: uuid.UUID
    quantity: int

    def to_payload(self) -> dict:
        return {**asdict(self), "order_id": str(self.order_id), "line_item_id": str(self.line_item_id)}


@dataclass(frozen=True, slots=True)
class LineItemReturned:
    order_id: uuid.UUID
    line_item_id: uuid.UUID
    quantity: int

    def to_payload(self) -> dict:
        return {**asdict(self), "order_id": str(self.order_id), "line_item_id": str(self.line_item_id)}


@dataclass(frozen=True, slots=True)
class PaymentReferenceAdded:
    order_id: uuid.UUID
    payment_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"order_id": str(self.order_id), "payment_id": str(self.payment_id)}


@dataclass(frozen=True, slots=True)
class PaymentStatusUpdated:
    order_id: uuid.UUID
    payment_id: uuid.UUID
    status: str

    def to_payload(self) -> dict:
        return {**asdict(self), "order_id": str(self.order_id), "payment_id": str(self.payment_id)}


@dataclass(frozen=True, slots=True)
class FulfillmentReferenceAdded:
    order_id: uuid.UUID
    fulfillment_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"order_id": str(self.order_id), "fulfillment_id": str(self.fulfillment_id)}


@dataclass(frozen=True, slots=True)
class FulfillmentStatusUpdated:
    order_id: uuid.UUID
    fulfillment_id: uuid.UUID
    status: str

    def to_payload(self) -> dict:
        return {**asdict(self), "order_id": str(self.order_id), "fulfillment_id": str(self.fulfillment_id)}


@dataclass(frozen=True, slots=True)
class InvoiceIssued:
    order_id: uuid.UUID
    invoice_id: uuid.UUID
    invoice_number: str

    def to_payload(self) -> dict:
        return {**asdict(self), "order_id": str(self.order_id), "invoice_id": str(self.invoice_id)}


@dataclass(frozen=True, slots=True)
class ReturnRequested:
    return_id: uuid.UUID
    order_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"return_id": str(self.return_id), "order_id": str(self.order_id)}


@dataclass(frozen=True, slots=True)
class ReturnApproved:
    return_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"return_id": str(self.return_id)}


@dataclass(frozen=True, slots=True)
class ReturnRejected:
    return_id: uuid.UUID
    reason: str

    def to_payload(self) -> dict:
        return {**asdict(self), "return_id": str(self.return_id)}


@dataclass(frozen=True, slots=True)
class ReturnReceived:
    return_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"return_id": str(self.return_id)}


@dataclass(frozen=True, slots=True)
class ReturnRefunded:
    return_id: uuid.UUID
    refund_amount: str

    def to_payload(self) -> dict:
        return {**asdict(self), "return_id": str(self.return_id)}


@dataclass(frozen=True, slots=True)
class CancellationRequested:
    cancellation_id: uuid.UUID
    order_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"cancellation_id": str(self.cancellation_id), "order_id": str(self.order_id)}


@dataclass(frozen=True, slots=True)
class CancellationApproved:
    cancellation_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"cancellation_id": str(self.cancellation_id)}


@dataclass(frozen=True, slots=True)
class CancellationRejected:
    cancellation_id: uuid.UUID
    reason: str

    def to_payload(self) -> dict:
        return {**asdict(self), "cancellation_id": str(self.cancellation_id)}


@dataclass(frozen=True, slots=True)
class CancellationCompleted:
    cancellation_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"cancellation_id": str(self.cancellation_id)}


@dataclass(frozen=True, slots=True)
class OrderLockedEvent:
    """Named with an Event suffix specifically to avoid colliding with the domain exception `OrderLocked` (exceptions.py) -- the same naming-collision pattern already resolved for `apps.cart`'s `CartLockedEvent`/`CartLocked`, `apps.inventory`'s `InventoryArchivedEvent`/`InventoryArchived`, and `apps.pricing`'s `PriceListArchivedEvent`/`PriceListArchived`. Caught here before it ever compiled as a real collision, not after."""

    order_id: uuid.UUID
    reason: str

    def to_payload(self) -> dict:
        return {**asdict(self), "order_id": str(self.order_id)}


@dataclass(frozen=True, slots=True)
class OrderUnlocked:
    order_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"order_id": str(self.order_id)}


@dataclass(frozen=True, slots=True)
class OrderArchivedEvent:
    order_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"order_id": str(self.order_id)}


@dataclass(frozen=True, slots=True)
class OrderRestored:
    order_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"order_id": str(self.order_id)}
