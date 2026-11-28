"""
Savatlar → Tahlil: the cart funnel from real events, not cart statuses.

* Started   = carts that got a product in the period (CartAuditEntry item_added).
* Ordered   = those of them an order was placed from (OrderModel.cart_id -- the storefront clears a cart after checkout
              instead of converting it, so the order link is the truth); Delivered = that order reached the customer.
* Abandoned = an active cart with products, untouched for 24 h, no order -- grouped by age, because a 2-day-old cart is
              still winnable and a 2-month-old one is not.
* Reminders = `reminder_sent` events; "won back" = the cart produced an order within 7 days after the reminder.
Money: order totals (invoice_total_amount, else lines) for ordered carts; abandoned carts at today's prices.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone

from apps.cart.infrastructure import models as orm

ZERO = Decimal("0")
ABANDONED_AFTER_HOURS = 24
WIN_BACK_DAYS = 7
AGE_BUCKETS = ((1, 3, "1–3 kun"), (3, 7, "3–7 kun"), (7, 30, "7–30 kun"), (30, 10**6, "30+ kun"))
PERIODS = {"7": 7, "30": 30, "90": 90}


def _order_totals(order_ids) -> dict:
    from apps.ordering.infrastructure.models import OrderLineItemModel, OrderModel

    ids = list(order_ids)
    if not ids:
        return {}
    expr = ExpressionWrapper(F("unit_price_amount") * F("quantity") - F("discount_amount") + F("tax_amount"), output_field=DecimalField(max_digits=16, decimal_places=2))
    lines = dict(OrderLineItemModel.objects.filter(order_id__in=ids, status="active").values("order_id").annotate(t=Sum(expr)).values_list("order_id", "t"))
    out = {}
    for oid, invoice in OrderModel.objects.filter(pk__in=ids).values_list("id", "invoice_total_amount"):
        out[oid] = lines.get(oid) or invoice or ZERO
    return out


def build(days: int = 30) -> dict:
    from apps.cart.infrastructure.admin import _variant_cards
    from apps.ordering.infrastructure.models import OrderModel

    now = timezone.now()
    since = now - timedelta(days=days)
    tz_today = timezone.localtime(now).date()

    # ---- funnel
    adds = list(orm.CartAuditEntryModel.objects.filter(action="item_added", occurred_at__gte=since).values_list("cart_id", "occurred_at"))
    first_add: dict = {}
    for cid, at in adds:
        if cid not in first_add or at < first_add[cid]:
            first_add[cid] = at
    started = set(first_add)
    carts = {c["id"]: c for c in orm.CartModel.objects.filter(id__in=started).values("id", "customer_id", "source")}
    signed = {cid for cid, c in carts.items() if c["customer_id"]}
    orders = list(OrderModel.objects.exclude(status="draft").filter(cart_id__in=started).values("id", "cart_id", "status", "created_at"))
    by_cart: dict = {}
    for o in sorted(orders, key=lambda o: o["created_at"]):
        by_cart.setdefault(o["cart_id"], o)  # the first order placed from the cart
    ordered = set(by_cart)
    delivered = {cid for cid, o in by_cart.items() if o["status"] in ("delivered", "completed")}
    lost = {cid for cid, o in by_cart.items() if o["status"] in ("cancelled", "returned", "failed")}
    totals = _order_totals(o["id"] for o in by_cart.values())
    revenue = sum((totals.get(by_cart[c]["id"], ZERO) for c in delivered), ZERO)
    pipeline = sum((totals.get(by_cart[c]["id"], ZERO) for c in ordered - delivered - lost), ZERO)
    waits = sorted((by_cart[c]["created_at"] - first_add[c]).total_seconds() / 60 for c in ordered if by_cart[c]["created_at"] >= first_add[c])
    median_wait = round(waits[len(waits) // 2]) if waits else None

    def pct(a, b):
        return round(a * 100 / b, 1) if b else 0

    funnel = [
        {"key": "started", "label": "Savatga qo'shildi", "n": len(started), "pct": 100 if started else 0, "icon": "fa-cart-plus", "color": "#6366f1"},
        {"key": "signed", "label": "Akkaunt bilan", "n": len(signed), "pct": pct(len(signed), len(started)), "icon": "fa-user-check", "color": "#0ea5e9"},
        {"key": "ordered", "label": "Buyurtma berildi", "n": len(ordered), "pct": pct(len(ordered), len(started)), "icon": "fa-bag-shopping", "color": "#f59e0b"},
        {"key": "delivered", "label": "Yetkazildi", "n": len(delivered), "pct": pct(len(delivered), len(started)), "icon": "fa-circle-check", "color": "#16a34a"},
    ]

    # ---- daily series (Tashkent days): carts started vs orders placed from carts
    series_days = min(days, 30)
    labels, s_started, s_ordered = [], [], []
    started_by_day = defaultdict(int)
    for cid, at in first_add.items():
        started_by_day[timezone.localtime(at).date()] += 1
    ordered_by_day = defaultdict(int)
    for o in by_cart.values():
        ordered_by_day[timezone.localtime(o["created_at"]).date()] += 1
    for k in range(series_days - 1, -1, -1):
        d = tz_today - timedelta(days=k)
        labels.append(d.strftime("%d.%m"))
        s_started.append(started_by_day.get(d, 0))
        s_ordered.append(ordered_by_day.get(d, 0))
    peak = max(s_started + s_ordered + [1])

    # ---- abandoned now, by age
    stale = now - timedelta(hours=ABANDONED_AFTER_HOURS)
    all_ordered = set(OrderModel.objects.exclude(cart_id=None).values_list("cart_id", flat=True))
    live = list(orm.CartItemModel.objects.filter(status="active", cart__status="active", cart__updated_at__lt=stale)
                .values("cart_id", "product_variant_id", "quantity", "cart__updated_at", "cart__customer_id"))
    live = [i for i in live if i["cart_id"] not in all_ordered]
    cards = _variant_cards({i["product_variant_id"] for i in live})
    reminded_recent = set(orm.CartAuditEntryModel.objects.filter(action="reminder_sent", occurred_at__gte=now - timedelta(hours=24)).values_list("cart_id", flat=True))
    buckets = [{"label": label, "carts": set(), "value": ZERO, "reachable": set()} for _a, _b, label in AGE_BUCKETS]
    products: dict = defaultdict(lambda: {"units": 0, "carts": set(), "value": ZERO})
    for i in live:
        age = (now - i["cart__updated_at"]).total_seconds() / 86400
        price = (cards.get(i["product_variant_id"]) or {}).get("price") or ZERO
        for b, (lo, hi, _l) in zip(buckets, AGE_BUCKETS):
            if lo <= age < hi or (lo == 1 and age < 1):
                b["carts"].add(i["cart_id"])
                b["value"] += price * i["quantity"]
                if i["cart__customer_id"] and i["cart_id"] not in reminded_recent:
                    b["reachable"].add(i["cart_id"])
                break
        p = products[i["product_variant_id"]]
        p["units"] += i["quantity"]
        p["carts"].add(i["cart_id"])
        p["value"] += price * i["quantity"]
    # ---- the honest number: carts STARTED IN THIS PERIOD that are still waiting (no order), at today's prices.
    # The age buckets above cover every cart ever left (30+ day ones too), so comparing their total with the
    # period's orders overstated the loss.
    per_cart: dict = {}
    for i in live:
        if i["cart_id"] in started:
            r = per_cart.setdefault(i["cart_id"], {"value": ZERO, "lines": 0, "signed": bool(i["cart__customer_id"])})
            r["value"] += ((cards.get(i["product_variant_id"]) or {}).get("price") or ZERO) * i["quantity"]
            r["lines"] += 1
    lost_vals = sorted(r["value"] for r in per_cart.values())
    lost = {"carts": len(per_cart), "value": sum(lost_vals, ZERO),
            "guest_carts": sum(1 for r in per_cart.values() if not r["signed"]),
            "guest_value": sum((r["value"] for r in per_cart.values() if not r["signed"]), ZERO),
            "signed_carts": sum(1 for r in per_cart.values() if r["signed"]),
            "signed_value": sum((r["value"] for r in per_cart.values() if r["signed"]), ZERO),
            "single": sum(1 for r in per_cart.values() if r["lines"] == 1),
            "median": lost_vals[len(lost_vals) // 2] if lost_vals else ZERO}
    lost["guest_pct"] = round(lost["guest_carts"] * 100 / lost["carts"]) if lost["carts"] else 0
    lost["single_pct"] = round(lost["single"] * 100 / lost["carts"]) if lost["carts"] else 0

    ab_total = sum((b["value"] for b in buckets), ZERO)
    ab_lead = max((b["value"] for b in buckets), default=ZERO) or Decimal(1)
    age = [{"label": b["label"], "carts": len(b["carts"]), "value": b["value"], "reachable": len(b["reachable"]),
            "pct": max(3, int(b["value"] * 100 / ab_lead)) if b["value"] else 0} for b in buckets]
    winnable = [b for b in buckets[:3]]  # up to 30 days: worth a reminder
    remindable = set().union(*(b["reachable"] for b in winnable)) if winnable else set()
    top = sorted(((v, d) for v, d in products.items() if v in cards), key=lambda kv: -kv[1]["value"])[:6]  # deleted products are left out
    top_lead = top[0][1]["value"] if top and top[0][1]["value"] else Decimal(1)
    top_products = [{"name": (cards.get(v) or {}).get("name", "—"), "thumb": (cards.get(v) or {}).get("thumb"), "units": d["units"], "carts": len(d["carts"]),
                     "value": d["value"], "pct": max(4, int(d["value"] * 100 / top_lead))} for v, d in top]

    # ---- reminders → won back
    rem = list(orm.CartAuditEntryModel.objects.filter(action="reminder_sent", occurred_at__gte=since).values_list("cart_id", "occurred_at"))
    rem_orders = {}
    if rem:
        for o in OrderModel.objects.exclude(status="draft").filter(cart_id__in={c for c, _a in rem}).values("id", "cart_id", "created_at", "status"):
            rem_orders.setdefault(o["cart_id"], []).append(o)
    won, won_ids = set(), []
    for cid, at in rem:
        for o in rem_orders.get(cid, []):
            if at <= o["created_at"] <= at + timedelta(days=WIN_BACK_DAYS) and o["status"] not in ("cancelled", "returned", "failed"):
                if cid not in won:
                    won.add(cid)
                    won_ids.append(o["id"])
                break
    won_value = sum(_order_totals(won_ids).values(), ZERO)

    # ---- sources
    src_names = {"web": "Sayt", "mobile": "Mobil", "pos": "POS", "api": "Telegram bot / API"}
    src = defaultdict(lambda: [0, 0])
    for cid, c in carts.items():
        src[c["source"]][0] += 1
        if cid in ordered:
            src[c["source"]][1] += 1
    sources = sorted(({"label": src_names.get(k, k), "carts": v[0], "ordered": v[1], "rate": pct(v[1], v[0]), "share": pct(v[0], len(carts))}
                      for k, v in src.items()), key=lambda r: -r["carts"])

    return {
        "days": days, "funnel": funnel,
        "kpi": {"started": len(started), "conversion": pct(len(ordered), len(started)), "abandon_rate": round(100 - pct(len(ordered), len(started)), 1) if started else 0,
                "revenue": revenue, "pipeline": pipeline, "median_wait": median_wait, "signed": pct(len(signed), len(started)),
                "guest_conversion": pct(len(ordered - signed), len(started - signed)), "signed_conversion": pct(len(ordered & signed), len(signed))},
        "series": {"labels": labels, "started": s_started, "ordered": s_ordered, "peak": peak,
                   "bars": [{"label": l, "a": a, "b": b, "ha": round(a * 100 / peak), "hb": round(b * 100 / peak)} for l, a, b in zip(labels, s_started, s_ordered)]},
        "lost": lost,
        "abandoned": {"age": age, "total": ab_total, "winnable": sum((b["value"] for b in buckets[:3]), ZERO), "old": buckets[-1]["value"], "carts": sum(a["carts"] for a in age), "remindable": len(remindable)},
        "top_products": top_products,
        "reminders": {"sent": len(rem), "won": len(won), "rate": pct(len(won), len({c for c, _a in rem})), "value": won_value},
        "sources": sources,
    }


def remindable_carts(limit: int = 200) -> list:
    """Abandoned carts (1–30 days) of signed-in customers that were not reminded in the last 24 h -- for "remind all"."""
    from apps.ordering.infrastructure.models import OrderModel

    now = timezone.now()
    all_ordered = set(OrderModel.objects.exclude(cart_id=None).values_list("cart_id", flat=True))
    reminded = set(orm.CartAuditEntryModel.objects.filter(action="reminder_sent", occurred_at__gte=now - timedelta(hours=24)).values_list("cart_id", flat=True))
    qs = (orm.CartModel.objects.filter(status="active", customer_id__isnull=False, updated_at__lt=now - timedelta(hours=ABANDONED_AFTER_HOURS),
                                       updated_at__gte=now - timedelta(days=30), items__status="active").distinct().order_by("-updated_at"))
    return [c for c in qs[: limit * 2] if c.id not in all_ordered and c.id not in reminded][:limit]
