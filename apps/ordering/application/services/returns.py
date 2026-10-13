"""
Return Application Services -- backs the independent OrderReturn
aggregate's lifecycle.
"""
from __future__ import annotations

import uuid
from datetime import timezone as datetime_timezone
from decimal import Decimal

from django.db import transaction
from django.utils import timezone as django_timezone

from apps.ordering.application.ports import OrderRepository, OrderReturnRepository
from apps.ordering.application.services._shared import OrderingServiceContext
from apps.ordering.domain.aggregates import OrderReturn
from apps.ordering.domain.enums import OrderLineItemStatus, OrderStatus, ReturnReason, ReturnStatus
from apps.ordering.domain.value_objects import Money, ReturnNumber
from common.exceptions import BusinessRuleViolation, ResourceNotFound, ValidationFailed

RETURNABLE_ORDER_STATUSES = (OrderStatus.DELIVERED, OrderStatus.COMPLETED)
# Returns that still hold (or have consumed) a claim on the order's units; a rejected one frees them again.
_CLAIMING = (ReturnStatus.REQUESTED, ReturnStatus.APPROVED, ReturnStatus.RECEIVED, ReturnStatus.REFUNDED, ReturnStatus.CLOSED)


def rule(code: str, message: str, **details) -> BusinessRuleViolation:
    """A rejection with a stable machine code the dashboard / storefront can localise."""
    err = BusinessRuleViolation(message, details=details)
    err.code = code
    return err


def _default_order_repo():
    from apps.ordering.infrastructure.composition import build_order_repository

    return build_order_repository()


def delivered_at(order):
    return next((h.changed_at for h in reversed(order.status_history) if h.to_status == OrderStatus.DELIVERED.value), None)


