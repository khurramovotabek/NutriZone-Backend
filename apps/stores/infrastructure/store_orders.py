"""
Online orders handled by a branch -- pickup at a store, or a delivery the dispatcher hands to a branch.

* `pickup_options(lines, lat, lng)`  -- active branches ranked for a cart: every item in stock first, then nearest.
* `assign(order, store, by)`        -- the branch that handles an order (pickup at checkout, or the dispatcher's choice).
                                      Moves a live reservation to that branch and tells the branch owner (bell + Telegram).
* `orders_for(store)` / `act(...)`  -- the branch owner's order list and the steps they may take
                                      (accept → pack → ready / handed to courier → picked up / delivered, or hand back),
                                      each through the Ordering lifecycle services, stock leaving THIS branch.

`OrderModel.fulfilment_method` / `fulfilment_store_id` live beside the Order aggregate (written only here and at checkout).
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone

from apps.stores.infrastructure.models import Store, StoreKind, StoreStatus

logger = logging.getLogger("nutrizone.app")

ACTIVE_FOR_STORE = ("pending_payment", "confirmed", "processing", "shipped")
# status → steps the branch may take (action, label for delivery, label for pickup)
STEPS = {
    "pending_payment": [("confirm", "Qabul qilish", "Qabul qilish")],
    "confirmed": [("start_processing", "Yig'ishni boshlash", "Yig'ishni boshlash")],
    "processing": [("ship", "Kuryerga topshirildi", "Olib ketishga tayyor")],
    "shipped": [("deliver", "Yetkazildi", "Mijoz olib ketdi")],
}
HAND_BACK_FROM = ("pending_payment", "confirmed", "processing")
STATUS_LABELS = {
    "pending_payment": "Yangi", "confirmed": "Qabul qilingan", "processing": "Yig'ilmoqda", "shipped": "Yo'lda",
    "delivered": "Yetkazildi", "completed": "Yakunlangan", "cancelled": "Bekor qilingan", "returned": "Qaytarilgan",
}
PICKUP_LABELS = {**STATUS_LABELS, "shipped": "Olib ketishga tayyor", "delivered": "Olib ketildi"}


class StoreOrderError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------- pickup options


def pickup_options(lines: list[tuple], lat: float | None = None, lng: float | None = None, lang: str = "uz") -> list[dict]:
    """lines = [(variant_id, qty)] → active branches: has_all (every unit free), missing units, distance, open now."""
    from apps.geo.infrastructure.gateways.geocoder import haversine_km
    from apps.stores.infrastructure.models import StoreProductStock

    ids = [vid for vid, _ in lines]
    stores = list(Store.objects.filter(kind=StoreKind.STORE, status=StoreStatus.ACTIVE, pickup_enabled=True))
    free: dict = {}
    for sid, vid, q, r in StoreProductStock.objects.filter(store__in=stores, product_variant_id__in=ids).values_list("store_id", "product_variant_id", "quantity", "reserved_quantity"):
        free[(sid, vid)] = max(q - r, 0)
    out = []
    for s in stores:
        missing = sum(max(qty - free.get((s.id, vid), 0), 0) for vid, qty in lines)
        km = haversine_km(lat, lng, s.latitude, s.longitude) if lat is not None and lng is not None and s.latitude is not None else None
        out.append({
            "id": str(s.id), "name": s.name, "slug": s.slug, "address": ", ".join(x for x in (s.address, s.district, s.city) if x),
            "latitude": s.latitude, "longitude": s.longitude, "phone": (s.phone_numbers or [""])[0] if s.phone_numbers else "",
            "has_all": missing == 0, "missing_units": missing, "distance_km": round(km, 1) if km is not None else None,
            "is_open_now": s.is_open_now(), "today": _today_hours(s),
        })
    out.sort(key=lambda o: (not o["has_all"], o["distance_km"] if o["distance_km"] is not None else 1e9, o["name"]))
    return out


def _today_hours(store: Store) -> str:
    today = store.today_hours()
    return "" if today.get("closed") else f"{today.get('open', '')}–{today.get('close', '')}".strip("–")


def pickup_store(store_id, lines: list[tuple]) -> Store:
    """The branch a pickup order may go to: active, a real branch, every item free there."""
    store = Store.objects.filter(pk=store_id, kind=StoreKind.STORE, status=StoreStatus.ACTIVE, pickup_enabled=True).first()
    if store is None:
        raise StoreOrderError("PICKUP_STORE_UNAVAILABLE", "This store can't take pickup orders right now.")
    option = next((o for o in pickup_options(lines) if o["id"] == str(store.id)), None)
    if option is None or not option["has_all"]:
        raise StoreOrderError("PICKUP_STORE_OUT_OF_STOCK", "Not every item is in stock at this store -- choose another store or delivery.")
    return store


def pickup_snapshot(store: Store, recipient_name: str, phone: str | None) -> dict:
    """The "shipping address" of a pickup order: the branch itself (the order desk, receipts and Telegram show it)."""
    return {
        "recipient_name": recipient_name, "phone": phone, "line1": (f"Olib ketish: {store.name}")[:255],
        "line2": (", ".join(x for x in (store.address, store.district) if x) or None), "city": store.city or "Toshkent", "country_code": "UZ",
        "postal_code": None, "latitude": store.latitude, "longitude": store.longitude,
    }


# ---------------------------------------------------------------- assignment


def _order_lines(order_row) -> list[tuple]:
    return [(l.product_variant_id, l.quantity) for l in order_row.lines.filter(status="active")]


@transaction.atomic
def assign(order_row, store: Store | None, by: str = "", method: str | None = None, notify_owner: bool = True) -> None:
    """Hand an order to a branch (None = back to the main warehouse); a live reservation moves with it."""
    from apps.ordering.infrastructure.models import OrderModel
    from apps.stores.infrastructure import online_fulfilment

    if store is not None and (store.kind != StoreKind.STORE or store.status != StoreStatus.ACTIVE):
        raise StoreOrderError("STORE_UNAVAILABLE", "Only an active branch can take orders.")
    from apps.stores.infrastructure.models import StoreOrderLog

    previous = order_row.fulfilment_store_id
    fields = {"fulfilment_store_id": store.id if store else None, "store_assigned_at": timezone.now() if store else None}
    if method:
        fields["fulfilment_method"] = method
    OrderModel.objects.filter(pk=order_row.pk).update(**fields)
    for k, v in fields.items():
        setattr(order_row, k, v)
    if order_row.status in ("confirmed", "processing") and previous != fields["fulfilment_store_id"]:
        online_fulfilment.release(order_row.order_number, actor=by, note="Order moved to another location")
        online_fulfilment.reserve(order_row.order_number, _order_lines(order_row), actor=by)
    if store is not None and previous != store.id:
        StoreOrderLog.objects.create(store=store, order_number=order_row.order_number, event=StoreOrderLog.ASSIGNED,
                                     method=fields.get("fulfilment_method") or order_row.fulfilment_method or "delivery", actor=(by or "")[:150])
    if store is not None and notify_owner:
        transaction.on_commit(lambda: _notify_owner(store.pk, order_row.pk))


def assigned_store(order_number: str) -> Store | None:
    from apps.ordering.infrastructure.models import OrderModel

    sid = OrderModel.objects.filter(order_number=order_number).values_list("fulfilment_store_id", flat=True).first()
    return Store.objects.filter(pk=sid, status=StoreStatus.ACTIVE).first() if sid else None


def _order_total(order_row) -> Decimal:
    expr = ExpressionWrapper(F("unit_price_amount") * F("quantity") - F("discount_amount") + F("tax_amount"), output_field=DecimalField(max_digits=16, decimal_places=2))
    return order_row.lines.filter(status="active").aggregate(t=Sum(expr))["t"] or Decimal(0)


def _notify_owner(store_id, order_pk) -> None:
    """New order for the branch: bell + Telegram (the owner's linked Telegram) with a link to the store's order page."""
    from apps.notifications.infrastructure.notify import fmt, notify
    from apps.ordering.infrastructure.models import OrderModel

    try:
        store = Store.objects.get(pk=store_id)
        order = OrderModel.objects.get(pk=order_pk)
        if not store.owner_id:
            return
        units = sum(q for _v, q in _order_lines(order))
        method = {"pickup": {"uz": "olib ketish", "ru": "самовывоз", "en": "pickup"}, "delivery": {"uz": "yetkazib berish", "ru": "доставка", "en": "delivery"}}[order.fulfilment_method or "delivery"]
        notify(store.owner_id, "store_order_new", {"order": order.order_number, "store": store.name, "units": units, "amount": fmt(_order_total(order)),
                                                   "i18n": {k: {"method": v} for k, v in method.items()}},
               link=f"/profile/store/orders?o={order.order_number}", dedupe_key=f"store_order:{store.pk}:{order.pk}")
    except Exception:  # noqa: BLE001 - a missed alert never breaks the assignment
        logger.exception("store orders: owner notification failed for %s", order_pk)


# ---------------------------------------------------------------- the branch's view


def _payload(o, lines_by_order: dict, products: dict) -> dict:
    pickup = o.fulfilment_method == "pickup"
    labels = PICKUP_LABELS if pickup else STATUS_LABELS
    steps = [{"action": a, "label": lp if pickup else ld} for a, ld, lp in STEPS.get(o.status, [])] if not o.is_archived else []
    if o.status in HAND_BACK_FROM:
        steps.append({"action": "hand_back", "label": "Omborga qaytarish"})
    lines = []
    total = Decimal(0)
    for l in lines_by_order.get(o.pk, []):
        net = l.unit_price_amount * l.quantity - l.discount_amount + l.tax_amount
        total += net
        info = products.get(l.product_variant_id)
        lines.append({"variant_id": str(l.product_variant_id), "name": info.name if info else str(l.product_variant_id), "sku": info.sku if info else "",
                      "image": (info.image_url or "") if info else "", "quantity": l.quantity, "total": str(net)})
    return {
        "number": o.order_number, "status": o.status, "status_label": labels.get(o.status, o.status), "method": o.fulfilment_method or "delivery",
        "placed_at": (o.placed_at or o.created_at).isoformat(), "assigned_at": o.store_assigned_at.isoformat() if o.store_assigned_at else None,
        "customer": {"name": o.shipping_recipient_name, "phone": o.shipping_phone or ""},
        "address": {"line1": o.shipping_line1, "line2": o.shipping_line2 or "", "city": o.shipping_city, "latitude": o.shipping_latitude, "longitude": o.shipping_longitude},
        "comment": o.customer_comment or "", "lines": lines, "units": sum(l["quantity"] for l in lines), "total": str(total), "currency": o.currency,
        "steps": steps,
    }


def orders_for(store: Store, scope: str = "active", query: str = "") -> dict:
    from apps.ordering.infrastructure.models import OrderLineItemModel, OrderModel
    from apps.stores.infrastructure.stock_service import variant_infos

    qs = OrderModel.objects.filter(fulfilment_store_id=store.id)
    counts = {"active": qs.filter(status__in=ACTIVE_FOR_STORE, is_archived=False).count(), "new": qs.filter(status="pending_payment").count(),
              "ready": qs.filter(status="shipped").count(), "done": qs.filter(status__in=("delivered", "completed")).count()}
    if scope == "active":
        qs = qs.filter(status__in=ACTIVE_FOR_STORE, is_archived=False)
    elif scope == "done":
        qs = qs.filter(status__in=("delivered", "completed", "cancelled", "returned"))
    if query:
        from django.db.models import Q

        qs = qs.filter(Q(order_number__icontains=query) | Q(shipping_recipient_name__icontains=query) | Q(shipping_phone__icontains=query))
    rows = list(qs.order_by("-placed_at", "-created_at")[:100])
    lines = list(OrderLineItemModel.objects.filter(order__in=rows, status="active"))
    by_order: dict = {}
    for l in lines:
        by_order.setdefault(l.order_id, []).append(l)
    products = variant_infos({l.product_variant_id for l in lines}, "uz")
    today = timezone.localdate()
    done_today = OrderModel.objects.filter(fulfilment_store_id=store.id, status__in=("delivered", "completed"), updated_at__date=today)
    return {"orders": [_payload(o, by_order, products) for o in rows], "counts": counts,
            "today": {"done": done_today.count(), "revenue": str(sum((_order_total(o) for o in done_today), Decimal(0)))}}


def act(store: Store, order_number: str, action: str, actor_id=None, actor_label: str = "", reason: str = "") -> dict:
    """One step on an order this branch handles, through the Ordering services (stock leaves THIS branch on ship)."""
    from apps.ordering.application.services import lifecycle as lc
    from apps.ordering.infrastructure.composition import build_ordering_service_context
    from apps.ordering.infrastructure.models import OrderModel
    from apps.ordering.infrastructure.repositories import DjangoOrderRepository

    order = OrderModel.objects.filter(order_number=order_number, fulfilment_store_id=store.id).first()
    if order is None:
        raise StoreOrderError("ORDER_NOT_FOUND", "This order is not handled by your store.")
    label = f"{store.name}" + (f" — {actor_label}" if actor_label else "")
    if action == "hand_back":
        if order.status not in HAND_BACK_FROM:
            raise StoreOrderError("CANNOT_HAND_BACK", "This order can't be handed back at this stage.")
        from apps.stores.infrastructure.models import StoreOrderLog

        StoreOrderLog.objects.create(store=store, order_number=order.order_number, event=StoreOrderLog.HANDED_BACK, method=order.fulfilment_method or "delivery",
                                     reason=reason.strip()[:300], actor=label[:150])
        assign(order, None, by=label, notify_owner=False)
        note = f"[{timezone.localtime().strftime('%d.%m %H:%M')}] {store.name} omborga qaytardi" + (f": {reason.strip()[:300]}" if reason.strip() else "")
        OrderModel.objects.filter(pk=order.pk).update(note=((order.note + "\n") if order.note else "") + note)
        _post_hand_back(order.pk, store.name, reason)
        return {"handed_back": True}
    allowed = [a for a, *_ in STEPS.get(order.status, [])]
    if action not in allowed:
        raise StoreOrderError("STEP_NOT_ALLOWED", "This step is not possible in the current status. Refresh the page.")
    services = {"confirm": lc.ConfirmOrder, "start_processing": lc.StartOrderProcessing, "ship": lc.ShipOrder, "deliver": lc.DeliverOrder}
    ctx = build_ordering_service_context(actor_id=actor_id, actor_label=label)
    service = services[action](DjangoOrderRepository(), ctx)
    if action == "ship":
        service.execute(order.id, store_id=store.id)
    else:
        service.execute(order.id)
    found = orders_for(store, "all", order.order_number)["orders"]
    return found[0] if found else {}


def _post_hand_back(order_pk, store_name: str, reason: str) -> None:
    """The dispatcher learns a branch handed an order back (staff Telegram channel)."""
    from html import escape

    from django.conf import settings

    from apps.ordering.infrastructure.models import OrderModel

    chat = getattr(settings, "TELEGRAM_ORDERS_CHAT_ID", None)
    order = OrderModel.objects.filter(pk=order_pk).first()
    if not chat or order is None:
        return

    def send():
        try:
            from apps.notifications.infrastructure import composition

            text = f"↩️ <b>{escape(store_name)}</b> {escape(order.order_number)} buyurtmasini omborga qaytardi" + (f"\n«{escape(reason[:300])}»" if reason else "")
            base = (getattr(settings, "PUBLIC_BASE_URL", "") or "").rstrip("/")
            kb = [[{"text": "Buyurtmani ochish", "url": f"{base}/django-admin/ordering/ordermodel/{order.pk}/change/"}]] if base.startswith("https://") else []
            composition.build_orders_telegram_gateway().send_message_with_keyboard(str(chat), text, kb)
        except Exception:  # noqa: BLE001
            logger.exception("store orders: hand-back alert failed")

    transaction.on_commit(send)

