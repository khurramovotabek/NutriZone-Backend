"""
Dispatcher board (Buyurtmalar paneli): live orders as Kanban columns -- data for templates/admin/ordering/ordermodel/board.html.

Every card is built from a fixed number of bulk queries (no per-order queries), so the 30-second auto-refresh stays
cheap. Moves are one step forward only and go through OrderAdmin.run_order_action (the same services as the workspace).
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.ordering.infrastructure import models as orm

# column key -> the action that moves a card OUT of it to the next column
NEXT_ACTION = {"pending_payment": "confirm", "confirmed": "start_processing", "processing": "ship", "shipped": "deliver"}
CARD_LIMIT = 80
DELIVERED_DAYS = 3
# (warn, late) thresholds in minutes for how long a card may sit in a column
SLA_MINUTES = {"pending_payment": (120, 720), "confirmed": (60, 240), "processing": (180, 480), "shipped": (1440, 2880)}


def _columns():
    from apps.ordering.infrastructure.admin_desk import status_style

    out = []
    for key, hint in (
        ("pending_payment", _("Waiting for payment or a call")),
        ("confirmed", _("New -- start packing")),
        ("processing", _("Packing -- hand over to the courier")),
        ("shipped", _("With the courier")),
        ("delivered", _("Delivered in the last 3 days")),
    ):
        style = status_style(key)
        out.append({"key": key, "label": str(style["label"]), "color": style["color"], "icon": style["icon"], "hint": hint, "next": NEXT_ACTION.get(key)})
    return out


def _entered_at(orders) -> dict:
    """When each order entered its current status (history), falling back to placed_at."""
    rows = orm.OrderStatusHistoryEntryModel.objects.filter(order_id__in=[o.id for o in orders]).values("order_id", "to_status", "changed_at")
    best: dict = {}
    status_of = {o.id: o.status for o in orders}
    for r in rows:
        if r["to_status"] == status_of.get(r["order_id"]) and (r["order_id"] not in best or r["changed_at"] > best[r["order_id"]]):
            best[r["order_id"]] = r["changed_at"]
    return best


def _stock_shortages(orders, lines_by_order) -> dict:
    """{order_id: number of lines the main warehouse can't cover} for orders not yet shipped (units this order reserved count as covered)."""
    from apps.stores.infrastructure import online_fulfilment as of
    from apps.stores.infrastructure import stock_service
    from apps.stores.infrastructure.models import StockMovement

    todo = [o for o in orders if o.status in ("confirmed", "processing")]
    store = of.fulfilment_store()
    if not todo or store is None:
        return {}
    vids = {l.product_variant_id for o in todo for l in lines_by_order.get(o.id, [])}
    free = stock_service.available_map(store, vids)
    reserved: dict = {}
    for row in StockMovement.objects.filter(store=store, reference__in=[o.order_number for o in todo], movement_type__in=("reservation", "release")).values("reference", "product_variant_id").annotate(n=Sum("quantity")):
        reserved[(row["reference"], row["product_variant_id"])] = reserved.get((row["reference"], row["product_variant_id"]), 0) + row["n"]
    out = {}
    for o in todo:
        short = 0
        for l in lines_by_order.get(o.id, []):
            if free.get(l.product_variant_id, 0) + max(reserved.get((o.order_number, l.product_variant_id), 0), 0) < l.quantity:
                short += 1
        if short:
            out[o.id] = short
    return out


def board_payload() -> dict:
    from apps.identity.infrastructure.models import User
    from apps.loyalty.infrastructure.models import WalletTransaction, WalletTransactionKind
    from apps.ordering.infrastructure.admin_desk import _variant_infos, money

    now = timezone.now()
    live = list(orm.OrderModel.objects.filter(is_archived=False, status__in=list(NEXT_ACTION)).order_by("placed_at", "created_at")[: CARD_LIMIT * 4])
    delivered = list(orm.OrderModel.objects.filter(is_archived=False, status="delivered", updated_at__gte=now - timedelta(days=DELIVERED_DAYS)).order_by("-updated_at")[:CARD_LIMIT])
    orders = live + delivered
    ids = [o.id for o in orders]

    lines_by_order: dict = {}
    for l in orm.OrderLineItemModel.objects.filter(order_id__in=ids, status="active"):
        lines_by_order.setdefault(l.order_id, []).append(l)
    infos = _variant_infos({l.product_variant_id for ls in lines_by_order.values() for l in ls})
    users = {u.id: u for u in User.objects.filter(id__in={o.customer_id for o in orders if o.customer_id}).only("id", "full_name", "phone_number")}
    coins = {r["order_id"]: -r["amount"] for r in WalletTransaction.objects.filter(order_id__in=ids, kind=WalletTransactionKind.SPEND).values("order_id", "amount")}
    open_returns = dict(orm.OrderReturnModel.objects.filter(order_id__in=ids, status__in=("requested", "approved", "received")).values_list("order_id").annotate(n=Count("id")))
    open_cancels = dict(orm.OrderCancellationModel.objects.filter(order_id__in=ids, status__in=("requested", "approved")).values_list("order_id").annotate(n=Count("id")))
    entered = _entered_at(orders)
    shortages = _stock_shortages(orders, lines_by_order)

    cards: dict = {c["key"]: [] for c in _columns()}
    totals: dict = {key: Decimal(0) for key in cards}
    for o in orders:
        ls = lines_by_order.get(o.id, [])
        total = sum((l.unit_price_amount * l.quantity - l.discount_amount + l.tax_amount for l in ls), Decimal(0))
        totals[o.status] += total
        u = users.get(o.customer_id)
        name = (u.full_name if u else "") or o.shipping_recipient_name or _("Customer")
        since = entered.get(o.id) or o.placed_at or o.created_at
        minutes = int((now - since).total_seconds() // 60) if since else 0
        warn, late = SLA_MINUTES.get(o.status, (10**9, 10**9))
        thumbs = []
        for l in ls[:3]:
            info = infos.get(l.product_variant_id)
            thumbs.append(info.image_url if info and info.image_url else "")
        first = infos.get(ls[0].product_variant_id) if ls else None
        cards[o.status].append({
            "id": str(o.id), "number": o.order_number, "url": f"/django-admin/ordering/ordermodel/{o.id}/change/",
            "status": o.status, "minutes": minutes, "sla": "late" if minutes >= late else "warn" if minutes >= warn else "ok",
            "placed": timezone.localtime(o.placed_at).strftime("%d.%m %H:%M") if o.placed_at else "",
            "customer": name, "phone": (u.phone_number if u else "") or o.shipping_phone or "",
            "city": ", ".join(p for p in (o.shipping_city, o.shipping_region) if p),
            "units": sum(l.quantity for l in ls), "lines": len(ls), "thumbs": thumbs, "more": max(len(ls) - 3, 0),
            "first_item": first.name if first else "",
            "total": money(total), "coins": money(coins[o.id]) if coins.get(o.id) else "",
            "comment": bool(o.customer_comment), "note": bool(o.note), "has_map": o.shipping_latitude is not None,
            "short": shortages.get(o.id, 0), "requests": open_returns.get(o.id, 0) + open_cancels.get(o.id, 0),
            "channel": o.channel,
        })
    columns = _columns()
    for c in columns:
        c["count"] = len(cards[c["key"]])
        c["sum"] = money(totals[c["key"]])
        c["late"] = sum(1 for card in cards[c["key"]] if card["sla"] == "late")
        c["cards"] = cards[c["key"]][:CARD_LIMIT]
    in_work = sum((totals[k] for k in ("confirmed", "processing", "shipped")), Decimal(0))
    today = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    delivered_today = orm.OrderModel.objects.filter(status__in=("delivered", "completed"), status_history__to_status="delivered", status_history__changed_at__gte=today).distinct().count()
    return {
        "columns": columns, "updated": timezone.localtime(now).strftime("%H:%M:%S"),
        "summary": {
            "active": sum(c["count"] for c in columns if c["key"] != "delivered"), "late": sum(c["late"] for c in columns),
            "in_work": money(in_work), "delivered_today": delivered_today,
            "requests": orm.OrderReturnModel.objects.filter(status="requested").count() + orm.OrderCancellationModel.objects.filter(status="requested").count(),
        },
        "cities": sorted({card["city"].split(",")[0] for c in columns for card in c["cards"] if card["city"]}),
    }


def ship_options(order: orm.OrderModel) -> list[dict]:
    from apps.ordering.infrastructure.admin_desk import _stock_options, _variant_infos

    ls = [l for l in order.lines.all() if l.status == "active"]
    infos = _variant_infos({l.product_variant_id for l in ls})
    lines = [{"variant_id": l.product_variant_id, "quantity": l.quantity, "active": True, "name": infos[l.product_variant_id].name if l.product_variant_id in infos else ""} for l in ls]
    return [
        {"id": str(o["id"]), "name": o["name"], "is_warehouse": o["is_warehouse"], "ok": o["ok"], "default": o["default"], "reserved_here": o["reserved_here"],
         "missing": [{"name": m["name"], "have": m["have"], "need": m["need"]} for m in o["missing"]]}
        for o in _stock_options(order, lines)
    ]
