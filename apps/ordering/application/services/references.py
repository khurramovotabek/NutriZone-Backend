"""
Reference Application Services: AttachShipment (-> Fulfillment
reference), AttachReservation (bound to a specific line item's
already-recorded reservation_id -- see note below), AttachPriceSnapshot
(same), AttachCoupon, UpdateAddress.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone as django_timezone

from apps.ordering.application.ports import OrderRepository
from apps.ordering.application.services._shared import OrderingServiceContext
from apps.ordering.domain.aggregates import Order
from apps.ordering.domain.enums import OrderStatus, PaymentReferenceStatus
from apps.ordering.domain.value_objects import AddressSnapshot, Money
from common.exceptions import ResourceNotFound


class AttachShipment:
    """Backs 'AttachShipment' -- records a cross-module reference to a fulfillment/shipment tracked by a future Fulfillment module via `Order.attach_fulfillment_reference()`."""

    def __init__(self, repo: OrderRepository, ctx: OrderingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, order_id: uuid.UUID, fulfillment_id: uuid.UUID) -> Order:
        order = self._repo.get_by_id(order_id)
        if order is None:
            raise ResourceNotFound("Order not found.")
        event = order.attach_fulfillment_reference(fulfillment_id)
        saved = self._repo.save(order)
        self._ctx.stage_events([("FulfillmentReferenceAdded", event.to_payload())])
        self._ctx.audit().updated(entity_type="Order", entity_id=str(order_id), before={}, after={"fulfillment_id": str(fulfillment_id)})
        self._ctx.invalidate_ordering_cache()
        return saved


class AttachPaymentReference:
    """Not explicitly named in this phase's brief by this exact name, but 'AttachShipment' has an obvious payment-side counterpart with no other service reaching `Order.attach_payment_reference()` -- added to close that gap, following the same precedent as StartOrderProcessing/ShipOrder/DeliverOrder/CompleteOrder."""

    def __init__(self, repo: OrderRepository, ctx: OrderingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, order_id: uuid.UUID, payment_id: uuid.UUID, amount: Decimal) -> Order:
        order = self._repo.get_by_id(order_id)
        if order is None:
            raise ResourceNotFound("Order not found.")
        event = order.attach_payment_reference(payment_id, Money(amount=amount, currency=order.currency))
        saved = self._repo.save(order)
        self._ctx.stage_events([("PaymentReferenceAdded", event.to_payload())])
        self._ctx.audit().updated(entity_type="Order", entity_id=str(order_id), before={}, after={"payment_id": str(payment_id)})
        self._ctx.invalidate_ordering_cache()
        return saved


class UpdatePaymentStatus:
    """
    Closes a real, confirmed gap: `Order.update_payment_status()`
    existed with zero Application Service callers before Phase 02E.
    Also the Payment -> Order boundary (Phase 02E, Step 9): a
    transition to CAPTURED triggers `Order.confirm()` -- but only if
    the order is still genuinely in PENDING_PAYMENT. An order already
    past that status (already confirmed by an earlier, different
    payment reference reaching CAPTURED first) is left alone rather
    than raising `InvalidOrderLifecycleTransition` -- the payment
    status update itself is still recorded, but confirming an
    already-confirmed order is a no-op here, not an error, since the
    underlying business fact ("this order's payment succeeded") is
    still true and idempotent from the caller's perspective.
    """

    def __init__(self, repo: OrderRepository, ctx: OrderingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, order_id: uuid.UUID, payment_reference_id: uuid.UUID, status) -> Order:
        order = self._repo.get_by_id(order_id)
        if order is None:
            raise ResourceNotFound("Order not found.")
        event = order.update_payment_status(payment_reference_id, status, django_timezone.now())
        confirmed_now = False
        if status == PaymentReferenceStatus.CAPTURED and order.status == OrderStatus.PENDING_PAYMENT:
            order.confirm(django_timezone.now())
            confirmed_now = True
        saved = self._repo.save(order)
        self._ctx.stage_events([("PaymentStatusUpdated", event.to_payload())])
        if confirmed_now:
            self._ctx.stage_events([("OrderConfirmed", {"order_id": str(order_id)})])
        self._ctx.audit().updated(entity_type="Order", entity_id=str(order_id), before={}, after={"payment_reference_id": str(payment_reference_id), "status": status.value})
        self._ctx.invalidate_ordering_cache()
        return saved