def normalise_lines(order, lines: list[dict], taken: dict, verb: str) -> dict:
    """Validates [{order_line_item_id, quantity}] against the order: own lines, still active, quantity within what's left after `taken`. Returns {line_id: qty} (duplicates merged)."""
    wanted: dict = {}
    for raw in lines or []:
        try:
            line_id = uuid.UUID(str(raw["order_line_item_id"]))
            qty = int(raw["quantity"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationFailed("Each line needs order_line_item_id and a whole quantity.") from exc
        if qty <= 0:
            continue
        wanted[line_id] = wanted.get(line_id, 0) + qty
    if not wanted:
        raise rule("NO_LINES", f"Choose at least one item to {verb}.")
    for line_id, qty in wanted.items():
        line = order.lines.get(line_id)
        if line is None or line.status != OrderLineItemStatus.ACTIVE:
            raise rule("LINE_NOT_IN_ORDER", "This item is not an active line of the order.", line_id=str(line_id))
        left = line.quantity - taken.get(line_id, 0)
        if qty > left:
            raise rule("QUANTITY_EXCEEDS_REMAINING", f"Only {max(left, 0)} unit(s) of this item can still be {verb}ed.", line_id=str(line_id), remaining=max(left, 0))
    return wanted


def returned_units(returns, statuses=_CLAIMING, exclude_id=None) -> dict:
    out: dict = {}
    for r in returns:
        if r.id == exclude_id or r.status not in statuses:
            continue
        for line in r.lines.values():
            out[line.order_line_item_id] = out.get(line.order_line_item_id, 0) + line.quantity
    return out


def paid_total(order) -> Decimal:
    """What the customer actually paid for this order. Captured payment references when there are any; a cash-on-delivery order (no references at all) paid its non-cancelled lines on delivery. Line discounts already include coupons and coins, so this is real money."""
    from apps.ordering.domain.enums import PaymentReferenceStatus

    refs = list(order.payment_references.values())
    if refs:
        return sum((ref.amount.amount for ref in refs if ref.status == PaymentReferenceStatus.CAPTURED), Decimal("0"))
    if delivered_at(order) is None:
        return Decimal("0")
    return sum((l.unit_price.amount * l.quantity - l.discount_amount.amount + l.tax_amount.amount for l in order.lines.values() if l.status != OrderLineItemStatus.CANCELLED), Decimal("0"))


def _generate_return_number() -> str:
    return f"RET-{uuid.uuid4().hex[:10].upper()}"


class RequestReturn:
    def __init__(self, return_repo: OrderReturnRepository, order_repo: OrderRepository, ctx: OrderingServiceContext) -> None:
        self._return_repo = return_repo
        self._order_repo = order_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, order_id: uuid.UUID, reason: str, lines: list[dict], enforce_window: bool = True) -> OrderReturn:
        """Only a delivered order, only its own active lines, never more units than are left after earlier (non-rejected) returns, and -- unless a staff member overrides it -- within the return window."""
        order = self._order_repo.get_by_id(order_id)
        if order is None:
            raise ResourceNotFound("Order not found.")
        if order.status not in RETURNABLE_ORDER_STATUSES:
            raise rule("ORDER_NOT_RETURNABLE", f"Only a delivered order can be returned (current status: {order.status.value}).", status=order.status.value)
        try:
            reason_value = ReturnReason(reason)
        except ValueError as exc:
            raise ValidationFailed("Unknown return reason.") from exc
        now = django_timezone.now()
        delivered = delivered_at(order)
        order_return = OrderReturn(id=uuid.uuid4(), return_number=ReturnNumber(_generate_return_number()), order_id=order_id, reason=reason_value, requested_at=now)
        if enforce_window and delivered is not None:
            from apps.ordering.domain.exceptions import ReturnWindowExpired

            if django_timezone.is_naive(delivered):
                delivered = django_timezone.make_aware(delivered, datetime_timezone.utc)
            try:
                order_return.assert_within_window(delivered, now)
            except ReturnWindowExpired as exc:
                raise rule("RETURN_WINDOW_EXPIRED", str(exc)) from exc
        wanted = normalise_lines(order, lines, returned_units(self._return_repo.list_for_order(order_id)), "return")
        for line_id, qty in wanted.items():
            order_return.add_line(line_id, qty)

        saved = self._return_repo.save(order_return)
        self._ctx.stage_events([("ReturnRequested", {"return_id": str(saved.id), "order_id": str(order_id), "by_customer": self._ctx.by_customer})])
        self._ctx.audit().created(entity_type="OrderReturn", entity_id=str(saved.id), after={"order_id": str(order_id), "reason": reason})
        self._ctx.invalidate_ordering_cache()
        return saved


class ApproveReturn:
    def __init__(self, repo: OrderReturnRepository, ctx: OrderingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, return_id: uuid.UUID) -> OrderReturn:
        order_return = self._repo.get_by_id(return_id)
        if order_return is None:
            raise ResourceNotFound("Return not found.")
        event = order_return.approve(django_timezone.now())
        saved = self._repo.save(order_return)
        self._ctx.stage_events([("ReturnApproved", event.to_payload())])
        self._ctx.audit().updated(entity_type="OrderReturn", entity_id=str(return_id), before={}, after={"status": "approved"})
        self._ctx.invalidate_ordering_cache()
        return saved


class RejectReturn:
    def __init__(self, repo: OrderReturnRepository, ctx: OrderingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, return_id: uuid.UUID, reason: str) -> OrderReturn:
        order_return = self._repo.get_by_id(return_id)
        if order_return is None:
            raise ResourceNotFound("Return not found.")
        event = order_return.reject(reason, django_timezone.now())
        saved = self._repo.save(order_return)
        if hasattr(self._repo, "set_rejection_reason"):
            self._repo.set_rejection_reason(return_id, reason)
        self._ctx.stage_events([("ReturnRejected", event.to_payload())])
        self._ctx.audit().updated(entity_type="OrderReturn", entity_id=str(return_id), before={}, after={"status": "rejected", "reason": reason})
        self._ctx.invalidate_ordering_cache()
        return saved


class ReceiveReturn:
    """The goods are back: the order's fully-returned lines become RETURNED, the order itself RETURNED once nothing is left active (which also reverses its coins via loyalty), and -- when `restock` -- the units go back on the shelf they were shipped from."""

    def __init__(self, repo: OrderReturnRepository, ctx: OrderingServiceContext, order_repo: OrderRepository | None = None) -> None:
        self._repo = repo
        self._ctx = ctx
        self._order_repo = order_repo

    @transaction.atomic
    def execute(self, return_id: uuid.UUID, restock: bool = True) -> OrderReturn:
        order_return = self._repo.get_by_id(return_id)
        if order_return is None:
            raise ResourceNotFound("Return not found.")
        now = django_timezone.now()
        event = order_return.receive(now)
        saved = self._repo.save(order_return)

        order_repo = self._order_repo or _default_order_repo()
        order = order_repo.get_by_id(order_return.order_id)
        if order is not None:
            back = returned_units(self._repo.list_for_order(order.id), statuses=(ReturnStatus.RECEIVED, ReturnStatus.REFUNDED, ReturnStatus.CLOSED))
            for line_id, units in back.items():
                line = order.lines.get(line_id)
                if line is not None and line.status == OrderLineItemStatus.ACTIVE and units >= line.quantity:
                    order.mark_line_returned(line_id, line.quantity, now)
            if not order.active_lines() and order.status in RETURNABLE_ORDER_STATUSES:
                order.mark_returned(now, reason=f"return {order_return.return_number.value}")
                self._ctx.stamp_actor(order)
            order_repo.save(order)
            if restock and self._ctx.stock is not None:
                by_variant: dict = {}
                for line in order_return.lines.values():
                    order_line = order.lines.get(line.order_line_item_id)
                    if order_line is not None:
                        by_variant[order_line.product_variant_id] = by_variant.get(order_line.product_variant_id, 0) + line.quantity
                self._ctx.stock.restock(order.order_number.value, list(by_variant.items()))

        self._ctx.stage_events([("ReturnReceived", event.to_payload())])
        self._ctx.audit().updated(entity_type="OrderReturn", entity_id=str(return_id), before={}, after={"status": "received", "restocked": restock})
        self._ctx.invalidate_ordering_cache()
        return saved


class RefundReturn:
    """
    `amount` was previously accepted without any cross-check against
    the order's own actual paid total -- a confirmed, real financial-
    integrity gap (Phase 03A final closure): nothing prevented a
    refund exceeding what was ever captured for the order. Fixed by
    computing the order's own paid total (sum of its CAPTURED
    `OrderPaymentReference`s) minus any prior refunds already issued
    for the same order (summing this return's own sibling
    `OrderReturn` records still in `REFUNDED` status), and rejecting
    if the new refund would exceed what remains.
    """

    def __init__(self, repo: OrderReturnRepository, ctx: OrderingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, return_id: uuid.UUID, amount: Decimal, currency: str) -> OrderReturn:
        order_return = self._repo.get_by_id(return_id)
        if order_return is None:
            raise ResourceNotFound("Return not found.")

        from apps.ordering.infrastructure.composition import build_order_repository

        order = build_order_repository().get_by_id(order_return.order_id)
        if order is not None:
            paid = paid_total(order)
            sibling_returns = self._repo.list_for_order(order_return.order_id)
            already_refunded = sum(
                (r.refund_amount.amount for r in sibling_returns if r.id != order_return.id and r.status == ReturnStatus.REFUNDED and r.refund_amount is not None),
                Decimal("0"),
            )
            remaining_refundable = paid - already_refunded
            if amount > remaining_refundable:
                raise ValidationFailed(f"Refund amount {amount} exceeds the remaining refundable amount {remaining_refundable} for this order.")

        event = order_return.refund(Money(amount=amount, currency=currency), django_timezone.now())
        saved = self._repo.save(order_return)
        self._ctx.stage_events([("ReturnRefunded", event.to_payload())])
        self._ctx.audit().updated(entity_type="OrderReturn", entity_id=str(return_id), before={}, after={"status": "refunded", "refund_amount": str(amount)})
        self._ctx.invalidate_ordering_cache()
        self._ctx.metric("returns_refunded_total")
        return saved


class GetReturn:
    def __init__(self, repo: OrderReturnRepository) -> None:
        self._repo = repo

    def execute(self, return_id: uuid.UUID) -> OrderReturn:
        order_return = self._repo.get_by_id(return_id)
        if order_return is None:
            raise ResourceNotFound("Return not found.")
        return order_return


class ListReturnsForOrder:
    def __init__(self, repo: OrderReturnRepository) -> None:
        self._repo = repo

    def execute(self, order_id: uuid.UUID) -> list[OrderReturn]:
        return self._repo.list_for_order(order_id)
