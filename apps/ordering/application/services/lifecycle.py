"""
Order Lifecycle Application Services.
"""
from __future__ import annotations

import logging
import uuid

from django.db import transaction
from django.utils import timezone as django_timezone

from apps.ordering.application.ports import OrderRepository
from apps.ordering.application.services._shared import OrderingServiceContext
from apps.ordering.domain.aggregates import Order
from apps.ordering.domain.enums import OrderLockReason
from common.exceptions import ResourceNotFound

logger = logging.getLogger("nutrizone.app")


def stock_lines(order: Order) -> list[tuple]:
    """[(variant_id, qty)] for the order's active lines -- what location stock is reserved / shipped for."""
    return [(line.product_variant_id, line.quantity) for line in order.active_lines()]


class LoadOrder:
    def __init__(self, repo: OrderRepository) -> None:
        self._repo = repo

    def execute(self, order_id: uuid.UUID | None = None, order_number: str | None = None) -> Order:
        order = None
        if order_id:
            order = self._repo.get_by_id(order_id)
        elif order_number:
            order = self._repo.get_by_order_number(order_number)
        if order is None:
            raise ResourceNotFound("Order not found.")
        return order


class ConfirmOrder:
    def __init__(self, repo: OrderRepository, ctx: OrderingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, order_id: uuid.UUID) -> Order:
        order = self._repo.get_by_id(order_id)
        if order is None:
            raise ResourceNotFound("Order not found.")
        event = order.confirm(django_timezone.now())
        self._ctx.stamp_actor(order)
        saved = self._repo.save(order)
        if self._ctx.stock is not None:
            shortages = self._ctx.stock.reserve(order.order_number.value, stock_lines(order))
            if shortages:
                logger.warning("Order %s confirmed with stock shortages at the fulfilment warehouse: %s", order.order_number.value, shortages)
        self._ctx.stage_events([("OrderConfirmed", event.to_payload())])
        self._ctx.audit().updated(entity_type="Order", entity_id=str(order_id), before={}, after={"status": "confirmed"})
        self._ctx.invalidate_ordering_cache()
        return saved


class StartOrderProcessing:
    """Not explicitly named in this phase's brief, but 'Order.start_processing()' is a real domain method with no other Application Service reaching it -- added to close that gap, matching every prior module's precedent of adding small, justified, explicitly-flagged services."""

    def __init__(self, repo: OrderRepository, ctx: OrderingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, order_id: uuid.UUID) -> Order:
        order = self._repo.get_by_id(order_id)
        if order is None:
            raise ResourceNotFound("Order not found.")
        event = order.start_processing(django_timezone.now())
        self._ctx.stamp_actor(order)
        saved = self._repo.save(order)
        self._ctx.stage_events([("OrderProcessingStarted", event.to_payload())])
        self._ctx.audit().updated(entity_type="Order", entity_id=str(order_id), before={}, after={"status": "processing"})
        self._ctx.invalidate_ordering_cache()
        return saved


class ShipOrder:
    """Same rationale as StartOrderProcessing -- closes the gap for `Order.ship()`."""

    def __init__(self, repo: OrderRepository, ctx: OrderingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, order_id: uuid.UUID, store_id: uuid.UUID | None = None) -> Order:
        """`store_id`: the location the parcel leaves from (default: where its stock was reserved, else the main warehouse). Refuses -- and rolls the status back -- when that location doesn't have the units."""
        order = self._repo.get_by_id(order_id)
        if order is None:
            raise ResourceNotFound("Order not found.")
        event = order.ship(django_timezone.now())
        self._ctx.stamp_actor(order)
        saved = self._repo.save(order)
        if self._ctx.stock is not None:
            self._ctx.stock.ship(order.order_number.value, stock_lines(order), store_id)
        self._ctx.stage_events([("OrderShipped", event.to_payload())])
        self._ctx.audit().updated(entity_type="Order", entity_id=str(order_id), before={}, after={"status": "shipped"})
        self._ctx.invalidate_ordering_cache()
        return saved


class DeliverOrder:
    """Same rationale as StartOrderProcessing -- closes the gap for `Order.deliver()`."""

    def __init__(self, repo: OrderRepository, ctx: OrderingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, order_id: uuid.UUID) -> Order:
        order = self._repo.get_by_id(order_id)
        if order is None:
            raise ResourceNotFound("Order not found.")
        event = order.deliver(django_timezone.now())
        self._ctx.stamp_actor(order)
        saved = self._repo.save(order)
        self._ctx.stage_events([("OrderDelivered", event.to_payload())])
        self._ctx.audit().updated(entity_type="Order", entity_id=str(order_id), before={}, after={"status": "delivered"})
        self._ctx.invalidate_ordering_cache()
        return saved


