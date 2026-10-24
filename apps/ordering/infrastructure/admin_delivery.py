"""
Delivery desk (Yetkazib berish markazi): every delivery order with what goes in the parcel, where it goes, who takes it
and how much the courier collects -- data for templates/admin/ordering/ordermodel/delivery.html.

Built from a fixed number of bulk queries. Status moves reuse OrderAdmin.run_order_action (board move endpoint);
this module only writes the courier assignment (DeliveryAssignment).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.ordering.infrastructure import models as orm

STAGES = {
    "new": ("pending_payment",),
    "prepare": ("confirmed", "processing"),
    "road": ("shipped",),
    "done": ("delivered", "completed"),
}
DONE_DAYS = 3
LIMIT = 150


def _stage_label(key: str) -> str:
    return {"new": _("Awaiting payment"), "prepare": _("To pack"), "road": _("On the road"), "done": _("Delivered")}[key]


def _base_qs():
    return orm.OrderModel.objects.filter(is_archived=False, fulfilment_method="delivery")


def _stage_qs(stage: str):
    qs = _base_qs().filter(status__in=STAGES[stage])
    if stage == "done":
        qs = qs.filter(updated_at__gte=timezone.now() - timedelta(days=DONE_DAYS))
    return qs


def _paid_by_order(ids) -> dict:
    from apps.payment.infrastructure.models import PaymentModel

    rows = PaymentModel.objects.filter(order_id__in=ids, status="succeeded").exclude(provider="cash").values("order_id").annotate(s=Sum("amount"))
    return {r["order_id"]: r["s"] or Decimal(0) for r in rows}


def _full_address(o) -> str:
    return ", ".join(p for p in (o.shipping_line1, o.shipping_line2, o.shipping_city, o.shipping_region) if p)


def desk_payload(stage: str = "prepare", q: str = "", city: str = "", courier: str = "", day: str = "") -> dict:
    from apps.geo.infrastructure.admin import map_links
    from apps.identity.infrastructure.models import User
    from apps.ordering.infrastructure.admin_board import SLA_MINUTES, _entered_at, _stock_shortages
    from apps.ordering.infrastructure.admin_desk import _variant_infos, money, status_style

    stage = stage if stage in STAGES else "prepare"
    now = timezone.now()
    qs = _stage_qs(stage).select_related("delivery", "delivery__courier")
    if q:
        qs = qs.filter(Q(order_number__icontains=q) | Q(shipping_recipient_name__icontains=q) | Q(shipping_phone__icontains=q) | Q(shipping_line1__icontains=q))
    if city:
        qs = qs.filter(shipping_city=city)
    if courier == "none":
        qs = qs.filter(Q(delivery__isnull=True) | Q(delivery__courier__isnull=True))
    elif courier:
        qs = qs.filter(delivery__courier_id=courier)
    if day:
        qs = qs.filter(delivery__planned_date=day)
    orders = list(qs.order_by("placed_at", "created_at")[:LIMIT])
    ids = [o.id for o in orders]

    lines_by_order: dict = {}
    for l in orm.OrderLineItemModel.objects.filter(order_id__in=ids, status="active"):
        lines_by_order.setdefault(l.order_id, []).append(l)
    infos = _variant_infos({l.product_variant_id for ls in lines_by_order.values() for l in ls})
    users = {u.id: u for u in User.objects.filter(id__in={o.customer_id for o in orders if o.customer_id}).only("id", "full_name", "phone_number")}
    paid = _paid_by_order(ids)
    entered = _entered_at(orders)
    shortages = _stock_shortages(orders, lines_by_order)

    cards = []
    for o in orders:
        ls = lines_by_order.get(o.id, [])
        items, total = [], Decimal(0)
        for l in ls:
            info = infos.get(l.product_variant_id)
            net = l.unit_price_amount * l.quantity - l.discount_amount + l.tax_amount
            total += net
            items.append({"name": info.name if info else _("Unknown product"), "size": info.size if info else "", "sku": info.sku if info else "",
                          "image": info.image_url if info else "", "qty": l.quantity, "unit": money(l.unit_price_amount), "total": money(net)})
        got = paid.get(o.id, Decimal(0))
        collect = max(total - got, Decimal(0))
        u = users.get(o.customer_id)
        since = entered.get(o.id) or o.placed_at or o.created_at
        minutes = int((now - since).total_seconds() // 60) if since else 0
        warn, late = SLA_MINUTES.get(o.status, (10**9, 10**9))
        d = getattr(o, "delivery", None)
        cards.append({
            "id": str(o.id), "number": o.order_number, "url": f"/django-admin/ordering/ordermodel/{o.id}/change/",
            "status": status_style(o.status), "raw_status": o.status,
            "placed": timezone.localtime(o.placed_at).strftime("%d.%m %H:%M") if o.placed_at else "",
            "minutes": minutes, "sla": "late" if minutes >= late else "warn" if minutes >= warn else "ok",
            "recipient": o.shipping_recipient_name or (u.full_name if u else "") or _("Customer"),
            "phone": o.shipping_phone or (u.phone_number if u else "") or "",
            "address": _full_address(o), "line1": o.shipping_line1, "line2": o.shipping_line2 or "",
            "city": o.shipping_city, "region": o.shipping_region or "",
            "lat": o.shipping_latitude, "lng": o.shipping_longitude, "links": map_links(o.shipping_latitude, o.shipping_longitude, o.shipping_line1),
            "items": items, "units": sum(i["qty"] for i in items), "total": money(total),
            "paid": money(got), "collect": money(collect), "raw_collect": collect, "is_paid": collect == 0 and total > 0,
            "comment": o.customer_comment or "", "note": o.note or "", "short": shortages.get(o.id, 0),
            "courier_id": str(d.courier_id) if d and d.courier_id else "", "courier": d.courier.name if d and d.courier else "",
            "courier_phone": d.courier.phone if d and d.courier else "",
            "planned_date": d.planned_date.isoformat() if d and d.planned_date else "", "time_slot": d.time_slot if d else "",
            "fee": f"{d.fee:.0f}" if d and d.fee is not None else "", "courier_note": d.note if d else "",
            "next": {"pending_payment": "confirm", "confirmed": "start_processing", "processing": "ship", "shipped": "deliver"}.get(o.status),
        })

    today = timezone.localdate()
    start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    road = list(_stage_qs("road").values_list("id", flat=True))
    road_total = Decimal(0)
    if road:
        from django.db.models import DecimalField, ExpressionWrapper, F

        expr = ExpressionWrapper(F("unit_price_amount") * F("quantity") - F("discount_amount") + F("tax_amount"), output_field=DecimalField(max_digits=16, decimal_places=2))
        road_total = orm.OrderLineItemModel.objects.filter(order_id__in=road, status="active").aggregate(t=Sum(expr))["t"] or Decimal(0)
        road_total -= sum(_paid_by_order(road).values(), Decimal(0))
    active = _base_qs().filter(status__in=STAGES["prepare"] + STAGES["road"])
    stats = {
        "new": _stage_qs("new").count(), "prepare": _stage_qs("prepare").count(), "road": len(road), "done": _stage_qs("done").count(),
        "unassigned": active.filter(Q(delivery__isnull=True) | Q(delivery__courier__isnull=True)).count(),
        "delivered_today": _base_qs().filter(status__in=STAGES["done"], status_history__to_status="delivered", status_history__changed_at__gte=start).distinct().count(),
        "to_collect": money(max(road_total, Decimal(0))),
        "late": sum(1 for c in cards if c["sla"] == "late"),
    }
    loads = {r["courier_id"]: r["n"] for r in orm.DeliveryAssignment.objects.filter(order__in=active, courier__isnull=False).values("courier_id").annotate(n=Count("id"))}
    couriers = [{"id": str(c.id), "name": c.name, "phone": c.phone, "vehicle": c.vehicle, "load": loads.get(c.id, 0)}
                for c in orm.Courier.objects.filter(is_active=True)]
    return {
        "stage": stage, "stages": [{"key": k, "label": _stage_label(k), "count": stats[k]} for k in STAGES],
        "cards": cards, "stats": stats, "couriers": couriers,
        "cities": sorted(set(_base_qs().filter(status__in=STAGES["prepare"] + STAGES["road"]).exclude(shipping_city="").values_list("shipping_city", flat=True))),
        "filters": {"q": q, "city": city, "courier": courier, "day": day},
        "pins": [{"n": c["number"], "lat": c["lat"], "lng": c["lng"], "who": c["recipient"], "addr": c["address"], "late": c["sla"] == "late"} for c in cards if c["lat"] is not None],
        "today": today.isoformat(), "tomorrow": (today + timedelta(days=1)).isoformat(),
        "updated": timezone.localtime(now).strftime("%H:%M"),
    }


def assign(order: orm.OrderModel, data: dict, by: str) -> orm.DeliveryAssignment:
    """Save who takes the order and when. A new courier can be typed in (name + phone) and is added to the list."""
    if order.fulfilment_method != "delivery":
        raise ValueError(_("This order is picked up in a store, it has no courier."))
    if order.status in ("cancelled", "returned", "failed") or order.is_archived:
        raise ValueError(_("This order is closed."))
    courier = None
    cid = (data.get("courier_id") or "").strip()
    new_name = (data.get("new_courier") or "").strip()[:120]
    if new_name:
        courier, _created = orm.Courier.objects.get_or_create(name=new_name, defaults={"phone": (data.get("new_phone") or "").strip()[:32]})
    elif cid:
        courier = orm.Courier.objects.filter(pk=cid, is_active=True).first()
        if courier is None:
            raise ValueError(_("Courier not found."))
    planned = None
    raw_date = (data.get("planned_date") or "").strip()
    if raw_date:
        try:
            planned = date.fromisoformat(raw_date)
        except ValueError as exc:
            raise ValueError(_("Invalid date.")) from exc
    fee = None
    raw_fee = str(data.get("fee") or "").replace(" ", "").strip()
    if raw_fee:
        try:
            fee = Decimal(raw_fee)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(_("Invalid amount.")) from exc
        if fee < 0:
            raise ValueError(_("Invalid amount."))
    row, _c = orm.DeliveryAssignment.objects.update_or_create(order=order, defaults={
        "courier": courier, "planned_date": planned, "time_slot": (data.get("time_slot") or "").strip()[:40],
        "fee": fee, "note": (data.get("note") or "").strip()[:300], "assigned_by": by[:150],
    })
    return row


def waybill(order: orm.OrderModel) -> dict:
    """One order for the printed delivery sheet (yo'l varaqasi)."""
    from apps.ordering.infrastructure.admin_desk import _variant_infos, money

    ls = list(order.lines.filter(status="active"))
    infos = _variant_infos({l.product_variant_id for l in ls})
    items, total = [], Decimal(0)
    for l in ls:
        info = infos.get(l.product_variant_id)
        net = l.unit_price_amount * l.quantity - l.discount_amount + l.tax_amount
        total += net
        items.append({"name": info.name if info else "—", "size": info.size if info else "", "sku": info.sku if info else "", "qty": l.quantity,
                      "unit": money(l.unit_price_amount), "total": money(net)})
    got = _paid_by_order([order.id]).get(order.id, Decimal(0))
    d = orm.DeliveryAssignment.objects.filter(order=order).select_related("courier").first()
    return {"order": order, "items": items, "units": sum(i["qty"] for i in items), "total": money(total), "paid": money(got),
            "collect": money(max(total - got, Decimal(0))), "is_paid": total > 0 and got >= total, "address": _full_address(order), "delivery": d,
            "placed": timezone.localtime(order.placed_at) if order.placed_at else None, "printed": timezone.localtime()}
