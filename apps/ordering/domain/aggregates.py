"""
Ordering aggregates.

Three aggregate roots, per this module's own functional scope:

- `Order` -- the central aggregate; owns the checkout lifecycle, order
  status, order timeline, order audit, and every order-scoped
  reference (line items, payment/fulfillment references, invoice).
- `OrderReturn` -- an independent lifecycle (REQUESTED -> APPROVED/
  REJECTED -> RECEIVED -> REFUNDED -> CLOSED) that can outlive the
  parent order's own COMPLETED status by weeks; references `order_id`
  by ID only, never holds a live `Order` reference.
- `OrderCancellation` -- an independent lifecycle (REQUESTED ->
  APPROVED/REJECTED -> COMPLETED) for a formal cancellation request/
  approval workflow (distinct from Order's own simpler `cancel()`
  transition, which still exists on Order itself for
  immediately-approved cancellations); also references `order_id` by
  ID only.

Every cross-module reference (cart_id, customer_id,
product_variant_id, price_snapshot_id, reservation_id, coupon_ids,
payment_id, fulfillment_id) is a plain UUID -- never a domain import
from Cart/Pricing/Inventory/Identity/a future Payments or Fulfillment
module.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from apps.ordering.domain.entities import (
    CancellationLineItem, OrderFailure, OrderFulfillmentReference, OrderInvoice, OrderLineItem,
    OrderPaymentReference, OrderStatusHistoryEntry, ReturnLineItem,
)
from apps.ordering.domain.enums import (
    CancellationReason, CancellationStatus, FulfillmentReferenceStatus, InvoiceStatus, OrderChannel,
    OrderLineItemStatus, OrderLockReason, OrderStatus, OrderType, PaymentReferenceStatus, ReturnReason, ReturnStatus,
)
from apps.ordering.domain.events import (
    CancellationApproved, CancellationCompleted, CancellationRejected, CancellationRequested,
    FulfillmentReferenceAdded, FulfillmentStatusUpdated, InvoiceIssued, LineItemCancelled, LineItemReturned,
    OrderArchivedEvent, OrderCancelled, OrderCompleted, OrderConfirmed, OrderCreated, OrderDelivered,
    OrderFailedEvent, OrderLockedEvent, OrderProcessingStarted, OrderRestored, OrderShipped, OrderUnlocked,
    PaymentReferenceAdded, PaymentStatusUpdated, ReturnApproved, ReturnReceived, ReturnRefunded, ReturnRejected,
    ReturnRequested,
)
from apps.ordering.domain.exceptions import (
    CancellationQuantityExceedsOrdered, EmptyOrder, FulfillmentReferenceNotFound, InvalidCancellationLifecycleTransition,
    InvalidInvoiceLifecycleTransition, InvalidOrderArchivalTransition, InvalidOrderLifecycleTransition,
    InvalidReturnLifecycleTransition, InvoiceAlreadyIssued, OrderAlreadyCancelled, OrderAlreadyCompleted,
    OrderAlreadyLocked, OrderEntityNotFound, OrderLineItemNotFound, OrderLocked, OrderNotEligibleForCancellation,
    OrderNotLocked, OrderNotModifiable, PaymentReferenceNotFound, ReturnQuantityExceedsOrdered, ReturnWindowExpired,
)
from apps.ordering.domain.value_objects import (
    AddressSnapshot, CustomerComment, Money, OrderNote, OrderNumber, OrderTotal, OrderVersion, ReturnNumber,
    ReturnWindow, TrackingNumber,
)
from common.exceptions import ValidationFailed

_MUTABLE_STATUSES = (OrderStatus.DRAFT, OrderStatus.PENDING_PAYMENT)
DEFAULT_RETURN_WINDOW = ReturnWindow(timedelta(days=14))


@dataclass(slots=True)
class Order:
    """Aggregate root -- the central Ordering aggregate."""

    id: uuid.UUID
    order_number: OrderNumber
    customer_id: uuid.UUID | None
    cart_id: uuid.UUID | None
    shipping_address: AddressSnapshot
    billing_address: AddressSnapshot
    currency: str
    order_type: OrderType = OrderType.STANDARD
    channel: OrderChannel = OrderChannel.WEB
    status: OrderStatus = OrderStatus.DRAFT
    version: OrderVersion = field(default_factory=lambda: OrderVersion(1))
    lines: dict[uuid.UUID, OrderLineItem] = field(default_factory=dict)
    coupon_ids: set = field(default_factory=set)
    promotion_ids: set = field(default_factory=set)
    payment_references: dict[uuid.UUID, OrderPaymentReference] = field(default_factory=dict)
    fulfillment_references: dict[uuid.UUID, OrderFulfillmentReference] = field(default_factory=dict)
    invoice: OrderInvoice | None = None
    failures: list[OrderFailure] = field(default_factory=list)
    status_history: list[OrderStatusHistoryEntry] = field(default_factory=list)
    note: OrderNote | None = None
    customer_comment: CustomerComment | None = None
    placed_at: datetime | None = None
    lock_reason: OrderLockReason | None = None
    is_archived: bool = False

    # --- Internal helpers ------------------------------------------------

    def _bump_version(self) -> None:
        self.version = self.version.next()

    def _record_transition(self, to_status: OrderStatus, at: datetime, reason: str | None = None, actor_id: uuid.UUID | None = None) -> None:
        self.status_history.append(OrderStatusHistoryEntry(id=uuid.uuid4(), from_status=self.status.value, to_status=to_status.value, reason=reason, changed_at=at, actor_id=actor_id))
        self.status = to_status
        self._bump_version()

    def _assert_modifiable(self) -> None:
        if self.lock_reason is not None:
            raise OrderLocked(f"This order is locked ({self.lock_reason.value}) and cannot be modified.")
        if self.status not in _MUTABLE_STATUSES:
            raise OrderNotModifiable(f"Order contents are frozen once past DRAFT/PENDING_PAYMENT (current status: {self.status.value}).")

    def active_lines(self) -> list[OrderLineItem]:
        return [l for l in self.lines.values() if l.status == OrderLineItemStatus.ACTIVE]

    def compute_total(self) -> OrderTotal:
        """Recomputes the order's total purely from its own line items -- never calls back into Pricing. The Application layer supplies shipping_total separately since that's sourced from Cart's shipping estimate at order-creation time, not derivable from line items alone."""
        lines = self.active_lines()
        subtotal = sum((l.unit_price.amount * l.quantity for l in lines), start=Decimal("0"))
        discount = sum((l.discount_amount.amount for l in lines), start=Decimal("0"))
        tax = sum((l.tax_amount.amount for l in lines), start=Decimal("0"))
        return OrderTotal.compute(Money(amount=subtotal, currency=self.currency), Money(amount=discount, currency=self.currency), Money(amount=tax, currency=self.currency), Money(amount=Decimal("0"), currency=self.currency))

    # --- Creation from Cart ------------------------------------------------

    @staticmethod
    def create_from_cart_data(order_id: uuid.UUID, order_number: OrderNumber, cart_id: uuid.UUID | None, customer_id: uuid.UUID | None, shipping_address: AddressSnapshot, billing_address: AddressSnapshot, currency: str, lines: list[OrderLineItem], coupon_ids: set, channel: OrderChannel, at: datetime) -> tuple["Order", OrderCreated]:
        if not lines:
            raise EmptyOrder("Cannot create an order with zero line items.")
        order = Order(
            id=order_id, order_number=order_number, customer_id=customer_id, cart_id=cart_id, shipping_address=shipping_address, billing_address=billing_address,
            currency=currency, channel=channel, status=OrderStatus.PENDING_PAYMENT, lines={l.id: l for l in lines}, coupon_ids=coupon_ids, placed_at=at,
        )
        order._record_transition(OrderStatus.PENDING_PAYMENT, at, reason="order_created")
        event = OrderCreated(order_id=order.id, order_number=order_number.value, cart_id=cart_id, customer_id=customer_id)
        return order, event

    # --- Status transitions ------------------------------------------------

    def confirm(self, at: datetime) -> OrderConfirmed:
        if self.status != OrderStatus.PENDING_PAYMENT:
            raise InvalidOrderLifecycleTransition(f"Cannot confirm an order in status {self.status.value}.")
        self._record_transition(OrderStatus.CONFIRMED, at, reason="payment_confirmed")
        return OrderConfirmed(order_id=self.id)

    def start_processing(self, at: datetime) -> OrderProcessingStarted:
        if self.status != OrderStatus.CONFIRMED:
            raise InvalidOrderLifecycleTransition(f"Cannot start processing an order in status {self.status.value}.")
        self._record_transition(OrderStatus.PROCESSING, at, reason="processing_started")
        return OrderProcessingStarted(order_id=self.id)

    def ship(self, at: datetime) -> OrderShipped:
        if self.status != OrderStatus.PROCESSING:
            raise InvalidOrderLifecycleTransition(f"Cannot ship an order in status {self.status.value}.")
        self._record_transition(OrderStatus.SHIPPED, at, reason="shipped")
        return OrderShipped(order_id=self.id)

    def deliver(self, at: datetime) -> OrderDelivered:
        if self.status != OrderStatus.SHIPPED:
            raise InvalidOrderLifecycleTransition(f"Cannot deliver an order in status {self.status.value}.")
        self._record_transition(OrderStatus.DELIVERED, at, reason="delivered")
        return OrderDelivered(order_id=self.id)

    def complete(self, at: datetime) -> OrderCompleted:
        if self.status != OrderStatus.DELIVERED:
            raise InvalidOrderLifecycleTransition(f"Cannot complete an order in status {self.status.value}.")
        self._record_transition(OrderStatus.COMPLETED, at, reason="completed")
        return OrderCompleted(order_id=self.id)

    def cancel(self, reason: str, at: datetime) -> OrderCancelled:
        if self.status == OrderStatus.CANCELLED:
            raise OrderAlreadyCancelled("This order has already been cancelled.")
        if self.status == OrderStatus.COMPLETED:
            raise OrderAlreadyCompleted("A completed order cannot be cancelled directly -- use a Return instead.")
        if self.status in (OrderStatus.SHIPPED, OrderStatus.DELIVERED):
            raise OrderNotEligibleForCancellation(f"An order in status {self.status.value} is not eligible for direct cancellation -- use OrderCancellation's formal approval workflow.")
        self._record_transition(OrderStatus.CANCELLED, at, reason=reason)
        return OrderCancelled(order_id=self.id, reason=reason)

    def finalize_cancellation(self, reason: str, at: datetime) -> OrderCancelled:
        """The outcome of a completed OrderCancellation workflow that covered every line: unlike cancel(), this is allowed after shipping (the formal workflow is exactly what those orders must go through)."""
        if self.status in (OrderStatus.CANCELLED, OrderStatus.RETURNED, OrderStatus.FAILED, OrderStatus.DRAFT):
            raise InvalidOrderLifecycleTransition(f"Cannot cancel an order in status {self.status.value}.")
        if self.status == OrderStatus.COMPLETED:
            raise OrderAlreadyCompleted("A completed order cannot be cancelled -- use a Return instead.")
        self._record_transition(OrderStatus.CANCELLED, at, reason=reason)
        return OrderCancelled(order_id=self.id, reason=reason)

    def mark_returned(self, at: datetime, reason: str = "returned") -> None:
        """Every line has come back through OrderReturn: the order's own terminal outcome becomes RETURNED."""
        if self.status not in (OrderStatus.DELIVERED, OrderStatus.COMPLETED):
            raise InvalidOrderLifecycleTransition(f"Cannot mark an order in status {self.status.value} as returned.")
        self._record_transition(OrderStatus.RETURNED, at, reason=reason)

    def fail(self, reason, detail: str, at: datetime) -> OrderFailedEvent:
        if self.status not in _MUTABLE_STATUSES:
            raise InvalidOrderLifecycleTransition(f"Cannot mark an order in status {self.status.value} as failed.")
        self.failures.append(OrderFailure(id=uuid.uuid4(), reason=reason, detail=detail, occurred_at=at))
        self._record_transition(OrderStatus.FAILED, at, reason=detail)
        return OrderFailedEvent(order_id=self.id, reason=reason.value)

    # --- Line item cancel/return (structural bookkeeping only -- the return/cancellation WORKFLOW lives in OrderReturn/OrderCancellation) ---

    def mark_line_cancelled(self, line_item_id: uuid.UUID, quantity: int, at: datetime) -> LineItemCancelled:
        line = self.lines.get(line_item_id)
        if line is None:
            raise OrderLineItemNotFound(f"Order line item '{line_item_id}' not found.")
        if quantity > line.quantity:
            raise CancellationQuantityExceedsOrdered(f"Cannot cancel {quantity} units; only {line.quantity} were ordered.")
        if quantity == line.quantity:
            line.status = OrderLineItemStatus.CANCELLED
        self._bump_version()
        return LineItemCancelled(order_id=self.id, line_item_id=line_item_id, quantity=quantity)

    def mark_line_returned(self, line_item_id: uuid.UUID, quantity: int, at: datetime) -> LineItemReturned:
        line = self.lines.get(line_item_id)
        if line is None:
            raise OrderLineItemNotFound(f"Order line item '{line_item_id}' not found.")
        if quantity > line.quantity:
            raise ReturnQuantityExceedsOrdered(f"Cannot return {quantity} units; only {line.quantity} were ordered.")
        if quantity == line.quantity:
            line.status = OrderLineItemStatus.RETURNED
        self._bump_version()
        return LineItemReturned(order_id=self.id, line_item_id=line_item_id, quantity=quantity)

    # --- Payment / Fulfillment references -----------------------------------

    def attach_payment_reference(self, payment_id: uuid.UUID, amount: Money) -> PaymentReferenceAdded:
        ref = OrderPaymentReference(id=uuid.uuid4(), payment_id=payment_id, amount=amount)
        self.payment_references[ref.id] = ref
        self._bump_version()
        return PaymentReferenceAdded(order_id=self.id, payment_id=payment_id)

    def update_payment_status(self, payment_reference_id: uuid.UUID, status: PaymentReferenceStatus, at: datetime) -> PaymentStatusUpdated:
        ref = self.payment_references.get(payment_reference_id)
        if ref is None:
            raise PaymentReferenceNotFound(f"Payment reference '{payment_reference_id}' not found.")
        ref.status = status
        ref.processed_at = at
        self._bump_version()
        return PaymentStatusUpdated(order_id=self.id, payment_id=ref.payment_id, status=status.value)

    def attach_fulfillment_reference(self, fulfillment_id: uuid.UUID) -> FulfillmentReferenceAdded:
        ref = OrderFulfillmentReference(id=uuid.uuid4(), fulfillment_id=fulfillment_id)
        self.fulfillment_references[ref.id] = ref
        self._bump_version()
        return FulfillmentReferenceAdded(order_id=self.id, fulfillment_id=fulfillment_id)

    def update_fulfillment_status(self, fulfillment_reference_id: uuid.UUID, status: FulfillmentReferenceStatus, at: datetime, tracking_number: TrackingNumber | None = None) -> FulfillmentStatusUpdated:
        ref = self.fulfillment_references.get(fulfillment_reference_id)
        if ref is None:
            raise FulfillmentReferenceNotFound(f"Fulfillment reference '{fulfillment_reference_id}' not found.")
        ref.status = status
        if tracking_number is not None:
            ref.tracking_number = tracking_number
        if status == FulfillmentReferenceStatus.SHIPPED:
            ref.shipped_at = at
        if status == FulfillmentReferenceStatus.DELIVERED:
            ref.delivered_at = at
        self._bump_version()
        return FulfillmentStatusUpdated(order_id=self.id, fulfillment_id=ref.fulfillment_id, status=status.value)

    # --- Invoice ---------------------------------------------------------

    def issue_invoice(self, invoice_number: str, total_amount: Money, at: datetime) -> InvoiceIssued:
        if self.invoice is not None and self.invoice.status == InvoiceStatus.ISSUED:
            raise InvoiceAlreadyIssued("This order's invoice has already been issued.")
        invoice = OrderInvoice(id=uuid.uuid4(), invoice_number=invoice_number, total_amount=total_amount, status=InvoiceStatus.ISSUED, issued_at=at)
        self.invoice = invoice
        self._bump_version()
        return InvoiceIssued(order_id=self.id, invoice_id=invoice.id, invoice_number=invoice_number)

    # --- Lock / Archive (orthogonal to OrderStatus -- see OrderLockReason/is_archived field docs) ---

    def lock(self, reason: OrderLockReason) -> OrderLockedEvent:
        if self.lock_reason is not None:
            raise OrderAlreadyLocked("This order is already locked.")
        self.lock_reason = reason
        self._bump_version()
        return OrderLockedEvent(order_id=self.id, reason=reason.value)

    def unlock(self) -> OrderUnlocked:
        if self.lock_reason is None:
            raise OrderNotLocked("This order is not locked.")
        self.lock_reason = None
        self._bump_version()
        return OrderUnlocked(order_id=self.id)

    def archive(self) -> OrderArchivedEvent:
        """Archiving is an admin-only visibility flag orthogonal to OrderStatus -- it hides an old order from a default admin view without altering its real business status (unlike Cart's `archive()`, which IS a status transition, since carts are transient and orders are permanent business records)."""
        if self.is_archived:
            raise InvalidOrderArchivalTransition("This order is already archived.")
        self.is_archived = True
        self._bump_version()
        return OrderArchivedEvent(order_id=self.id)

    def restore(self) -> OrderRestored:
        if not self.is_archived:
            raise InvalidOrderArchivalTransition("This order is not archived.")
        self.is_archived = False
        self._bump_version()
        return OrderRestored(order_id=self.id)

    # --- Coupon reference / Address updates (both require the order still be modifiable) ---

    def apply_coupon_reference(self, coupon_id: uuid.UUID) -> None:
        self._assert_modifiable()
        self.coupon_ids.add(coupon_id)
        self._bump_version()

    def update_addresses(self, shipping_address: AddressSnapshot | None = None, billing_address: AddressSnapshot | None = None) -> None:
        self._assert_modifiable()
        if shipping_address is not None:
            self.shipping_address = shipping_address
        if billing_address is not None:
            self.billing_address = billing_address
        self._bump_version()

    def reattach_line_reservation(self, line_item_id: uuid.UUID, reservation_id: uuid.UUID) -> None:
        """Sets `reservation_id` on an existing line item -- for the rare re-attachment case (e.g. after a reservation was re-created following a stock transfer); the normal case is set at creation time via `create_from_cart_data()`."""
        line = self.lines.get(line_item_id)
        if line is None:
            raise OrderLineItemNotFound(f"Order line item '{line_item_id}' not found.")
        line.reservation_id = reservation_id
        self._bump_version()

    def reattach_line_price_snapshot(self, line_item_id: uuid.UUID, price_snapshot_id: uuid.UUID) -> None:
        """Same rationale as `reattach_line_reservation` -- for `price_snapshot_id`."""
        line = self.lines.get(line_item_id)
        if line is None:
            raise OrderLineItemNotFound(f"Order line item '{line_item_id}' not found.")
        line.price_snapshot_id = price_snapshot_id
        self._bump_version()


