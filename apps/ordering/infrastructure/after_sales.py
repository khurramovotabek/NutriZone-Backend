"""
Customer self-service after an order is placed: cancel it, or ask for a return.

  * pending_payment / confirmed  -> cancelled immediately (CancelOrder: reserved stock released, coins returned).
  * processing / shipped         -> a cancellation *request* (OrderCancellation) the store approves in the dashboard.
  * delivered / completed        -> a return request (OrderReturn), within the return window.

Only the order's own customer may do any of this; every step goes through the Application Services
with the production context (stock + outbox), with the customer as the actor.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from django.db.models import Sum

from apps.ordering.infrastructure import models as orm
from common.exceptions import BusinessRuleViolation, ResourceNotFound
from common.exceptions import PermissionDenied as DomainPermissionDenied

RETURN_WINDOW_DAYS = 14
INSTANT_CANCEL = ("pending_payment", "confirmed")
REQUEST_CANCEL = ("processing", "shipped")
RETURNABLE = ("delivered", "completed")
CUSTOMER_CANCEL_REASONS = ("customer_request", "other")
CUSTOMER_COMMENT_PREFIX = "Customer: "


def _rule(code: str, message: str) -> BusinessRuleViolation:
    err = BusinessRuleViolation(message)
    err.code = code
    return err


def own_order(order_number: str, user_id) -> orm.OrderModel:
    order = orm.OrderModel.objects.filter(order_number=order_number).first()
    if order is None:
        raise ResourceNotFound("Order not found.")
    if user_id is None or str(order.customer_id) != str(user_id):
        raise DomainPermissionDenied("You can only manage your own orders.")
    return order


def _delivered_at(order: orm.OrderModel):
    return order.status_history.filter(to_status="delivered").order_by("-changed_at").values_list("changed_at", flat=True).first()


def _open_cancellation(order: orm.OrderModel):
    return orm.OrderCancellationModel.objects.filter(order_id=order.id, status__in=("requested", "approved")).first()


def snapshot(order: orm.OrderModel) -> dict:
    from django.utils import timezone

    claimed = {
        row["order_line_item_id"]: row["n"]
        for row in orm.ReturnLineItemModel.objects.filter(order_return__order_id=order.id).exclude(order_return__status="rejected").values("order_line_item_id").annotate(n=Sum("quantity"))
    }
    delivered = _delivered_at(order)
    deadline = delivered + timedelta(days=RETURN_WINDOW_DAYS) if delivered else None
    expired = bool(deadline and timezone.now() > deadline)
    lines = [
        {"id": str(l.id), "product_variant_id": str(l.product_variant_id), "quantity": l.quantity, "returnable": max(l.quantity - claimed.get(l.id, 0), 0) if l.status == "active" else 0}
        for l in order.lines.all()
    ]
    pending = _open_cancellation(order)
    if order.status in INSTANT_CANCEL:
        can_cancel = "now"
    elif order.status in REQUEST_CANCEL and pending is None:
        can_cancel = "request"
    else:
        can_cancel = None

    def items(model_lines):
        return [{"order_line_item_id": str(i.order_line_item_id), "quantity": i.quantity} for i in model_lines.all()]

    return {
        "order_number": order.order_number, "status": order.status,
        "can_cancel": can_cancel, "cancel_pending": pending is not None,
        "can_return": order.status in RETURNABLE and not expired and any(l["returnable"] for l in lines),
        "return_deadline": deadline.isoformat() if deadline else None, "return_window_expired": expired,
        "lines": lines,
        "returns": [
            {"number": r.return_number, "status": r.status, "reason": r.reason, "created_at": r.created_at.isoformat(),
             "refund_amount": str(r.refund_amount) if r.refund_amount is not None else None, "items": items(r.lines),
             "rejection_reason": r.rejection_reason if r.status == "rejected" else ""}
            for r in orm.OrderReturnModel.objects.filter(order_id=order.id).order_by("-created_at").prefetch_related("lines")
        ],
        "cancellations": [
            {"status": c.status, "reason": c.reason, "created_at": c.created_at.isoformat(), "items": items(c.lines),
             "rejection_reason": c.rejection_reason if c.status == "rejected" else ""}
            for c in orm.OrderCancellationModel.objects.filter(order_id=order.id).order_by("-created_at").prefetch_related("lines")
        ],
        "reasons": {"cancel": list(CUSTOMER_CANCEL_REASONS), "return": [r for r in ("defective", "wrong_item", "not_as_described", "damaged_in_transit", "changed_mind", "other")]},
    }


def _note(text: str) -> str:
    text = (text or "").strip()[:1000]
    return f"{CUSTOMER_COMMENT_PREFIX}{text}" if text else ""


def cancel(order: orm.OrderModel, user_id: uuid.UUID, reason: str, comment: str = "") -> str:
    """Returns "cancelled" (done) or "requested" (waiting for the store)."""
    from apps.ordering.application.services.cancellations import RequestCancellation
    from apps.ordering.application.services.lifecycle import CancelOrder
    from apps.ordering.infrastructure.composition import build_ordering_service_context
    from apps.ordering.infrastructure.repositories import DjangoOrderCancellationRepository, DjangoOrderRepository

    reason = reason if reason in CUSTOMER_CANCEL_REASONS else "customer_request"
    ctx = build_ordering_service_context(actor_id=user_id)
    if order.status in INSTANT_CANCEL:
        CancelOrder(DjangoOrderRepository(), ctx).execute(order.id, reason=f"cancellation:{reason}")
        note = _note(comment)
        if note:
            orm.OrderModel.objects.filter(pk=order.pk).update(note=f"{order.note}\n{note}" if order.note else note)
        return "cancelled"
    if order.status in REQUEST_CANCEL:
        if _open_cancellation(order) is not None:
            raise _rule("CANCELLATION_PENDING", "A cancellation request for this order is already waiting for the store.")
        created = RequestCancellation(DjangoOrderCancellationRepository(), DjangoOrderRepository(), ctx).execute(order.id, reason=reason, lines=None)
        orm.OrderCancellationModel.objects.filter(pk=created.id).update(note=_note(comment))
        return "requested"
    if order.status in RETURNABLE:
        raise _rule("ORDER_DELIVERED_USE_RETURN", "This order is already delivered -- ask for a return instead.")
    raise _rule("ORDER_NOT_CANCELLABLE", "This order can no longer be cancelled.")


def request_return(order: orm.OrderModel, user_id: uuid.UUID, reason: str, lines: list[dict], comment: str = "") -> str:
    from apps.ordering.application.services.returns import RequestReturn
    from apps.ordering.infrastructure.composition import build_ordering_service_context
    from apps.ordering.infrastructure.repositories import DjangoOrderRepository, DjangoOrderReturnRepository

    created = RequestReturn(DjangoOrderReturnRepository(), DjangoOrderRepository(), build_ordering_service_context(actor_id=user_id)).execute(
        order.id, reason=reason, lines=lines, enforce_window=True,
    )
    orm.OrderReturnModel.objects.filter(pk=created.id).update(note=_note(comment))
    return created.return_number.value
