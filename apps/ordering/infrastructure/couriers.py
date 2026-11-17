"""
Couriers (Dashboard → Buyurtmalar → Kuryerlar): who delivers, how they are doing and what cash they hold.

* A courier can be linked to a customer account (identity User) -- found by phone, name, @username or Telegram id.
  Linked couriers get every order assigned to them in their inbox and on Telegram (notify kind `courier_assigned`).
* Stats come from DeliveryAssignment + the order status history: active / on the road / delivered (period, today),
  average time from assignment to delivery, courier fees, and the cash in hand = what the courier collected for
  delivered orders (goods + delivery − succeeded online payments) and has not handed in yet.
* Settling cash only stamps the assignments (cash_settled_at); it never touches the order or the payments.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum
from django.utils import timezone

from apps.ordering.infrastructure import models as orm

ZERO = Decimal("0")
ACTIVE = ("confirmed", "processing", "shipped")
DONE = ("delivered", "completed")


def _line_total():
    return ExpressionWrapper(F("unit_price_amount") * F("quantity") - F("discount_amount") + F("tax_amount"),
                             output_field=DecimalField(max_digits=16, decimal_places=2))


def collect_amounts(order_ids) -> dict:
    """order id -> cash the courier collects at the door (goods + delivery − succeeded non-cash payments)."""
    ids = list(order_ids)
    if not ids:
        return {}
    from apps.ordering.infrastructure.admin_delivery import _paid_by_order

    goods = dict(orm.OrderLineItemModel.objects.filter(order_id__in=ids, status="active").values("order_id")
                 .annotate(t=Sum(_line_total())).values_list("order_id", "t"))
    shipping = dict(orm.OrderModel.objects.filter(pk__in=ids).values_list("id", "shipping_amount"))
    paid = _paid_by_order(ids)
    return {i: max((goods.get(i) or ZERO) + (shipping.get(i) or ZERO) - paid.get(i, ZERO), ZERO) for i in ids}


def _delivered_at(order_ids) -> dict:
    rows = (orm.OrderStatusHistoryEntryModel.objects.filter(order_id__in=list(order_ids), to_status="delivered")
            .values_list("order_id", "changed_at"))
    out: dict = {}
    for oid, at in rows:
        out[oid] = max(out.get(oid, at), at)
    return out


def stats(couriers, days: int = 30) -> dict:
    """courier id -> {active, road, delivered, today, avg_minutes, fees, cash, cash_orders, last}."""
    ids = [c.id for c in couriers]
    out = {cid: {"active": 0, "road": 0, "delivered": 0, "today": 0, "avg_minutes": None, "fees": ZERO, "cash": ZERO,
                 "cash_orders": 0, "last": None, "lifetime": 0} for cid in ids}
    if not ids:
        return out
    now = timezone.now()
    since = now - timedelta(days=days)
    today = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = list(orm.DeliveryAssignment.objects.filter(courier_id__in=ids)
                .values("courier_id", "order_id", "order__status", "fee", "assigned_at", "created_at", "cash_settled_at"))
    done_ids = [r["order_id"] for r in rows if r["order__status"] in DONE]
    delivered = _delivered_at(done_ids)
    unsettled = [r["order_id"] for r in rows if r["order__status"] in DONE and not r["cash_settled_at"]]
    cash = collect_amounts(unsettled)
    durations = defaultdict(list)
    for r in rows:
        s = out[r["courier_id"]]
        st = r["order__status"]
        if st in ACTIVE:
            s["active"] += 1
            if st == "shipped":
                s["road"] += 1
        if st in DONE:
            s["lifetime"] += 1
            at = delivered.get(r["order_id"])
            if at and (s["last"] is None or at > s["last"]):
                s["last"] = at
            if at and at >= since:
                s["delivered"] += 1
                s["fees"] += r["fee"] or ZERO
                start = r["assigned_at"] or r["created_at"]
                if start and at > start:
                    durations[r["courier_id"]].append((at - start).total_seconds() / 60)
            if at and at >= today:
                s["today"] += 1
            if not r["cash_settled_at"]:
                amount = cash.get(r["order_id"], ZERO)
                if amount > 0:
                    s["cash"] += amount
                    s["cash_orders"] += 1
    for cid, values in durations.items():
        out[cid]["avg_minutes"] = round(sum(values) / len(values))
    return out


def duration_text(minutes) -> str:
    if minutes is None:
        return "—"
    if minutes < 60:
        return f"{minutes} daq"
    if minutes < 60 * 24:
        return f"{minutes // 60} soat {minutes % 60} daq" if minutes % 60 else f"{minutes // 60} soat"
    return f"{minutes // (60 * 24)} kun {minutes % (60 * 24) // 60} soat"


def recent(courier, limit: int = 15) -> list[dict]:
    """The courier's latest deliveries for the courier card."""
    from apps.ordering.infrastructure.admin_desk import money, status_style

    rows = list(orm.DeliveryAssignment.objects.filter(courier=courier).select_related("order").order_by("-assigned_at", "-created_at")[:limit])
    ids = [r.order_id for r in rows]
    cash, delivered = collect_amounts(ids), _delivered_at(ids)
    out = []
    for r in rows:
        o = r.order
        at = delivered.get(o.id)
        out.append({"number": o.order_number, "url": f"/django-admin/ordering/ordermodel/{o.id}/change/", "status": status_style(o.status),
                    "city": o.shipping_city, "address": ", ".join(p for p in (o.shipping_line1, o.shipping_city) if p),
                    "collect": money(cash.get(o.id, ZERO)), "fee": money(r.fee) if r.fee is not None else "—",
                    "assigned": timezone.localtime(r.assigned_at).strftime("%d.%m %H:%M") if r.assigned_at else "",
                    "delivered": timezone.localtime(at).strftime("%d.%m %H:%M") if at else "",
                    "minutes": duration_text(round((at - (r.assigned_at or r.created_at)).total_seconds() / 60)) if at and (r.assigned_at or r.created_at) and at > (r.assigned_at or r.created_at) else "—",
                    "settled": bool(r.cash_settled_at), "done": o.status in DONE})
    return out