@dataclass(slots=True)
class OrderReturn:
    """Aggregate root -- independent lifecycle, references `order_id` by ID only."""

    id: uuid.UUID
    return_number: ReturnNumber
    order_id: uuid.UUID
    status: ReturnStatus = ReturnStatus.REQUESTED
    lines: dict[uuid.UUID, ReturnLineItem] = field(default_factory=dict)
    reason: ReturnReason = ReturnReason.OTHER
    refund_amount: Money | None = None
    requested_at: datetime | None = None
    approved_at: datetime | None = None
    received_at: datetime | None = None
    refunded_at: datetime | None = None

    def add_line(self, order_line_item_id: uuid.UUID, quantity: int) -> None:
        line = ReturnLineItem(id=uuid.uuid4(), order_line_item_id=order_line_item_id, quantity=quantity)
        self.lines[line.id] = line

    def approve(self, at: datetime) -> ReturnApproved:
        if self.status != ReturnStatus.REQUESTED:
            raise InvalidReturnLifecycleTransition(f"Cannot approve a return in status {self.status.value}.")
        self.status = ReturnStatus.APPROVED
        self.approved_at = at
        return ReturnApproved(return_id=self.id)

    def reject(self, reason: str, at: datetime) -> ReturnRejected:
        if self.status != ReturnStatus.REQUESTED:
            raise InvalidReturnLifecycleTransition(f"Cannot reject a return in status {self.status.value}.")
        self.status = ReturnStatus.REJECTED
        return ReturnRejected(return_id=self.id, reason=reason)

    def receive(self, at: datetime) -> ReturnReceived:
        if self.status != ReturnStatus.APPROVED:
            raise InvalidReturnLifecycleTransition(f"Cannot receive a return in status {self.status.value}.")
        self.status = ReturnStatus.RECEIVED
        self.received_at = at
        return ReturnReceived(return_id=self.id)

    def refund(self, amount: Money, at: datetime) -> ReturnRefunded:
        if self.status != ReturnStatus.RECEIVED:
            raise InvalidReturnLifecycleTransition(f"Cannot refund a return in status {self.status.value}.")
        self.status = ReturnStatus.REFUNDED
        self.refund_amount = amount
        self.refunded_at = at
        return ReturnRefunded(return_id=self.id, refund_amount=str(amount.amount))

    def assert_within_window(self, delivered_at: datetime, at: datetime, window: ReturnWindow = DEFAULT_RETURN_WINDOW) -> None:
        if not window.is_within_window(delivered_at, at):
            raise ReturnWindowExpired(f"The return window ({window.duration.days} days from delivery) has expired.")


