"""
Business analytics -- ONE read-only calculation feeding both the dashboard "Analitika" page and the
NutriZoneAnalyticsBot Telegram reports, so the two can never disagree.

Every figure comes from data that already exists; nothing here writes.

Definitions (one of each, used everywhere below):
    revenue (sof tushum)  store tills: sales_reports.rows() "revenue" (lines − basket discount + delivery − returns,
                          coins included), by completion time
                          + online: active order lines (price × qty − discount + tax) of orders that are delivered /
                          completed, by the time the customer placed them (online_orders_report's formula)
    purchases             completed till receipts + delivered/completed online orders (what the revenue came from)
    pipeline              online orders still on their way (pending payment … shipped) -- NOT revenue yet
    lost                  cancelled / returned / failed online orders -- never revenue
    COGS                  units sold × best known purchase cost (count_service.cost_info: latest receipt cost, else the
                          catalogue cost price). Units whose cost is unknown (only the selling price is known) are left
                          out and reported as "coverage"; gross profit is shown only when coverage is high enough.
Not available (no data source exists): operating expenses, therefore net profit.

All periods are Asia/Tashkent wall-clock; a running period (today, this month …) is compared with the same elapsed
span of the previous one (today 00:00–15:40 vs yesterday 00:00–15:40), never with a full day.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

logger = logging.getLogger("nutrizone.analytics")

TZ = ZoneInfo("Asia/Tashkent")
ZERO = Decimal("0")
EARNED = ("delivered", "completed")
PIPELINE = ("pending_payment", "confirmed", "processing", "shipped")
LOST = ("cancelled", "returned", "failed")
RELIABLE_COST = ("receipt", "catalog")
PROFIT_MIN_COVERAGE = 90  # % of revenue that must have a known purchase cost before gross profit is shown
EXPIRY_DAYS = 30
SLOW_DAYS = 30
ONLINE_KEY = "online"

STATUS_LABELS = {
    "pending_payment": "To'lov kutilmoqda", "confirmed": "Tasdiqlangan", "processing": "Yig'ilmoqda", "shipped": "Yo'lda",
    "delivered": "Yetkazilgan", "completed": "Yakunlangan", "cancelled": "Bekor qilingan", "returned": "Qaytarilgan", "failed": "Muvaffaqiyatsiz",
}
METHOD_LABELS = {
    "cash": "Naqd", "uzcard": "Uzcard", "humo": "Humo", "click": "Click", "payme": "Payme", "uzum": "Uzum",
    "coins": "NutriZone Coins", "cod": "Naqd (yetkazishda)", "card": "Karta",
}


# ---------------------------------------------------------------- periods


@dataclass(frozen=True)
class Period:
    key: str
    title: str          # "Bugun", "O'tgan hafta" …
    start: datetime
    end: datetime       # exclusive; "now" for a running period
    prev_start: datetime
    prev_end: datetime
    compare_label: str  # "kechaga nisbatan" …
    running: bool       # the period is not over yet (figures are "so far")

    @property
    def first_day(self) -> date:
        return self.start.astimezone(TZ).date()

    @property
    def last_day(self) -> date:
        return (self.end - timedelta(microseconds=1)).astimezone(TZ).date()

    @property
    def days(self) -> int:
        return (self.last_day - self.first_day).days + 1

    def range_text(self) -> str:
        a, b = self.first_day, self.last_day
        text = a.strftime("%d.%m.%Y") if a == b else f"{a.strftime('%d.%m')}–{b.strftime('%d.%m.%Y')}"
        if self.running:
            text += f" · {self.end.astimezone(TZ).strftime('%H:%M')} holatiga"
        return text


PERIODS = ("today", "yesterday", "7d", "30d", "this_month", "week", "month", "custom")
PERIOD_TITLES = {"today": "Bugun", "yesterday": "Kecha", "7d": "So'nggi 7 kun", "30d": "So'nggi 30 kun", "this_month": "Shu oy",
                 "week": "O'tgan hafta", "month": "O'tgan oy", "custom": "Tanlangan davr"}


def _at(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=TZ)


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _prev_month_start(d: date) -> date:
    return _month_start(_month_start(d) - timedelta(days=1))


def period(key: str = "today", now: datetime | None = None, date_from=None, date_to=None) -> Period:
    now = (now or timezone.now()).astimezone(TZ)
    today = now.date()
    key = key if key in PERIODS else "today"

    def closed(a: date, b: date, prev_a: date, label: str) -> Period:
        start, end = _at(a), _at(b + timedelta(days=1))
        prev_start = _at(prev_a)
        return Period(key, PERIOD_TITLES[key], start, end, prev_start, prev_start + (end - start) if key != "month" else _at(a), label, False)

    if key == "today":
        start = _at(today)
        return Period(key, PERIOD_TITLES[key], start, now, start - timedelta(days=1), now - timedelta(days=1), "kechaga nisbatan (shu vaqtgacha)", True)
    if key == "yesterday":
        d = today - timedelta(days=1)
        return closed(d, d, d - timedelta(days=1), "oldingi kunga nisbatan")
    if key in ("7d", "30d"):
        n = 7 if key == "7d" else 30
        start = _at(today - timedelta(days=n - 1))
        prev_start = start - timedelta(days=n)
        return Period(key, PERIOD_TITLES[key], start, now, prev_start, prev_start + (now - start), f"oldingi {n} kunga nisbatan", True)
    if key == "this_month":
        start = _at(_month_start(today))
        prev_start = _at(_prev_month_start(today))
        prev_end = min(prev_start + (now - start), start)
        return Period(key, PERIOD_TITLES[key], start, now, prev_start, prev_end, "o'tgan oyning shu kunlariga nisbatan", True)
    if key == "week":  # the last full Monday–Sunday week
        monday = today - timedelta(days=today.weekday() + 7)
        return closed(monday, monday + timedelta(days=6), monday - timedelta(days=7), "oldingi haftaga nisbatan")
    if key == "month":  # the last full calendar month
        first = _prev_month_start(today)
        last = _month_start(today) - timedelta(days=1)
        return closed(first, last, _prev_month_start(first), "oldingi oyga nisbatan")
    # custom
    try:
        a, b = date.fromisoformat(str(date_from)), date.fromisoformat(str(date_to))
    except (TypeError, ValueError):
        return period("7d", now=now)
    if a > b:
        a, b = b, a
    a = max(a, b - timedelta(days=365))
    b = min(b, today)
    span = (b - a).days + 1
    return closed(a, b, a - timedelta(days=span), f"oldingi {span} kunga nisbatan")


def change(current, previous) -> dict:
    """{'pct': 12.4 | None, 'diff': current − previous, 'dir': up/down/flat/None} -- pct is None without a baseline (never ÷0)."""
    current, previous = Decimal(str(current or 0)), Decimal(str(previous or 0))
    diff = current - previous
    direction = "up" if diff > 0 else "down" if diff < 0 else "flat"
    pct = round(float(diff / previous * 100), 1) if previous else None
    if not previous and not current:
        direction = None
    return {"pct": pct, "diff": diff, "dir": direction}


def duration(minutes: int) -> str:
    minutes = int(minutes or 0)
    if minutes >= 1440:
        return f"{minutes // 1440} kun"
    if minutes >= 60:
        return f"{minutes // 60} soat"
    return f"{minutes} daqiqa"


# ---------------------------------------------------------------- raw data


def _pos_rows(start, end, store_ids=None):
    from apps.pos.infrastructure import sales_reports as rep

    qs = rep.closed_sales().filter(completed_at__gte=start, completed_at__lt=end)
    if store_ids is not None:  # one branch's view: its own tills only (the dashboard till sells for no branch)
        qs = qs.filter(channel="store", branch_id__in=list(store_ids))
    return rep.rows(qs)


def _online_orders(start, end, store_ids=None) -> list[dict]:
    from apps.ordering.infrastructure.models import OrderModel

    line_total = ExpressionWrapper(
        F("lines__unit_price_amount") * F("lines__quantity") - F("lines__discount_amount") + F("lines__tax_amount"),
        output_field=DecimalField(max_digits=16, decimal_places=2),
    )
    qs = OrderModel.objects.exclude(status="draft").filter(currency="UZS")
    if store_ids is not None:  # a branch sees the online orders assigned to it (pickup there / delivered from there)
        qs = qs.filter(fulfilment_store_id__in=list(store_ids))
    return list(
        qs.annotate(at=Coalesce("placed_at", "created_at")).filter(at__gte=start, at__lt=end)
        .annotate(amount=Sum(line_total, filter=Q(lines__status="active")), units=Sum("lines__quantity", filter=Q(lines__status="active")))
        .values("id", "order_number", "status", "at", "amount", "units", "customer_id", "fulfilment_store_id")
    )


def _base(start, end, store_ids=None) -> dict:
    pos = _pos_rows(start, end, store_ids)
    online = _online_orders(start, end, store_ids)
    kept = [r for r in pos if r["status"] in ("completed", "refunded")]
    earned = [o for o in online if o["status"] in EARNED]
    pos_rev = sum((r["revenue"] for r in kept), ZERO)
    online_rev = sum((o["amount"] or ZERO for o in earned), ZERO)
    purchases = sum(1 for r in kept if r["status"] == "completed") + len(earned)
    units = sum(r["units"] for r in kept) + sum(o["units"] or 0 for o in earned)
    return {
        "pos": pos, "kept": kept, "online": online, "earned": earned,
        "revenue": pos_rev + online_rev, "pos_revenue": pos_rev, "online_revenue": online_rev,
        "purchases": purchases, "units": units,
        "pipeline_value": sum((o["amount"] or ZERO for o in online if o["status"] in PIPELINE), ZERO),
        "pipeline_orders": sum(1 for o in online if o["status"] in PIPELINE),
        "lost_orders": sum(1 for o in online if o["status"] in LOST),
        "lost_value": sum((o["amount"] or ZERO for o in online if o["status"] in LOST), ZERO),
        "refunds_total": sum((r["returned"] for r in kept), ZERO),
        "refunds_count": sum(1 for r in kept if r["returned"] > 0),
        "discounts": sum((r["discount_amount"] for r in kept), ZERO),
        "delivery": sum((r["delivery_fee_amount"] for r in kept), ZERO),
        "gross_sales": sum((r["gross"] for r in kept), ZERO) + online_rev,
    }


# ---------------------------------------------------------------- products sold (+ cost)


def _sold_lines(base: dict) -> dict:
    """{key: {variant, product, units, revenue}} for the till receipts and earned online orders of a period."""
    from apps.ordering.infrastructure.models import OrderLineItemModel
    from apps.pos.infrastructure.models import SaleLineItemModel

    out: dict = {}

    def add(key, variant, product, units, revenue):
        a = out.setdefault(key, {"variant": variant, "product": product, "units": 0, "revenue": ZERO})
        a["units"] += units
        a["revenue"] += revenue

    sale_ids = [r["id"] for r in base["kept"]]
    if sale_ids:
        for r in (SaleLineItemModel.objects.filter(sale_id__in=sale_ids).values("product_variant_id", "product_id")
                  .annotate(q=Sum(F("quantity") - F("refunded_quantity")), rev=Sum(F("unit_price_amount") * (F("quantity") - F("refunded_quantity"))))):
            units = r["q"] or 0
            if units > 0:
                key = r["product_variant_id"] or ("p", r["product_id"])
                add(key, r["product_variant_id"], r["product_id"], units, r["rev"] or ZERO)
    loose = {k[1] for k in out if isinstance(k, tuple)}
    if loose:  # a till line recorded without its variant: attribute it to the product's only (or default) variant
        from apps.products.infrastructure.models import ProductVariant

        by_product: dict = defaultdict(list)
        for v in ProductVariant.objects.filter(product_id__in=loose).order_by("-is_default").values("id", "product_id", "is_default"):
            by_product[v["product_id"]].append(v)
        for pid in loose:
            vs = by_product.get(pid) or []
            pick = vs[0]["id"] if len(vs) == 1 or (vs and vs[0]["is_default"]) else None
            if pick:
                a = out.pop(("p", pid))
                add(pick, pick, pid, a["units"], a["revenue"])
    order_ids = [o["id"] for o in base["earned"]]
    if order_ids:
        for r in (OrderLineItemModel.objects.filter(order_id__in=order_ids, status="active").values("product_variant_id")
                  .annotate(q=Sum("quantity"), rev=Sum(F("unit_price_amount") * F("quantity") - F("discount_amount") + F("tax_amount")))):
            add(r["product_variant_id"], r["product_variant_id"], None, r["q"] or 0, r["rev"] or ZERO)
    return out


def _cost(lines: dict, revenue: Decimal) -> dict:
    from apps.stores.infrastructure.count_service import cost_info

    info = cost_info([a["variant"] for a in lines.values() if a["variant"]])
    cogs, covered = ZERO, ZERO
    for a in lines.values():
        cost, source = info.get(a["variant"], (ZERO, None)) if a["variant"] else (ZERO, None)
        if source in RELIABLE_COST and cost:
            cogs += cost * a["units"]
            covered += a["revenue"]
    line_revenue = sum((a["revenue"] for a in lines.values()), ZERO)
    coverage = int(round(covered / line_revenue * 100)) if line_revenue else None
    reliable = coverage is not None and coverage >= PROFIT_MIN_COVERAGE
    # Profit over the part of revenue whose cost is known, scaled to nothing: shown only when (almost) all of it is known.
    gross_profit = (covered - cogs) if reliable else None
    margin = round(float(gross_profit / covered * 100), 1) if reliable and covered else None
    return {"cogs": cogs if reliable else None, "gross_profit": gross_profit, "margin": margin, "coverage": coverage, "reliable": reliable}


def _names(lines: dict, keys) -> dict:
    from apps.products.infrastructure.models import ProductTranslation
    from apps.stores.infrastructure.stock_service import variant_infos

    infos = variant_infos([lines[k]["variant"] for k in keys if lines[k]["variant"]])
    out = {}
    missing_products = {lines[k]["product"] for k in keys if not lines[k]["variant"]}
    product_names: dict = {}
    for tr in ProductTranslation.objects.filter(product_id__in=missing_products).values("product_id", "locale_code", "name"):
        if tr["name"] and (tr["product_id"] not in product_names or tr["locale_code"] == "uz"):
            product_names[tr["product_id"]] = tr["name"]
    for k in keys:
        a = lines[k]
        info = infos.get(a["variant"]) if a["variant"] else None
        if info:
            out[k] = {"name": info.name, "size": info.size or "", "sku": info.sku, "image": info.image_url}
        else:
            out[k] = {"name": product_names.get(a["product"], "—"), "size": "", "sku": "", "image": None}
    return out


def top_products(lines: dict, limit: int = 8) -> list[dict]:
    top = sorted(lines, key=lambda k: (-lines[k]["revenue"], -lines[k]["units"]))[:limit]
    names = _names(lines, top)
    lead = lines[top[0]]["revenue"] if top else ZERO
    return [{**names[k], "units": lines[k]["units"], "revenue": lines[k]["revenue"],
             "share": int(lines[k]["revenue"] * 100 / lead) if lead else 0} for k in top]


# ---------------------------------------------------------------- sections


def _stores(cur: dict, prev: dict, store_ids=None) -> list[dict]:
    from apps.pos.infrastructure import sales_reports as rep
    from apps.stores.infrastructure.models import Store

    def group(base):
        g: dict = defaultdict(lambda: {"revenue": ZERO, "purchases": 0, "units": 0})
        for r in base["kept"]:
            a = g[rep.branch_key(r)]
            a["revenue"] += r["revenue"]
            a["purchases"] += r["status"] == "completed"
            a["units"] += r["units"]
        if base["earned"] or base["online_revenue"]:
            a = g[ONLINE_KEY]
            a["revenue"] += base["online_revenue"]
            a["purchases"] += len(base["earned"])
            a["units"] += sum(o["units"] or 0 for o in base["earned"])
        return g

    now_g, prev_g = group(cur), group(prev)
    keys = set(now_g) | set(prev_g)
    names = rep.store_names([k for k in keys if k != ONLINE_KEY])
    meta = {str(s["id"]): s for s in Store.objects.values("id", "color", "kind", "status")}
    # every active selling branch is listed, even with no sales (a silent branch is news too)
    for sid, s in meta.items():
        if s["kind"] == "store" and s["status"] == "active" and (store_ids is None or sid in {str(x) for x in store_ids}):
            keys.add(sid)
    names.update(rep.store_names([k for k in keys if k not in names and k != ONLINE_KEY]))
    out = []
    for k in keys:
        a, p = now_g.get(k, {"revenue": ZERO, "purchases": 0, "units": 0}), prev_g.get(k, {"revenue": ZERO, "purchases": 0, "units": 0})
        if k == ONLINE_KEY:
            name, color, kind = "Onlayn do'kon", "#6366F1", "online"
        elif k == rep.CENTRAL:
            name, color, kind = names.get(k, "Dashboard kassa"), rep.CENTRAL_COLOR, "central"
        else:
            m = meta.get(k, {})
            name, color, kind = names.get(k, "—"), m.get("color") or rep.CENTRAL_COLOR, m.get("kind") or "store"
        out.append({"key": k, "name": name, "color": color, "kind": kind, "revenue": a["revenue"], "purchases": a["purchases"], "units": a["units"],
                    "prev_revenue": p["revenue"], "change": change(a["revenue"], p["revenue"]),
                    "average": (a["revenue"] / a["purchases"]).quantize(Decimal("1")) if a["purchases"] else ZERO})
    out.sort(key=lambda s: (-s["revenue"], s["name"]))
    total = sum((s["revenue"] for s in out), ZERO)
    for i, s in enumerate(out, 1):
        s["rank"] = i
        s["share"] = round(float(s["revenue"] / total * 100), 1) if total else 0
    return out


def _payments(cur: dict) -> dict:
    """Store tills: the stored payment split (net of returns). Online: the captured provider payment of each earned order, else cash on delivery."""
    from apps.payment.infrastructure.models import PaymentModel

    amounts: dict = defaultdict(lambda: ZERO)
    counts: dict = defaultdict(int)
    for r in cur["kept"]:
        for m, v in r["split"].items():
            if v:
                amounts[m] += v
                counts[m] += 1
        if r["coins_kept"]:
            amounts["coins"] += r["coins_kept"]
            counts["coins"] += 1
    paid = {}
    if cur["earned"]:
        for p in PaymentModel.objects.filter(order_id__in=[o["id"] for o in cur["earned"]], status="succeeded").order_by("paid_at").values("order_id", "method", "provider"):
            paid[p["order_id"]] = p["method"] or p["provider"]
    for o in cur["earned"]:
        m = paid.get(o["id"], "cod")
        amounts[m] += o["amount"] or ZERO
        counts[m] += 1
    total = sum(amounts.values(), ZERO)
    rows = [{"code": m, "label": METHOD_LABELS.get(m, m.title()), "amount": v, "count": counts[m], "share": round(float(v / total * 100), 1) if total else 0}
            for m, v in amounts.items() if v]
    rows.sort(key=lambda x: -x["amount"])
    return {"rows": rows, "total": total}


def _orders(cur: dict, prev: dict) -> dict:
    from apps.ordering.infrastructure.models import OrderModel

    by_status: dict = defaultdict(int)
    for o in cur["online"]:
        by_status[o["status"]] += 1
    placed = len(cur["online"])
    prev_placed = len(prev["online"])
    cancelled = sum(1 for o in cur["online"] if o["status"] in ("cancelled", "failed"))
    prev_cancelled = sum(1 for o in prev["online"] if o["status"] in ("cancelled", "failed"))
    rate = round(cancelled / placed * 100, 1) if placed else 0.0
    prev_rate = round(prev_cancelled / prev_placed * 100, 1) if prev_placed else None
    # a spike = at least 3 cancellations and the rate doubled (or +10 points) vs a comparable period that had orders
    spike = bool(cancelled >= 3 and prev_rate is not None and (rate >= prev_rate * 2 or rate - prev_rate >= 10))
    backlog = dict(OrderModel.objects.filter(status__in=PIPELINE).values_list("status").annotate(n=Count("id")))
    return {
        "placed": placed, "prev_placed": prev_placed, "change": change(placed, prev_placed),
        "statuses": [{"code": s, "label": STATUS_LABELS.get(s, s), "count": by_status[s]} for s in (*PIPELINE, *EARNED, *LOST) if by_status.get(s)],
        "delivered": by_status.get("delivered", 0) + by_status.get("completed", 0),
        "cancelled": cancelled, "returned": by_status.get("returned", 0),
        "cancel_rate": rate, "prev_cancel_rate": prev_rate, "cancel_spike": spike,
        "backlog": [{"code": s, "label": STATUS_LABELS[s], "count": backlog.get(s, 0)} for s in PIPELINE if backlog.get(s)],
        "backlog_total": sum(backlog.values()),
        "pos_voided": sum(1 for r in cur["pos"] if r["status"] == "voided"),
    }


def _purchase_customers(start, end, store_ids=None) -> list:
    from apps.ordering.infrastructure.models import OrderModel
    from apps.pos.infrastructure.models import SaleModel

    sales = SaleModel.objects.filter(status__in=("completed", "refunded"), completed_at__gte=start, completed_at__lt=end, customer_id__isnull=False)
    orders = OrderModel.objects.filter(status__in=EARNED, customer_id__isnull=False)
    if store_ids is not None:
        sales = sales.filter(channel="store", branch_id__in=list(store_ids))
        orders = orders.filter(fulfilment_store_id__in=list(store_ids))
    ids = list(sales.values_list("customer_id", flat=True))
    ids += list(orders.annotate(at=Coalesce("placed_at", "created_at")).filter(at__gte=start, at__lt=end).values_list("customer_id", flat=True))
    return ids


def _customers(p: Period, cur: dict, store_ids=None) -> dict:
    from apps.identity.infrastructure.models import User
    from apps.ordering.infrastructure.models import OrderModel
    from apps.pos.infrastructure.models import SaleModel

    # sign-ups belong to no branch: a branch view leaves them out (None) rather than showing the company figure
    new = User.objects.filter(created_at__gte=p.start, created_at__lt=p.end).count() if store_ids is None else None
    prev_new = User.objects.filter(created_at__gte=p.prev_start, created_at__lt=p.prev_end).count() if store_ids is None else None
    purchases = _purchase_customers(p.start, p.end, store_ids)
    per: dict = defaultdict(int)
    for c in purchases:
        per[c] += 1
    buyers = set(per)
    earlier = set()
    if buyers:
        earlier = set(SaleModel.objects.filter(status__in=("completed", "refunded"), completed_at__lt=p.start, customer_id__in=buyers).values_list("customer_id", flat=True).distinct())
        earlier |= set(OrderModel.objects.filter(status__in=EARNED, customer_id__in=buyers).annotate(at=Coalesce("placed_at", "created_at"))
                       .filter(at__lt=p.start).values_list("customer_id", flat=True).distinct())
    repeat = {c for c in buyers if c in earlier or per[c] > 1}
    anonymous = sum(1 for r in cur["kept"] if r["status"] == "completed" and not r["customer_id"])
    return {
        "new": new, "new_change": change(new, prev_new) if new is not None else None, "buyers": len(buyers), "repeat": len(repeat),
        "first_time": len(buyers) - len(repeat),
        "repeat_share": round(len(repeat) / len(buyers) * 100) if buyers else None,
        "frequency": round(len(purchases) / len(buyers), 2) if buyers else None,
        "anonymous": anonymous,
    }


def _inventory(today: date, store_ids=None) -> dict:
    from apps.platform.infrastructure.dashboard_home import wms_low_stock
    from apps.stores.infrastructure import planning_service as plan
    from apps.stores.infrastructure.models import StockMovement, Store
    from apps.stores.infrastructure.stock_service import variant_infos

    low = wms_low_stock()
    active = set(Store.objects.exclude(status="inactive").values_list("id", flat=True))
    if store_ids is not None:
        wanted = {str(x) for x in store_ids}
        low = [i for i in low if i["store_id"] in wanted]
        active = {x for x in active if str(x) in wanted}
    store_names = dict(Store.objects.values_list("id", "name"))
    expiring, expired = [], []
    for ly in plan.layers(active):
        if not ly.expiry:
            continue
        left = (ly.expiry - today).days
        if left < 0:
            expired.append(ly)
        elif left <= EXPIRY_DAYS:
            expiring.append(ly)
    infos = variant_infos({ly.variant_id for ly in expiring + expired})
    soon = sorted(expiring, key=lambda ly: ly.expiry)
    soon_rows = [{"name": infos[ly.variant_id].name if ly.variant_id in infos else "—", "store": store_names.get(ly.store_id, "—"), "quantity": ly.quantity,
                  "expiry": ly.expiry, "days_left": (ly.expiry - today).days} for ly in soon[:8]]

    # slow movers: on hand, no sale for SLOW_DAYS -- only once the ledger is older than that (otherwise "no sale" means "no history")
    first = StockMovement.objects.order_by("created_at").values_list("created_at", flat=True).first()
    history_ok = bool(first and first <= timezone.now() - timedelta(days=SLOW_DAYS))
    slow, slow_total = [], 0
    if history_ok:
        from apps.stores.infrastructure.report_service import build

        report = build(store_ids=active, days=SLOW_DAYS)
        dead = sorted(report["dead"], key=lambda r: -r.value)
        slow_total = len(dead)
        slow = [{"name": r.info.name, "size": r.info.size or "", "on_hand": r.on_hand, "value": r.value, "last_sale": r.last_sale} for r in dead[:8]]
    return {
        "low_stock": low[:10], "low_stock_total": len(low), "out_of_stock": sum(1 for i in low if i["available_quantity"] == 0),
        "expiring": soon_rows, "expiring_skus": len({(ly.store_id, ly.variant_id) for ly in expiring}), "expiring_units": sum(ly.quantity for ly in expiring),
        "expired_skus": len({(ly.store_id, ly.variant_id) for ly in expired}), "expired_units": sum(ly.quantity for ly in expired),
        "slow": slow, "slow_total": slow_total, "slow_history_ok": history_ok, "slow_days": SLOW_DAYS, "expiry_days": EXPIRY_DAYS,
    }


def _chats(store_ids=None) -> dict:
    """Support chats waiting for the staff -- or, for a branch view, the branch's own customer chats waiting for the owner."""
    from apps.chat.infrastructure.automation import waiting_conversations

    now = timezone.now()
    if store_ids is None:
        times = [i["message"].created_at for i in waiting_conversations(timedelta(0))]
    else:
        from apps.chat.infrastructure.models import ConversationModel, MessageModel, ParticipantModel

        ids = list(ConversationModel.objects.filter(conversation_type="customer_sales", status="open", store_id__in=list(store_ids)).values_list("id", flat=True))
        customers = dict(ParticipantModel.objects.filter(conversation_id__in=ids, role="customer").values_list("conversation_id", "user_id"))
        times = [m.created_at for m in MessageModel.objects.filter(conversation_id__in=ids).order_by("conversation_id", "-created_at").distinct("conversation_id")
                 if customers.get(m.conversation_id) == m.sender_id]
    oldest = max(((now - t).total_seconds() // 60 for t in times), default=0)
    return {"waiting": len(times), "oldest_minutes": int(oldest), "store_chats": store_ids is not None}


def _series(p: Period, cur: dict, prev: dict | None = None) -> dict:
    """Revenue per day (per hour for a one-day period), store tills and online split, plus the previous period's
    total on the same slots (day 1 vs day 1 …) for the comparison line."""
    hourly = p.days == 1
    if hourly:
        keys = list(range(24))
        labels = [f"{h:02d}:00" for h in keys]
    else:
        keys = [p.first_day + timedelta(days=i) for i in range(p.days)]
        labels = [d.strftime("%d.%m") for d in keys]
    index = {k: i for i, k in enumerate(keys)}
    pos, online = [0.0] * len(keys), [0.0] * len(keys)

    def slot(dt):
        local = timezone.localtime(dt, TZ)
        return index.get(local.hour if hourly else local.date())

    for r in cur["kept"]:
        i = slot(r["when"])
        if i is not None:
            pos[i] += float(r["revenue"])
    for o in cur["earned"]:
        i = slot(o["at"])
        if i is not None:
            online[i] += float(o["amount"] or 0)
    previous = [0.0] * len(keys)
    if prev is not None:
        shift = p.start - p.prev_start
        for when, amount in [(r["when"], r["revenue"]) for r in prev["kept"]] + [(o["at"], o["amount"] or 0) for o in prev["earned"]]:
            i = slot(when + shift)
            if i is not None:
                previous[i] += float(amount)
    return {"labels": labels, "pos": pos, "online": online, "previous": previous, "hourly": hourly,
            "totals": [a + b for a, b in zip(pos, online, strict=True)]}


WEEKDAYS = ("Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya")


def _heatmap(cur: dict) -> dict:
    """When people buy: revenue and purchases by weekday × hour (store time), with the busiest slot and day."""
    revenue = [[0.0] * 24 for _ in range(7)]
    count = [[0] * 24 for _ in range(7)]
    for when, amount in [(r["when"], r["revenue"]) for r in cur["kept"] if r["status"] == "completed"] + [(o["at"], o["amount"] or 0) for o in cur["earned"]]:
        local = timezone.localtime(when, TZ)
        revenue[local.weekday()][local.hour] += float(amount)
        count[local.weekday()][local.hour] += 1
    peak = max(((d, h) for d in range(7) for h in range(24)), key=lambda x: count[x[0]][x[1]])
    by_day = [sum(row) for row in revenue]
    by_hour = [sum(revenue[d][h] for d in range(7)) for h in range(24)]
    has = any(any(row) for row in count)
    return {
        "days": WEEKDAYS, "revenue": revenue, "count": count, "max": max((max(row) for row in revenue), default=0) or 1,
        "peak": {"day": WEEKDAYS[peak[0]], "hour": peak[1], "count": count[peak[0]][peak[1]]} if has else None,
        "best_day": WEEKDAYS[by_day.index(max(by_day))] if has else None,
        "best_hour": by_hour.index(max(by_hour)) if has else None,
    }


def _sellers(cur: dict, limit: int = 8) -> list[dict]:
    """Till revenue per seller (PIN cashiers, branch owners, dashboard staff) -- sales_reports.by_seller."""
    from apps.pos.infrastructure import sales_reports as rep

    rows = [r for r in rep.by_seller(cur["pos"]) if r["revenue"] or r["count"]][:limit]
    lead = rows[0]["revenue"] if rows else ZERO
    return [{"name": r["name"], "branch": r["branch"], "revenue": r["revenue"], "count": r["count"], "average": r["average"],
             "units": r["units"], "share": int(r["revenue"] * 100 / lead) if lead else 0} for r in rows]


def _mix(lines: dict) -> dict:
    """Revenue by category and by brand (top 6 + "Boshqa")."""
    from apps.products.infrastructure.models import BrandTranslation, CategoryTranslation, Product, ProductVariant

    variant_product = dict(getattr(ProductVariant, "all_objects", ProductVariant.objects).filter(id__in=[a["variant"] for a in lines.values() if a["variant"]]).values_list("id", "product_id"))
    product_ids = set(variant_product.values()) | {a["product"] for a in lines.values() if a["product"]}
    meta = {p["id"]: p for p in Product.all_objects.filter(id__in=product_ids).values("id", "category_id", "brand_id")}

    def names(model, field, ids):
        out = {}
        for row in model.objects.filter(**{f"{field}__in": ids}).values(field, "locale_code", "name"):
            if row["name"] and (row[field] not in out or row["locale_code"] == "uz"):
                out[row[field]] = row["name"]
        return out

    cats = names(CategoryTranslation, "category_id", {m["category_id"] for m in meta.values() if m["category_id"]})
    brands = names(BrandTranslation, "brand_id", {m["brand_id"] for m in meta.values() if m["brand_id"]})
    by_cat: dict = defaultdict(lambda: ZERO)
    by_brand: dict = defaultdict(lambda: ZERO)
    for a in lines.values():
        m = meta.get(variant_product.get(a["variant"]) or a["product"]) or {}
        by_cat[cats.get(m.get("category_id"), "Kategoriyasiz")] += a["revenue"]
        by_brand[brands.get(m.get("brand_id"), "Brendsiz")] += a["revenue"]

    def top(d):
        total = sum(d.values(), ZERO)
        items = sorted(d.items(), key=lambda kv: -kv[1])
        head, rest = items[:6], sum((v for _k, v in items[6:]), ZERO)
        if rest:
            head.append(("Boshqa", rest))
        return [{"name": k, "revenue": v, "share": round(float(v / total * 100), 1) if total else 0} for k, v in head if v]

    return {"categories": top(by_cat), "brands": top(by_brand)}


# ---------------------------------------------------------------- alerts & summary


def _alerts(r: dict) -> list[dict]:
    out = []
    o, inv, ov = r.get("orders"), r.get("inventory"), r.get("overview")
    if ov and ov["revenue_change"]["pct"] is not None and abs(ov["revenue_change"]["pct"]) >= 30 and ov["prev_revenue"] >= 100_000:
        down = ov["revenue_change"]["dir"] == "down"
        out.append({"level": "danger" if down else "good", "icon": "📉" if down else "📈",
                    "text": f"Tushum {r['period'].compare_label.split(' (')[0]} {abs(ov['revenue_change']['pct']):.0f}% {'kamaydi' if down else 'oshdi'}"})
    if ov and ov["revenue"] == 0 and ov["prev_revenue"] > 0:
        out.append({"level": "warn", "icon": "⏳", "text": "Bu davrda hali birorta savdo qayd etilmagan"})
    if o and o["cancel_spike"]:
        out.append({"level": "danger", "icon": "🚫", "text": f"Bekor qilishlar ko'paydi: {o['cancelled']} ta ({o['cancel_rate']}%, oldin {o['prev_cancel_rate']}%)"})
    elif o and o["cancelled"] >= 3:
        out.append({"level": "warn", "icon": "🚫", "text": f"Bekor qilingan onlayn buyurtmalar: {o['cancelled']} ta"})
    if inv:
        if inv["out_of_stock"]:
            out.append({"level": "danger", "icon": "🛑", "text": f"Tugagan mahsulotlar (minimal qoldiq qoidasi bo'yicha): {inv['out_of_stock']} ta"})
        if inv["low_stock_total"] - inv["out_of_stock"] > 0:
            out.append({"level": "warn", "icon": "📦", "text": f"Kam qolgan mahsulotlar: {inv['low_stock_total'] - inv['out_of_stock']} ta"})
        if inv["expired_skus"]:
            out.append({"level": "danger", "icon": "☠️", "text": f"Muddati o'tgan partiyalar javonda: {inv['expired_skus']} ta ({inv['expired_units']} dona)"})
        if inv["expiring_skus"]:
            out.append({"level": "warn", "icon": "⏰", "text": f"{inv['expiry_days']} kun ichida muddati tugaydi: {inv['expiring_skus']} ta ({inv['expiring_units']} dona)"})
    ch = r.get("chats")
    if ch and ch["waiting"]:
        out.append({"level": "warn" if ch["oldest_minutes"] < 60 else "danger", "icon": "💬", "text": f"Javobsiz chatlar: {ch['waiting']} ta (eng eskisi {duration(ch['oldest_minutes'])})"})
    if o and o["backlog"]:
        stuck = next((b for b in o["backlog"] if b["code"] == "pending_payment"), None)
        if stuck and stuck["count"] >= 5:
            out.append({"level": "warn", "icon": "💳", "text": f"To'lov kutayotgan buyurtmalar: {stuck['count']} ta"})
    failed = [name for name, ok in r["sections_ok"].items() if not ok]
    if failed:
        out.append({"level": "danger", "icon": "⚠️", "text": "Ma'lumot yuklanmadi: " + ", ".join(failed)})
    return out


def _summary(r: dict) -> list[str]:
    """Two or three evidence-based lines: the strongest result and the most important issue."""
    lines = []
    ov, stores, products = r.get("overview"), r.get("stores") or [], r.get("products") or {}
    if ov and ov["revenue"] > 0:
        best = next((s for s in stores if s["revenue"] > 0), None)
        if best and len([s for s in stores if s["revenue"] > 0]) > 1:
            lines.append(f"🏆 Eng kuchli filial — {best['name']}: tushumning {best['share']:.0f}%")
        top = (products.get("top") or [None])[0]
        if top:
            lines.append(f"🔥 Yetakchi mahsulot — {top['name']}: {top['units']} dona")
        if ov["revenue_change"]["dir"] == "up" and ov["revenue_change"]["pct"] is not None:
            lines.append(f"📈 Tushum {ov['revenue_change']['pct']:+.1f}% — {r['period'].compare_label}")
    elif ov:
        lines.append("ℹ️ Bu davrda savdo qayd etilmagan")
    issue = next((a for a in r["alerts"] if a["level"] == "danger"), None) or next((a for a in r["alerts"] if a["level"] == "warn"), None)
    if issue:
        lines.append(f"⚠️ Asosiy e'tibor: {issue['text']}")
    return lines[:4]


# ---------------------------------------------------------------- entry point


def _safe(name: str, ok: dict, fn, default=None):
    try:
        value = fn()
        ok[name] = True
        return value
    except Exception:  # noqa: BLE001 - one broken source never takes the whole report down; it's reported as missing instead
        logger.exception("analytics: section %s failed", name)
        ok[name] = False
        return default


ALL_SECTIONS = ("overview", "finance", "stores", "products", "orders", "customers", "inventory", "chats", "series", "heatmap", "sellers", "mix")


def build(p: Period, sections=ALL_SECTIONS, store_ids=None) -> dict:
    """The whole report. `store_ids` narrows every figure to those branches (a branch owner's view); None = the company."""
    ok: dict = {}
    store_ids = list(store_ids) if store_ids is not None else None
    r: dict = {"period": p, "generated_at": timezone.now().astimezone(TZ), "sections_ok": ok, "store_ids": store_ids}
    if store_ids is not None:
        from apps.stores.infrastructure.models import Store

        r["scope_names"] = list(Store.objects.filter(id__in=store_ids).order_by("name").values_list("name", flat=True))
    cur = _safe("Savdo", ok, lambda: _base(p.start, p.end, store_ids))
    prev = _safe("Oldingi davr", ok, lambda: _base(p.prev_start, p.prev_end, store_ids)) if cur is not None else None
    lines = _safe("Mahsulotlar", ok, lambda: _sold_lines(cur)) if cur is not None else None

    if cur is not None and prev is not None:
        cost = _safe("Tannarx", ok, lambda: _cost(lines, cur["revenue"])) if lines is not None else None
        prev_cost = None
        if cost and cost["reliable"]:
            prev_cost = _safe("Tannarx", ok, lambda: _cost(_sold_lines(prev), prev["revenue"]))
        avg = (cur["revenue"] / cur["purchases"]).quantize(Decimal("1")) if cur["purchases"] else None
        prev_avg = (prev["revenue"] / prev["purchases"]).quantize(Decimal("1")) if prev["purchases"] else None
        r["overview"] = {
            "revenue": cur["revenue"], "prev_revenue": prev["revenue"], "revenue_change": change(cur["revenue"], prev["revenue"]),
            "purchases": cur["purchases"], "purchases_change": change(cur["purchases"], prev["purchases"]),
            "units": cur["units"], "units_change": change(cur["units"], prev["units"]),
            "average": avg, "average_change": change(avg, prev_avg) if avg is not None and prev_avg is not None else None,
            "pos_revenue": cur["pos_revenue"], "online_revenue": cur["online_revenue"],
            "pipeline_value": cur["pipeline_value"], "pipeline_orders": cur["pipeline_orders"],
            "gross_profit": cost["gross_profit"] if cost else None, "margin": cost["margin"] if cost else None,
            "cost_coverage": cost["coverage"] if cost else None, "cogs": cost["cogs"] if cost else None,
            "profit_change": change(cost["gross_profit"], prev_cost["gross_profit"]) if cost and prev_cost and prev_cost["reliable"] else None,
        }
        if "finance" in sections:
            def finance():
                windows = {}
                for key in ("today", "7d", "30d"):
                    w = period(key)
                    windows[key] = _base(w.start, w.end, store_ids)["revenue"]
                return {
                    "windows": [{"key": k, "label": PERIOD_TITLES[k], "revenue": v} for k, v in windows.items()],
                    "lifetime": _base(_at(date(2000, 1, 1)), timezone.now(), store_ids)["revenue"],
                    "gross_sales": cur["gross_sales"], "discounts": cur["discounts"], "delivery": cur["delivery"], "refunds": cur["refunds_total"], "refunds_count": cur["refunds_count"],
                    "net_revenue": cur["revenue"], "lost_value": cur["lost_value"], "payments": _payments(cur),
                    "expenses_available": False,
                }
            r["finance"] = _safe("Moliya", ok, finance)
        if "stores" in sections:
            r["stores"] = _safe("Filiallar", ok, lambda: _stores(cur, prev, store_ids), [])
        if "orders" in sections:
            r["orders"] = _safe("Buyurtmalar", ok, lambda: _orders(cur, prev))
        if "customers" in sections:
            r["customers"] = _safe("Mijozlar", ok, lambda: _customers(p, cur, store_ids))
        if "series" in sections:
            r["series"] = _safe("Grafik", ok, lambda: _series(p, cur, prev))
        if "heatmap" in sections:
            r["heatmap"] = _safe("Soatlar", ok, lambda: _heatmap(cur))
        if "sellers" in sections:
            r["sellers"] = _safe("Kassirlar", ok, lambda: _sellers(cur), [])
        if "mix" in sections and lines is not None:
            r["mix"] = _safe("Kategoriyalar", ok, lambda: _mix(lines))
        if "products" in sections and lines is not None:
            r["products"] = _safe("Top mahsulotlar", ok, lambda: {"top": top_products(lines), "sku_sold": len(lines)})
    if "inventory" in sections:
        r["inventory"] = _safe("Ombor", ok, lambda: _inventory(timezone.now().astimezone(TZ).date(), store_ids))
    if "chats" in sections:
        r["chats"] = _safe("Chatlar", ok, lambda: _chats(store_ids))
    r["alerts"] = _alerts(r)
    r["summary"] = _summary(r)
    return r