def settle_cash(courier, by: str) -> tuple[int, Decimal]:
    """The courier handed in the cash: stamp every delivered, unsettled assignment. Returns (orders, amount)."""
    rows = list(orm.DeliveryAssignment.objects.filter(courier=courier, order__status__in=DONE, cash_settled_at__isnull=True)
                .values_list("id", "order_id"))
    if not rows:
        return 0, ZERO
    amount = sum(collect_amounts([o for _i, o in rows]).values(), ZERO)
    orm.DeliveryAssignment.objects.filter(pk__in=[i for i, _o in rows]).update(cash_settled_at=timezone.now(), cash_settled_by=by[:150])
    return len(rows), amount


# ---------------------------------------------------------------- linking to a user account


def find_users(term: str, limit: int = 8) -> list[dict]:
    """Accounts matching a phone, name, @username or Telegram id -- for the "link an account" picker."""
    from apps.identity.infrastructure.models import User

    term = (term or "").strip().lstrip("@")
    if len(term) < 2:
        return []
    digits = "".join(ch for ch in term if ch.isdigit())
    q = Q(full_name__icontains=term) | Q(username__iexact=term) | Q(telegram_username__iexact=term)
    if len(digits) >= 4:
        q |= Q(phone_number__contains=digits[-9:])
    if digits and digits == term and len(digits) >= 6:
        q |= Q(telegram_user_id=int(digits))
    taken = dict(orm.Courier.objects.exclude(user=None).values_list("user_id", "code"))
    out = []
    for u in User.objects.filter(q).order_by("full_name")[:limit]:
        out.append({"id": str(u.id), "name": u.full_name or "—", "phone": u.phone_number or "", "username": u.telegram_username or u.username or "",
                    "telegram": bool(u.telegram_user_id), "courier": taken.get(u.id, "")})
    return out


def normalize_phone(raw: str) -> str:
    """'90 123 45 67', '8 90…', '998901234567', '+998 (90) 123-45-67' → '+998901234567'; '' when it isn't an Uzbek mobile number."""
    from apps.identity.domain.phone import parse_uz_phone

    return parse_uz_phone(raw)


def account_for_phone(phone: str):
    """The active customer account registered with this phone, if exactly one exists."""
    from apps.identity.infrastructure.models import User

    phone = normalize_phone(phone)
    if not phone:
        return None
    users = list(User.objects.filter(phone_number=phone)[:2])  # default manager hides soft-deleted accounts
    return users[0] if len(users) == 1 else None


def auto_link_account(user) -> "orm.Courier | None":
    """
    A courier entered by the admin before they had an account gets it the moment someone signs up
    (site, bot, Mini App) with the courier's phone -- no second trip to the dashboard.
    """
    from apps.ordering.infrastructure import models as orm

    phone = normalize_phone(getattr(user, "phone_number", "") or "")
    if not phone or orm.Courier.objects.filter(user=user).exists():
        return None
    courier = orm.Courier.objects.filter(user__isnull=True, is_active=True, phone=phone).first()
    if courier is None:
        return None
    link_user(courier, user)
    courier.save(update_fields=["user", "name", "phone", "telegram_username", "updated_at"])
    return courier


def connect_link() -> str:
    """The shop bot link a courier opens to sign in with their phone (which links the account automatically)."""
    from django.conf import settings

    username = (getattr(settings, "TELEGRAM_BOT_USERNAME", "") or "").lstrip("@")
    return f"https://t.me/{username}" if username else ""


def link_user(courier, user) -> list[str]:
    """Attach the account and fill the courier's empty contact fields from it. Returns the fields filled."""
    filled = []
    courier.user = user
    if user is not None:
        for field, value in (("name", user.full_name), ("phone", user.phone_number), ("telegram_username", user.telegram_username)):
            if value and not getattr(courier, field):
                setattr(courier, field, value)
                filled.append(field)
    return filled


def notify_assignment(assignment) -> bool:
    """Tell a linked courier about an order just assigned to them (inbox + Telegram). False when not linked."""
    courier = assignment.courier
    if courier is None or not courier.user_id:
        return False
    from apps.notifications.infrastructure.notify import notify
    from apps.ordering.infrastructure.admin_desk import money

    o = assignment.order
    collect = collect_amounts([o.id]).get(o.id, ZERO)
    when = " ".join(p for p in (assignment.planned_date.strftime("%d.%m.%Y") if assignment.planned_date else "", assignment.time_slot) if p)
    if o.shipping_latitude is not None and o.shipping_longitude is not None:  # the button opens the route in Yandex Maps
        link = f"https://yandex.uz/maps/?rtext=~{o.shipping_latitude:.6f},{o.shipping_longitude:.6f}&rtt=auto"
    else:
        link = "/account/notifications"
    notify(courier.user_id, "courier_assigned", {
        "order": o.order_number, "address": ", ".join(p for p in (o.shipping_line1, o.shipping_line2, o.shipping_city) if p) or "—",
        "recipient": o.shipping_recipient_name or "—", "phone": o.shipping_phone or "—",
        "collect": f"{money(collect)} so'm" if collect > 0 else "to'langan", "when": when or "—", "note": assignment.note or "—",
    }, link=link, dedupe_key=f"courier_assigned:{o.id}:{courier.id}:{int((assignment.assigned_at or timezone.now()).timestamp())}")
    return True