@dataclass(slots=True)
class OrderCancellation:
    """Aggregate root -- independent, formal cancellation-approval lifecycle, distinct from `Order.cancel()`'s simpler immediate transition. References `order_id` by ID only."""

    id: uuid.UUID
    order_id: uuid.UUID
    status: CancellationStatus = CancellationStatus.REQUESTED
    lines: dict[uuid.UUID, CancellationLineItem] = field(default_factory=dict)
    reason: CancellationReason = CancellationReason.CUSTOMER_REQUEST
    refund_amount: Money | None = None
    requested_at: datetime | None = None
    approved_at: datetime | None = None
    completed_at: datetime | None = None

    def add_line(self, order_line_item_id: uuid.UUID, quantity: int) -> None:
        line = CancellationLineItem(id=uuid.uuid4(), order_line_item_id=order_line_item_id, quantity=quantity)
        self.lines[line.id] = line

    def approve(self, at: datetime) -> CancellationApproved:
        if self.status != CancellationStatus.REQUESTED:
            raise InvalidCancellationLifecycleTransition(f"Cannot approve a cancellation in status {self.status.value}.")
        self.status = CancellationStatus.APPROVED
        self.approved_at = at
        return CancellationApproved(cancellation_id=self.id)

    def reject(self, reason: str, at: datetime) -> CancellationRejected:
        if self.status != CancellationStatus.REQUESTED:
            raise InvalidCancellationLifecycleTransition(f"Cannot reject a cancellation in status {self.status.value}.")
        self.status = CancellationStatus.REJECTED
        return CancellationRejected(cancellation_id=self.id, reason=reason)

    def complete(self, refund_amount: Money | None, at: datetime) -> CancellationCompleted:
        if self.status != CancellationStatus.APPROVED:
            raise InvalidCancellationLifecycleTransition(f"Cannot complete a cancellation in status {self.status.value}.")
        self.status = CancellationStatus.COMPLETED
        self.refund_amount = refund_amount
        self.completed_at = at
        return CancellationCompleted(cancellation_id=self.id)