class AttachReservation:
    """
    Backs 'AttachReservation' -- unlike Cart's identically-named
    service (which attaches to a mutable cart item pre-checkout),
    Order's line items are frozen once created, so this sets the
    `reservation_id` field directly on an existing `OrderLineItem`
    (a simple field assignment, not a domain state-transition method
    -- Order's line items don't have a dedicated `attach_reservation()`
    aggregate method since a reservation reference is establishded at
    creation time via `CreateOrderFromCart`; this service exists for
    the rarer case of re-attaching after a reservation was re-created
    following a stock-transfer).
    """

    def __init__(self, repo: OrderRepository, ctx: OrderingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, order_id: uuid.UUID, line_item_id: uuid.UUID, reservation_id: uuid.UUID) -> Order:
        order = self._repo.get_by_id(order_id)
        if order is None:
            raise ResourceNotFound("Order not found.")
        order.reattach_line_reservation(line_item_id, reservation_id)
        saved = self._repo.save(order)
        self._ctx.audit().updated(entity_type="Order", entity_id=str(order_id), before={}, after={"line_item_id": str(line_item_id), "reservation_id": str(reservation_id)})
        self._ctx.invalidate_ordering_cache()
        return saved


class AttachPriceSnapshot:
    """Same rationale as AttachReservation -- sets `price_snapshot_id` on an existing OrderLineItem for the rare re-attachment case."""

    def __init__(self, repo: OrderRepository, ctx: OrderingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, order_id: uuid.UUID, line_item_id: uuid.UUID, price_snapshot_id: uuid.UUID) -> Order:
        order = self._repo.get_by_id(order_id)
        if order is None:
            raise ResourceNotFound("Order not found.")
        order.reattach_line_price_snapshot(line_item_id, price_snapshot_id)
        saved = self._repo.save(order)
        self._ctx.audit().updated(entity_type="Order", entity_id=str(order_id), before={}, after={"line_item_id": str(line_item_id), "price_snapshot_id": str(price_snapshot_id)})
        self._ctx.invalidate_ordering_cache()
        return saved


class AttachCoupon:
    def __init__(self, repo: OrderRepository, ctx: OrderingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, order_id: uuid.UUID, coupon_id: uuid.UUID) -> Order:
        order = self._repo.get_by_id(order_id)
        if order is None:
            raise ResourceNotFound("Order not found.")
        order.apply_coupon_reference(coupon_id)
        saved = self._repo.save(order)
        self._ctx.audit().updated(entity_type="Order", entity_id=str(order_id), before={}, after={"coupon_id": str(coupon_id)})
        self._ctx.invalidate_ordering_cache()
        return saved


class UpdateAddress:
    def __init__(self, repo: OrderRepository, ctx: OrderingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, order_id: uuid.UUID, shipping_address: dict | None = None, billing_address: dict | None = None) -> Order:
        order = self._repo.get_by_id(order_id)
        if order is None:
            raise ResourceNotFound("Order not found.")
        order.update_addresses(
            shipping_address=AddressSnapshot(**shipping_address) if shipping_address is not None else None,
            billing_address=AddressSnapshot(**billing_address) if billing_address is not None else None,
        )
        saved = self._repo.save(order)
        self._ctx.audit().updated(entity_type="Order", entity_id=str(order_id), before={}, after={"shipping_address_changed": shipping_address is not None, "billing_address_changed": billing_address is not None})
        self._ctx.invalidate_ordering_cache()
        return saved
