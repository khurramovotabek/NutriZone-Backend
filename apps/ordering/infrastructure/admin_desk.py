"""
Order desk -- the data and actions behind the premium Ordering admin pages
(templates/admin/ordering/{ordermodel,orderreturnmodel,ordercancellationmodel}/).

Every state change goes through an Application Service with the production context
(outbox events, location stock, actor stamping); nothing here writes a status by hand.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.utils.translation import get_language
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.ordering.infrastructure import models as orm

# (label, colour, icon) per workflow status / reason
RETURN_STATUS = {
    "requested": (gettext_lazy("Requested"), "#f59e0b", "fa-inbox"),
    "approved": (gettext_lazy("Approved"), "#6366f1", "fa-circle-check"),
    "received": (gettext_lazy("Received"), "#0ea5e9", "fa-box"),
    "refunded": (gettext_lazy("Money refunded"), "#10b981", "fa-money-bill-wave"),
    "rejected": (gettext_lazy("Rejected"), "#e11d48", "fa-ban"),
    "closed": (gettext_lazy("Closed"), "#64748b", "fa-lock"),
}
RETURN_REASON = {
    "defective": gettext_lazy("Defective"),
    "wrong_item": gettext_lazy("Wrong item"),
    "not_as_described": gettext_lazy("Not as described"),
    "changed_mind": gettext_lazy("Changed mind"),
    "damaged_in_transit": gettext_lazy("Damaged in transit"),
    "other": gettext_lazy("Other"),
}
CANCEL_STATUS = {
    "requested": (gettext_lazy("Requested"), "#f59e0b", "fa-inbox"),
    "approved": (gettext_lazy("Approved"), "#6366f1", "fa-circle-check"),
    "completed": (gettext_lazy("Completed"), "#10b981", "fa-flag-checkered"),
    "rejected": (gettext_lazy("Rejected"), "#e11d48", "fa-ban"),
}
CANCEL_REASON = {
    "customer_request": gettext_lazy("Customer request"),
    "out_of_stock": gettext_lazy("Out of stock"),
    "payment_failed": gettext_lazy("Payment failed"),
    "fraud_suspected": gettext_lazy("Fraud suspected"),
    "admin_action": gettext_lazy("Store decision"),
    "other": gettext_lazy("Other"),
}
# Reasons whose goods usually can't be sold again -- the "put back on the shelf" box starts unticked.
NOT_RESELLABLE = ("defective", "damaged_in_transit")

ORDER_FLOW = ["pending_payment", "confirmed", "processing", "shipped", "delivered"]
NEXT_STEP = {
    "pending_payment": ("confirm", gettext_lazy("Confirm order"), "fa-circle-check"),
    "confirmed": ("start_processing", gettext_lazy("Start packing"), "fa-box-open"),
    "processing": ("ship", gettext_lazy("Hand over to courier"), "fa-truck-fast"),
    "shipped": ("deliver", gettext_lazy("Mark as delivered"), "fa-house-circle-check"),
}

ERROR_TEXT = {
    "ORDER_NOT_RETURNABLE": gettext_lazy("Only a delivered order can be returned."),
    "RETURN_WINDOW_EXPIRED": gettext_lazy("The 14-day return period has passed. Tick “Accept after the return period” to accept it anyway."),
    "ORDER_DELIVERED_USE_RETURN": gettext_lazy("This order is already delivered -- open a return instead."),
    "ORDER_NOT_CANCELLABLE": gettext_lazy("This order can no longer be cancelled."),
    "NO_LINES": gettext_lazy("Choose at least one item."),
    "LINE_NOT_IN_ORDER": gettext_lazy("This item is not an active line of the order."),
    "QUANTITY_EXCEEDS_REMAINING": gettext_lazy("The quantity is more than is left of this item."),
    "INSUFFICIENT_STOCK": gettext_lazy("Not enough stock at the chosen location. Receive stock first or pick another location."),
    "NO_FULFILMENT_LOCATION": gettext_lazy("No location to ship from."),
}


def money(amount) -> str:
    return f"{int(round(Decimal(amount or 0))):,}".replace(",", " ")


def error_text(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    if code in ERROR_TEXT:
        base = str(ERROR_TEXT[code])
        lines = (getattr(exc, "details", None) or {}).get("lines")
        if code == "INSUFFICIENT_STOCK" and lines:
            infos = _variant_infos([uuid.UUID(l["variant_id"]) for l in lines])
            parts = [f"{infos[uuid.UUID(l['variant_id'])].name if uuid.UUID(l['variant_id']) in infos else l['variant_id']}: {l['have']}/{l['need']}" for l in lines]
            base += " (" + "; ".join(parts) + ")"
        return base
    name = type(exc).__name__
    if name in ("InvalidOrderLifecycleTransition", "InvalidReturnLifecycleTransition", "InvalidCancellationLifecycleTransition", "OrderNotEligibleForCancellation", "OrderAlreadyCancelled", "OrderAlreadyCompleted"):
        return _("This step is not possible in the current status. Refresh the page.")
    message = getattr(exc, "message", None) or str(exc)
    if "exceeds the remaining refundable amount" in message:
        return _("The refund is more than the customer paid for this order (minus earlier refunds).")
    return message


def staff_ctx(request):
    from apps.ordering.infrastructure.composition import build_ordering_service_context

    user = request.user
    label = (user.get_full_name() or user.get_username()) if getattr(user, "is_authenticated", False) else ""
    return build_ordering_service_context(actor_id=getattr(user, "id", None), actor_label=label)


def _variant_infos(variant_ids) -> dict:
    from apps.stores.infrastructure.stock_service import variant_infos

    lang = (get_language() or "uz")[:2]
    return variant_infos(set(variant_ids), lang if lang in ("uz", "ru", "en") else "uz")


def status_style(status: str):
    from apps.ordering.infrastructure.admin import _ORDER_STATUS_LABELS, _STATUS_STYLE

    color, icon = _STATUS_STYLE.get(status, ("#64748b", "fa-circle"))
    return {"key": status, "label": _ORDER_STATUS_LABELS.get(status, status), "color": color, "icon": icon}


def _line_net(line) -> Decimal:
    return line.unit_price_amount * line.quantity - line.discount_amount + line.tax_amount


def _customer(order: orm.OrderModel) -> dict:
    from apps.identity.infrastructure.models import User

    user = User.objects.filter(id=order.customer_id).first() if order.customer_id else None
    name = (user.full_name if user else "") or order.shipping_recipient_name or _("Customer")
    phone = (user.phone_number if user else "") or order.shipping_phone or ""
    out = {
        "name": name, "phone": phone, "initials": "".join(p[0] for p in name.split()[:2]).upper() or "?",
        "telegram": (user.telegram_username if user else "") or "", "user_id": user.id if user else None,
        "orders": 0, "delivered": 0, "spent": "0", "since": getattr(user, "created_at", None),
    }
    if order.customer_id:
        mine = orm.OrderModel.objects.filter(customer_id=order.customer_id).exclude(status="draft")
        out["orders"] = mine.count()
        done = mine.filter(status__in=("delivered", "completed"))
        out["delivered"] = done.count()
        from django.db.models import DecimalField, ExpressionWrapper, F

        expr = ExpressionWrapper(F("unit_price_amount") * F("quantity") - F("discount_amount") + F("tax_amount"), output_field=DecimalField(max_digits=16, decimal_places=2))
        total = orm.OrderLineItemModel.objects.filter(order__in=done, status="active").aggregate(t=Sum(expr))["t"]
        out["spent"] = money(total)
    return out


def _coins(order_id) -> dict:
    try:
        from apps.loyalty.infrastructure.models import WalletTransaction, WalletTransactionKind
        from apps.loyalty.infrastructure.services import coins_spent_on_order

        earned = WalletTransaction.objects.filter(order_id=order_id, kind=WalletTransactionKind.EARN).values_list("amount", flat=True).first()
        reversed_ = WalletTransaction.objects.filter(order_id=order_id, kind=WalletTransactionKind.REVERSAL).exists()
        refunded = WalletTransaction.objects.filter(order_id=order_id, kind=WalletTransactionKind.REFUND).exists()
        return {"spent": coins_spent_on_order(order_id), "earned": earned or 0, "reversed": reversed_, "refunded": refunded}
    except Exception:  # noqa: BLE001 - loyalty is optional decoration on this page
        return {"spent": 0, "earned": 0, "reversed": False, "refunded": False}


def _history(order: orm.OrderModel) -> list[dict]:
    from apps.identity.infrastructure.models import User
    from apps.ordering.application.services._shared import ACTOR_SEPARATOR

    rows = list(order.status_history.order_by("changed_at"))
    users = {u.id: (u.full_name or u.phone_number) for u in User.objects.filter(id__in=[r.actor_id for r in rows if r.actor_id])}
    out = []
    for r in rows:
        reason, _sep, staff = (r.reason or "").partition(ACTOR_SEPARATOR)
        actor = staff or users.get(r.actor_id) or ""
        out.append({**status_style(r.to_status), "at": r.changed_at, "reason": _humanise_reason(reason), "actor": actor, "is_customer": bool(r.actor_id and not staff)})
    return out


def _humanise_reason(reason: str) -> str:
    known = {
        "": "", "completed": "", "returned": "", "processing_started": "", "shipped": "", "delivered": "", "confirmed": "",
        "admin_bulk_cancel": _("Cancelled from the order list"),
        "Manager cancelled via Telegram Orders Channel": _("Cancelled in the Telegram orders channel"),
    }
    if reason in known:
        return known[reason]
    if reason.startswith("cancellation:"):
        return str(CANCEL_REASON.get(reason.split(":", 1)[1], reason))
    if reason.startswith("return "):
        return _("Return %(number)s") % {"number": reason.split(" ", 1)[1]}
    return reason


def _stock_options(order: orm.OrderModel, lines: list[dict]) -> list[dict]:
    """Where the parcel can leave from, with what each location is missing for this order."""
    from apps.stores.infrastructure import online_fulfilment as of

    pairs = [(l["variant_id"], l["quantity"]) for l in lines if l["active"]]
    if not pairs:
        return []
    default = of.fulfilment_store()
    reserved = of.reserved_for(order.order_number)
    reserving = {sid for (sid, _v) in reserved}
    names = {l["variant_id"]: l["name"] for l in lines}
    out = []
    for store in of.ship_locations():
        missing = [{**m, "name": names.get(m["variant_id"], "")} for m in of.shortages_at(store, order.order_number, pairs)]
        out.append({
            "id": store.id, "name": store.name, "is_warehouse": store.kind == "warehouse",
            "missing": missing, "ok": not missing, "reserved_here": store.id in reserving,
            "default": (store.id in reserving) if reserving else (default is not None and store.id == default.id),
        })
    out.sort(key=lambda o: (not o["default"], not o["ok"], not o["is_warehouse"], o["name"]))
    return out


def _fulfilment(order: orm.OrderModel, lines: list[dict]) -> dict:
    """Delivery or pickup, the branch handling it, and the branches it could go to (stock + distance) for the assign form."""
    from apps.geo.infrastructure.admin import map_links
    from apps.stores.infrastructure import store_orders
    from apps.stores.infrastructure.models import Store

    store = Store.objects.filter(pk=order.fulfilment_store_id).first() if order.fulfilment_store_id else None
    pairs = [(l["variant_id"], l["quantity"]) for l in lines if l["active"]]
    options = store_orders.pickup_options(pairs, order.shipping_latitude, order.shipping_longitude) if pairs else []
    return {
        "method": order.fulfilment_method or "delivery", "pickup": order.fulfilment_method == "pickup",
        "store": store, "assigned_at": order.store_assigned_at, "options": options,
        "can_assign": order.status in ("pending_payment", "confirmed", "processing") and not order.is_archived,
        "links": map_links(order.shipping_latitude, order.shipping_longitude, order.shipping_line1),
    }


def order_snapshot(order: orm.OrderModel) -> dict:
    lines_qs = list(order.lines.all())
    infos = _variant_infos([l.product_variant_id for l in lines_qs])
    returned = _units_by_line(orm.ReturnLineItemModel.objects.filter(order_return__order_id=order.id).exclude(order_return__status="rejected"))
    cancelled = _units_by_line(orm.CancellationLineItemModel.objects.filter(cancellation__order_id=order.id).exclude(cancellation__status="rejected"))
    lines, subtotal, discount, tax = [], Decimal(0), Decimal(0), Decimal(0)
    for l in lines_qs:
        info = infos.get(l.product_variant_id)
        active = l.status == "active"
        if active:
            subtotal += l.unit_price_amount * l.quantity
            discount += l.discount_amount
            tax += l.tax_amount
        lines.append({
            "id": l.id, "variant_id": l.product_variant_id, "quantity": l.quantity, "status": l.status, "active": active,
            "name": info.name if info else _("Unknown product"), "size": info.size if info else None, "sku": info.sku if info else "",
            "image": info.image_url if info else None, "product_id": info.product_id if info else None,
            "unit": money(l.unit_price_amount), "discount": money(l.discount_amount) if l.discount_amount else "",
            "total": money(_line_net(l)), "net_unit": (_line_net(l) / l.quantity) if l.quantity else Decimal(0),
            "returned": returned.get(l.id, 0), "cancelled": cancelled.get(l.id, 0),
            "returnable": max(l.quantity - returned.get(l.id, 0), 0) if active else 0,
            "cancellable": max(l.quantity - cancelled.get(l.id, 0), 0) if active else 0,
        })
    coins = _coins(order.id)
    total = subtotal - discount + tax
    style = status_style(order.status)
    flow_index = ORDER_FLOW.index(order.status) if order.status in ORDER_FLOW else None
    steps = []
    reached = {h.to_status: h.changed_at for h in order.status_history.all()}
    for i, key in enumerate(ORDER_FLOW):
        s = status_style(key)
        s["state"] = "done" if flow_index is not None and i < flow_index else "current" if flow_index == i else ("done" if order.status == "completed" else "todo")
        s["at"] = reached.get(key)
        steps.append(s)
    returns = list(orm.OrderReturnModel.objects.filter(order_id=order.id).order_by("-created_at"))
    cancels = list(orm.OrderCancellationModel.objects.filter(order_id=order.id).order_by("-created_at"))
    return {
        "order": order, "style": style, "steps": steps, "lines": lines, "units": sum(l["quantity"] for l in lines if l["active"]),
        "totals": {
            "subtotal": money(subtotal), "discount": money(discount), "tax": money(tax), "total": money(total),
            # Line discounts hold coupon + coins together (cart allocates both); split them back for display.
            "coupon": money(max(discount - coins["spent"], Decimal(0))), "coins": money(coins["spent"]), "has_coins": coins["spent"] > 0,
            "cash": money(total),
            "raw_subtotal": subtotal, "raw_discount": discount, "raw_total": total,
        },
        "coins": coins, "customer": _customer(order), "history": _history(order),
        "next": NEXT_STEP.get(order.status) if not order.is_archived else None,
        "can_cancel_now": order.status in ("pending_payment", "confirmed", "processing"),
        "can_request_cancellation": order.status in ("pending_payment", "confirmed", "processing", "shipped"),
        "can_return": order.status in ("delivered", "completed"),
        "stock_options": _stock_options(order, lines) if order.status in ("confirmed", "processing") else [],
        "returns": [{"obj": r, "style": _style(RETURN_STATUS, r.status)} for r in returns],
        "cancellations": [{"obj": c, "style": _style(CANCEL_STATUS, c.status)} for c in cancels],
        "map": _map(order.shipping_latitude, order.shipping_longitude),
        "fulfilment": _fulfilment(order, lines),
        "channel": _channel(order.channel),
        "cancel_reasons": list(CANCEL_REASON.items()),
    }


def _map(lat, lng):
    if lat is None or lng is None:
        return None
    return {"lat": f"{lat:.6f}", "lng": f"{lng:.6f}", "bbox": f"{lng - 0.006:.6f},{lat - 0.0035:.6f},{lng + 0.006:.6f},{lat + 0.0035:.6f}"}


def _channel(channel: str) -> dict:
    from apps.ordering.infrastructure.admin import _CHANNEL_ICONS, _CHANNEL_LABELS

    icon = _CHANNEL_ICONS.get(channel, "fa-globe")
    return {"label": _CHANNEL_LABELS.get(channel, channel), "icon": icon if icon.startswith("fab") else f"fas {icon}"}


def _units_by_line(qs) -> dict:
    return {row["order_line_item_id"]: row["n"] for row in qs.values("order_line_item_id").annotate(n=Sum("quantity"))}


def _style(table: dict, status: str) -> dict:
    label, color, icon = table.get(status, (status, "#64748b", "fa-circle"))
    return {"key": status, "label": label, "color": color, "icon": icon}


# ------------------------------------------------------------------ returns / cancellations


def workflow_snapshot(obj, kind: str) -> dict:
    """Detail of one return ("return") or cancellation ("cancel"): its items priced from the order, the order, the customer, the steps."""
    is_return = kind == "return"
    order = orm.OrderModel.objects.filter(id=obj.order_id).first()
    order_lines = {l.id: l for l in order.lines.all()} if order else {}
    items_qs = list(obj.lines.all())
    infos = _variant_infos([order_lines[i.order_line_item_id].product_variant_id for i in items_qs if i.order_line_item_id in order_lines])
    items, value = [], Decimal(0)
    for i in items_qs:
        ol = order_lines.get(i.order_line_item_id)
        info = infos.get(ol.product_variant_id) if ol else None
        unit_net = (_line_net(ol) / ol.quantity) if ol and ol.quantity else Decimal(0)
        line_value = unit_net * i.quantity
        value += line_value
        items.append({
            "quantity": i.quantity, "ordered": ol.quantity if ol else None, "name": info.name if info else _("Unknown product"),
            "size": info.size if info else None, "sku": info.sku if info else "", "image": info.image_url if info else None,
            "unit": money(unit_net), "total": money(line_value),
        })
    table = RETURN_STATUS if is_return else CANCEL_STATUS
    flow = ["requested", "approved", "received", "refunded"] if is_return else ["requested", "approved", "completed"]
    stamps = {"requested": obj.requested_at, "approved": obj.approved_at}
    stamps.update({"received": obj.received_at, "refunded": obj.refunded_at} if is_return else {"completed": obj.completed_at})
    rejected = obj.status == "rejected"
    current = flow.index(obj.status) if obj.status in flow else (len(flow) if obj.status == "closed" else 0)
    steps = []
    for i, key in enumerate(flow):
        s = _style(table, key)
        s["at"] = stamps.get(key)
        s["state"] = "done" if (i < current or (i == current and key == flow[-1])) else "current" if i == current and not rejected else "todo"
        if rejected and i == 1:
            s = {**_style(table, "rejected"), "state": "rejected", "at": obj.updated_at}
        steps.append(s)
        if rejected and i == 1:
            break
    paid = Decimal(0)
    refundable = Decimal(0)
    if order and is_return:
        from apps.ordering.application.services.returns import paid_total
        from apps.ordering.infrastructure.composition import build_order_repository

        domain_order = build_order_repository().get_by_id(order.id)
        paid = paid_total(domain_order) if domain_order else Decimal(0)
        earlier = orm.OrderReturnModel.objects.filter(order_id=order.id, status="refunded").exclude(id=obj.id).aggregate(t=Sum("refund_amount"))["t"] or Decimal(0)
        refundable = max(paid - earlier, Decimal(0))
    suggested = min(value, refundable) if is_return else value
    return {
        "obj": obj, "kind": kind, "style": _style(table, obj.status), "steps": steps, "items": items,
        "value": money(value), "suggested": int(round(suggested)), "paid": money(paid), "refundable": money(refundable),
        "refunded": money(obj.refund_amount) if obj.refund_amount is not None else "",
        "reason_label": (RETURN_REASON if is_return else CANCEL_REASON).get(obj.reason, obj.reason),
        "order": order, "order_style": status_style(order.status) if order else None, "customer": _customer(order) if order else None,
        "restock_default": obj.reason not in NOT_RESELLABLE if is_return else True,
        "number": obj.return_number if is_return else f"BEK-{str(obj.id)[:8].upper()}",
    }


def cancellation_number(obj) -> str:
    return f"BEK-{str(obj.id)[:8].upper()}"


def find_orders(q: str, purpose: str, limit: int = 8) -> list[dict]:
    """Order picker for the "new return / new cancellation" pages: by number, buyer name or phone."""
    from apps.identity.infrastructure.models import User

    q = (q or "").strip()
    qs = orm.OrderModel.objects.exclude(status="draft")
    if purpose == "return":
        qs = qs.filter(status__in=("delivered", "completed"))
    else:
        qs = qs.filter(status__in=("pending_payment", "confirmed", "processing", "shipped"))
    if q:
        match = Q(order_number__icontains=q) | Q(shipping_recipient_name__icontains=q)
        digits = "".join(ch for ch in q if ch.isdigit())
        users = User.objects.filter(Q(full_name__icontains=q) | (Q(phone_number__icontains=digits) if len(digits) >= 3 else Q(pk__in=[])))
        match |= Q(customer_id__in=users.values("id"))
        if len(digits) >= 3:
            match |= Q(shipping_phone__icontains=digits)
        qs = qs.filter(match)
    out = []
    for o in qs.order_by("-placed_at")[:limit]:
        c = _customer(o)
        active = [l for l in o.lines.all() if l.status == "active"]
        out.append({
            "id": str(o.id), "number": o.order_number, "status": status_style(o.status), "customer": c["name"], "phone": c["phone"],
            "total": money(sum((_line_net(l) for l in active), Decimal(0))), "units": sum(l.quantity for l in active),
            "placed": timezone.localtime(o.placed_at).strftime("%d.%m.%Y") if o.placed_at else "",
        })
    return out


def parse_lines(post, prefix: str = "qty_") -> list[dict]:
    lines = []
    for key, value in post.items():
        if key.startswith(prefix) and value not in ("", "0"):
            try:
                lines.append({"order_line_item_id": key[len(prefix):], "quantity": int(value)})
            except ValueError:
                continue
    return lines


def parse_amount(raw) -> Decimal | None:
    raw = (raw or "").replace(" ", "").replace(",", ".")
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    return value if value >= 0 else None


def list_kpis(model, statuses: dict, money_field: str = "refund_amount") -> dict:
    """Header numbers for the returns / cancellations lists."""
    now = timezone.now()
    month = model.objects.filter(created_at__gte=now - timedelta(days=30))
    counts = dict(model.objects.values_list("status").annotate(n=Count("id")))
    refunded = month.aggregate(t=Sum(money_field))["t"] or Decimal(0)
    return {"counts": counts, "month": month.count(), "refunded": money(refunded), "total": sum(counts.values())}


def annotate_rows(rows, kind: str) -> None:
    """Changelist rows (returns or cancellations) get order number, customer, item count and value -- a fixed number of queries per page."""
    from django.db.models import DecimalField, ExpressionWrapper, F

    from apps.identity.infrastructure.models import User

    rows = list(rows)
    if not rows:
        return
    is_return = kind == "return"
    orders = {o.id: o for o in orm.OrderModel.objects.filter(id__in={r.order_id for r in rows})}
    users = {u.id: u for u in User.objects.filter(id__in={o.customer_id for o in orders.values() if o.customer_id})}
    item_model = orm.ReturnLineItemModel if is_return else orm.CancellationLineItemModel
    fk = "order_return_id" if is_return else "cancellation_id"
    items = list(item_model.objects.filter(**{f"{fk}__in": [r.id for r in rows]}).values(fk, "order_line_item_id", "quantity"))
    order_lines = {l.id: l for l in orm.OrderLineItemModel.objects.filter(id__in={i["order_line_item_id"] for i in items})}
    per_row: dict = {}
    for i in items:
        ol = order_lines.get(i["order_line_item_id"])
        units, value = per_row.get(i[fk], (0, Decimal(0)))
        unit_net = (_line_net(ol) / ol.quantity) if ol and ol.quantity else Decimal(0)
        per_row[i[fk]] = (units + i["quantity"], value + unit_net * i["quantity"])
    table = RETURN_STATUS if is_return else CANCEL_STATUS
    reasons = RETURN_REASON if is_return else CANCEL_REASON
    now = timezone.now()
    for r in rows:
        o = orders.get(r.order_id)
        u = users.get(o.customer_id) if o and o.customer_id else None
        name = (u.full_name if u else "") or (o.shipping_recipient_name if o else "") or _("Customer")
        units, value = per_row.get(r.id, (0, Decimal(0)))
        r.nz = {
            "number": r.return_number if is_return else cancellation_number(r),
            "order": o, "order_style": status_style(o.status) if o else None,
            "customer": name, "phone": (u.phone_number if u else "") or (o.shipping_phone if o else "") or "",
            "initials": "".join(p[0] for p in name.split()[:2]).upper() or "?",
            "units": units, "value": money(r.refund_amount if r.refund_amount is not None else value),
            "is_refund": r.refund_amount is not None,
            "style": _style(table, r.status), "reason": reasons.get(r.reason, r.reason),
            "age_days": (now - r.created_at).days if r.created_at else 0,
            "open": r.status in ("requested", "approved") or (is_return and r.status == "received"),
        }
