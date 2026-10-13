"""
Cancellation Application Services -- backs the independent
OrderCancellation aggregate's formal approval workflow (distinct from
`CancelOrder` in lifecycle.py, which triggers Order's own simpler,
immediately-effective `cancel()` transition for orders that haven't
shipped yet).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone as django_timezone

from apps.ordering.application.ports import OrderCancellationRepository, OrderRepository
from apps.ordering.application.services._shared import OrderingServiceContext
from apps.ordering.domain.aggregates import OrderCancellation
from apps.ordering.application.services.returns import _default_order_repo, normalise_lines, rule
from apps.ordering.domain.enums import CancellationReason, CancellationStatus, OrderLineItemStatus, OrderStatus
from apps.ordering.domain.value_objects import Money
from common.exceptions import ResourceNotFound, ValidationFailed

# A delivered order goes through a Return instead; terminal orders can't be cancelled at all.
CANCELLABLE_ORDER_STATUSES = (OrderStatus.PENDING_PAYMENT, OrderStatus.CONFIRMED, OrderStatus.PROCESSING, OrderStatus.SHIPPED)
_CLAIMING = (CancellationStatus.REQUESTED, CancellationStatus.APPROVED, CancellationStatus.COMPLETED)


def cancelled_units(cancellations, statuses=_CLAIMING) -> dict:
    out: dict = {}
    for c in cancellations:
        if c.status not in statuses:
            continue
        for line in c.lines.values():
            out[line.order_line_item_id] = out.get(line.order_line_item_id, 0) + line.quantity
    return out


class RequestCancellation:
    def __init__(self, cancellation_repo: OrderCancellationRepository, order_repo: OrderRepository, ctx: OrderingServiceContext) -> None:
        self._cancellation_repo = cancellation_repo
        self._order_repo = order_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, order_id: uuid.UUID, reason: str, lines: list[dict] | None = None) -> OrderCancellation:
        """`lines` empty/None = the whole order (every unit not already claimed by another cancellation)."""
        order = self._order_repo.get_by_id(order_id)
        if order is None:
            raise ResourceNotFound("Order not found.")
        if order.status not in CANCELLABLE_ORDER_STATUSES:
            code = "ORDER_DELIVERED_USE_RETURN" if order.status in (OrderStatus.DELIVERED, OrderStatus.COMPLETED) else "ORDER_NOT_CANCELLABLE"
            raise rule(code, f"An order in status {order.status.value} can't be cancelled.", status=order.status.value)
        try:
            reason_value = CancellationReason(reason)
        except ValueError as exc:
            raise ValidationFailed("Unknown cancellation reason.") from exc
        taken = cancelled_units(self._cancellation_repo.list_for_order(order_id))
        if not lines:
            lines = [{"order_line_item_id": l.id, "quantity": l.quantity - taken.get(l.id, 0)} for l in order.active_lines()]
        wanted = normalise_lines(order, lines, taken, "cancel")

        now = django_timezone.now()
        cancellation = OrderCancellation(id=uuid.uuid4(), order_id=order_id, reason=reason_value, requested_at=now)
        for line_id, qty in wanted.items():
            cancellation.add_line(line_id, qty)

        saved = self._cancellation_repo.save(cancellation)
        self._ctx.stage_events([("CancellationRequested", {"cancellation_id": str(saved.id), "order_id": str(order_id), "by_customer": self._ctx.by_customer})])
        self._ctx.audit().created(entity_type="OrderCancellation", entity_id=str(saved.id), after={"order_id": str(order_id), "reason": reason})
        self._ctx.invalidate_ordering_cache()
        return saved


class ApproveCancellation:
    def __init__(self, repo: OrderCancellationRepository, ctx: OrderingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, cancellation_id: uuid.UUID) -> OrderCancellation:
        cancellation = self._repo.get_by_id(cancellation_id)
        if cancellation is None:
            raise ResourceNotFound("Cancellation not found.")
        event = cancellation.approve(django_timezone.now())
        saved = self._repo.save(cancellation)
        self._ctx.stage_events([("CancellationApproved", event.to_payload())])
        self._ctx.audit().updated(entity_type="OrderCancellation", entity_id=str(cancellation_id), before={}, after={"status": "approved"})
        self._ctx.invalidate_ordering_cache()
        return saved


class RejectCancellation:
    def __init__(self, repo: OrderCancellationRepository, ctx: OrderingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, cancellation_id: uuid.UUID, reason: str) -> OrderCancellation:
        cancellation = self._repo.get_by_id(cancellation_id)
        if cancellation is None:
            raise ResourceNotFound("Cancellation not found.")
        event = cancellation.reject(reason, django_timezone.now())
        saved = self._repo.save(cancellation)
        if hasattr(self._repo, "set_rejection_reason"):
            self._repo.set_rejection_reason(cancellation_id, reason)
        self._ctx.stage_events([("CancellationRejected", event.to_payload())])
        self._ctx.audit().updated(entity_type="OrderCancellation", entity_id=str(cancellation_id), before={}, after={"status": "rejected", "reason": reason})
        self._ctx.invalidate_ordering_cache()
        return saved


class CompleteCancellation:
    """Carries the approved cancellation out on the order: fully-cancelled lines become CANCELLED, the order CANCELLED once nothing is left active (coins are then returned by loyalty), reserved stock is released -- or, if the parcel had already left, the units are put back."""

    def __init__(self, repo: OrderCancellationRepository, ctx: OrderingServiceContext, order_repo: OrderRepository | None = None) -> None:
        self._repo = repo
        self._ctx = ctx
        self._order_repo = order_repo

    @transaction.atomic
    def execute(self, cancellation_id: uuid.UUID, refund_amount: Decimal | None = None, currency: str = "UZS") -> OrderCancellation:
        cancellation = self._repo.get_by_id(cancellation_id)
        if cancellation is None:
            raise ResourceNotFound("Cancellation not found.")
        now = django_timezone.now()
        amount = Money(amount=refund_amount, currency=currency) if refund_amount is not None else None
        event = cancellation.complete(amount, now)
        saved = self._repo.save(cancellation)

        order_repo = self._order_repo or _default_order_repo()
        order = order_repo.get_by_id(cancellation.order_id)
        if order is not None:
            done = cancelled_units(self._repo.list_for_order(order.id), statuses=(CancellationStatus.COMPLETED,))
            by_variant: dict = {}
            for line in cancellation.lines.values():
                order_line = order.lines.get(line.order_line_item_id)
                if order_line is not None:
                    by_variant[order_line.product_variant_id] = by_variant.get(order_line.product_variant_id, 0) + line.quantity
            for line_id, units in done.items():
                line = order.lines.get(line_id)
                if line is not None and line.status == OrderLineItemStatus.ACTIVE and units >= line.quantity:
                    order.mark_line_cancelled(line_id, line.quantity, now)
            if not order.active_lines() and order.status not in (OrderStatus.CANCELLED, OrderStatus.RETURNED, OrderStatus.FAILED):
                order.finalize_cancellation(f"cancellation:{cancellation.reason.value}", now)
                self._ctx.stamp_actor(order)
            order_repo.save(order)
            if self._ctx.stock is not None and by_variant:
                number = order.order_number.value
                if self._ctx.stock.has_shipped(number):
                    self._ctx.stock.restock(number, list(by_variant.items()))
                else:
                    self._ctx.stock.release(number, list(by_variant.items()))

        self._ctx.stage_events([("CancellationCompleted", event.to_payload())])
        self._ctx.audit().updated(entity_type="OrderCancellation", entity_id=str(cancellation_id), before={}, after={"status": "completed"})
        self._ctx.invalidate_ordering_cache()
        self._ctx.metric("cancellations_completed_total")
        return saved


class GetCancellation:
    def __init__(self, repo: OrderCancellationRepository) -> None:
        self._repo = repo

    def execute(self, cancellation_id: uuid.UUID) -> OrderCancellation:
        cancellation = self._repo.get_by_id(cancellation_id)
        if cancellation is None:
            raise ResourceNotFound("Cancellation not found.")
        return cancellation


class ListCancellationsForOrder:
    def __init__(self, repo: OrderCancellationRepository) -> None:
        self._repo = repo

    def execute(self, order_id: uuid.UUID) -> list[OrderCancellation]:
        return self._repo.list_for_order(order_id)