class CompleteOrder:
    """Same rationale as StartOrderProcessing -- closes the gap for `Order.complete()`."""

    def __init__(self, repo: OrderRepository, ctx: OrderingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, order_id: uuid.UUID) -> Order:
        order = self._repo.get_by_id(order_id)
        if order is None:
            raise ResourceNotFound("Order not found.")
        event = order.complete(django_timezone.now())
        self._ctx.stamp_actor(order)
        saved = self._repo.save(order)
        self._ctx.stage_events([("OrderCompleted", event.to_payload())])
        self._ctx.audit().updated(entity_type="Order", entity_id=str(order_id), before={}, after={"status": "completed"})
        self._ctx.invalidate_ordering_cache()
        self._ctx.metric("orders_completed_total")
        return saved


class CancelOrder:
    def __init__(self, repo: OrderRepository, ctx: OrderingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, order_id: uuid.UUID, reason: str) -> Order:
        order = self._repo.get_by_id(order_id)
        if order is None:
            raise ResourceNotFound("Order not found.")
        event = order.cancel(reason, django_timezone.now())
        self._ctx.stamp_actor(order)
        saved = self._repo.save(order)
        if self._ctx.stock is not None:
            self._ctx.stock.release(order.order_number.value)
        self._ctx.stage_events([("OrderCancelled", {**event.to_payload(), "by_customer": self._ctx.by_customer})])
        self._ctx.audit().updated(entity_type="Order", entity_id=str(order_id), before={}, after={"status": "cancelled", "reason": reason})
        self._ctx.invalidate_ordering_cache()
        self._ctx.metric("orders_cancelled_total")
        return saved


class ExpireOrder:
    def __init__(self, repo: OrderRepository, ctx: OrderingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, order_id: uuid.UUID) -> Order:
        from apps.ordering.domain.enums import OrderFailureReason

        order = self._repo.get_by_id(order_id)
        if order is None:
            raise ResourceNotFound("Order not found.")
        event = order.fail(OrderFailureReason.SYSTEM_ERROR, "Order expired before payment was confirmed.", django_timezone.now())
        self._ctx.stamp_actor(order)
        saved = self._repo.save(order)
        if self._ctx.stock is not None:
            self._ctx.stock.release(order.order_number.value)
        self._ctx.stage_events([("OrderFailedEvent", event.to_payload())])
        self._ctx.audit().updated(entity_type="Order", entity_id=str(order_id), before={}, after={"status": "failed", "reason": "expired"})
        self._ctx.invalidate_ordering_cache()
        self._ctx.metric("orders_expired_total")
        return saved


class LockOrder:
    def __init__(self, repo: OrderRepository, ctx: OrderingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, order_id: uuid.UUID, reason: str) -> Order:
        order = self._repo.get_by_id(order_id)
        if order is None:
            raise ResourceNotFound("Order not found.")
        event = order.lock(OrderLockReason(reason))
        saved = self._repo.save(order)
        self._ctx.stage_events([("OrderLockedEvent", event.to_payload())])
        self._ctx.audit().updated(entity_type="Order", entity_id=str(order_id), before={}, after={"lock_reason": reason})
        self._ctx.invalidate_ordering_cache()
        return saved


class UnlockOrder:
    def __init__(self, repo: OrderRepository, ctx: OrderingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, order_id: uuid.UUID) -> Order:
        order = self._repo.get_by_id(order_id)
        if order is None:
            raise ResourceNotFound("Order not found.")
        event = order.unlock()
        saved = self._repo.save(order)
        self._ctx.stage_events([("OrderUnlocked", event.to_payload())])
        self._ctx.audit().updated(entity_type="Order", entity_id=str(order_id), before={}, after={"lock_reason": None})
        self._ctx.invalidate_ordering_cache()
        return saved


class ArchiveOrder:
    def __init__(self, repo: OrderRepository, ctx: OrderingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, order_id: uuid.UUID) -> Order:
        order = self._repo.get_by_id(order_id)
        if order is None:
            raise ResourceNotFound("Order not found.")
        event = order.archive()
        saved = self._repo.save(order)
        self._ctx.stage_events([("OrderArchivedEvent", event.to_payload())])
        self._ctx.audit().updated(entity_type="Order", entity_id=str(order_id), before={}, after={"is_archived": True})
        self._ctx.invalidate_ordering_cache()
        return saved


class RestoreOrder:
    def __init__(self, repo: OrderRepository, ctx: OrderingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, order_id: uuid.UUID) -> Order:
        order = self._repo.get_by_id(order_id)
        if order is None:
            raise ResourceNotFound("Order not found.")
        event = order.restore()
        saved = self._repo.save(order)
        self._ctx.stage_events([("OrderRestored", event.to_payload())])
        self._ctx.audit().updated(entity_type="Order", entity_id=str(order_id), before={}, after={"is_archived": False})
        self._ctx.invalidate_ordering_cache()
        return saved
