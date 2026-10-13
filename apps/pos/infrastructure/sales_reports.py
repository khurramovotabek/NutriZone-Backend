"""
Sales figures for the dashboard (Sales Management list, reports, export) -- one
definition of every number, over any SaleModel queryset:

    gross     Σ line items at catalogue price
    discount  the cashier's basket discount
    coins     loyalty coins that covered part of the bill (1 coin = 1 so'm)
    delivery  delivery fee (dashboard till only)
    returned  value given back by (partial) returns (money + coins)
    revenue   gross − discount + delivery − returned   -- net value sold (coins included)
    paid      money kept = revenue − coins kept, split by method (`payments`, net of returns)

A fully returned sale nets to zero; returns are also reported separately.
Everything is computed from the stored sale rows -- nothing here writes.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models import F, Sum
from django.utils import timezone

from apps.pos.domain.enums import PaymentMethod
from apps.pos.infrastructure.models import SaleLineItemModel, SaleModel

TZ = ZoneInfo("Asia/Tashkent")
ZERO = Decimal("0")
CENTRAL = "central"  # the dashboard till (not a partner store)
METHODS = ("cash", "uzcard", "humo", "click", "payme", "uzum")


def split_of(payments, method: str | None, amount: Decimal) -> dict:
    out: dict = {}
    for p in payments or []:
        m = "uzcard" if p.get("method") == PaymentMethod.CARD.value else p.get("method")
        out[m] = out.get(m, ZERO) + Decimal(str(p.get("amount") or 0))
    if not out and method and amount > 0:
        out["uzcard" if method == PaymentMethod.CARD.value else method] = amount
    return out


def rows(qs) -> list[dict]:
    line_total = F("line_items__unit_price_amount") * F("line_items__quantity")
    out = list(qs.order_by().annotate(gross=Sum(line_total), units=Sum("line_items__quantity"), units_back=Sum("line_items__refunded_quantity")).values(
        "id", "status", "channel", "branch_id", "cashier_id", "customer_id", "payment_method", "payments", "receipt_number",
        "gross", "units", "units_back", "discount_amount", "coins_redeemed", "delivery_fee_amount", "completed_at", "created_at", "refunded_at",
        "refunded_amount", "refunded_coins", "refunded_split",
    ))
    for r in out:
        r["gross"] = r["gross"] or ZERO
        r["units"] = (r["units"] or 0) - (r["units_back"] or 0)
        sold_value = r["gross"] - r["discount_amount"] + r["delivery_fee_amount"]
        r["split_sold"] = split_of(r["payments"], r["payment_method"], max(ZERO, sold_value - r["coins_redeemed"]))
        back = {m: Decimal(str(v)) for m, v in (r["refunded_split"] or {}).items()}
        r["split"] = {m: a - back.get(m, ZERO) for m, a in r["split_sold"].items()}
        r["returned"] = r["refunded_amount"] + r["refunded_coins"]
        r["revenue"] = sold_value - r["returned"]
        r["coins_kept"] = r["coins_redeemed"] - r["refunded_coins"]
        r["paid"] = max(ZERO, r["revenue"] - r["coins_kept"])
        r["method"] = "uzcard" if r["payment_method"] == PaymentMethod.CARD.value else r["payment_method"]
        r["when"] = r["completed_at"] or r["created_at"]
    return out


def _sum(items, key) -> Decimal:
    return sum((r[key] for r in items), ZERO)


def summary(all_rows: list[dict]) -> dict:
    kept = [r for r in all_rows if r["status"] in ("completed", "refunded")]
    done = [r for r in kept if r["status"] == "completed"]
    revenue = _sum(kept, "revenue")
    by_method = {m: sum((r["split"].get(m, ZERO) for r in kept), ZERO) for m in METHODS}
    returned = [r for r in kept if r["returned"] > 0]
    return {
        "count": len(done), "revenue": revenue, "average": (revenue / len(done)).quantize(Decimal("1")) if done else ZERO,
        "units": sum(r["units"] for r in kept), "gross": _sum(done, "gross"), "discount": _sum(done, "discount_amount"),
        "coins": _sum(kept, "coins_kept"), "paid": _sum(kept, "paid"), "by_method": by_method,
        "cards": by_method["uzcard"] + by_method["humo"],
        "refunds_count": len(returned), "refunds_total": _sum(returned, "returned"),
        "customers": len({r["customer_id"] for r in done if r["customer_id"]}),
    }


# ---------------------------------------------------------------- names


def branch_key(row: dict) -> str:
    return str(row["branch_id"]) if row["channel"] == "store" else CENTRAL


def _brand_name() -> str:
    from apps.platform.infrastructure.branding import brand_name

    return brand_name()


def store_names(ids) -> dict[str, str]:
    from apps.stores.infrastructure.models import Store

    from apps.stores.infrastructure.pos_cashiers import ONLINE_KASSA_NAME

    names = {str(i): (ONLINE_KASSA_NAME if kind == "warehouse" else n) for i, n, kind in Store.objects.filter(id__in=[i for i in ids if i != CENTRAL]).values_list("id", "name", "kind")}
    names[CENTRAL] = f"{_brand_name()} (Dashboard POS)"
    return names


def _staff_uuid_map() -> dict:
    """Dashboard-till sales carry a uuid5 of the staff member's auth id (see pos_view._actor_id) -- map it back to a name."""
    from django.contrib.auth import get_user_model

    return {
        uuid.uuid5(uuid.NAMESPACE_DNS, f"nutrizone-admin-staff-{u.pk}"): (u.get_full_name() or u.get_username())
        for u in get_user_model().objects.filter(is_staff=True).only("id", "username", "first_name", "last_name")
    }


def people_names(ids) -> dict:
    from apps.identity.infrastructure.models import User

    ids = {i for i in ids if i}
    names = {u.id: (u.full_name or u.phone_number) for u in User.objects.filter(id__in=ids).only("id", "full_name", "phone_number")}
    missing = ids - set(names)
    if missing:
        staff = _staff_uuid_map()
        names.update({i: staff[i] for i in missing if i in staff})
    return names


def product_summary(sale_ids, locale: str = "uz") -> dict:
    """{sale_id: [(name, qty), ...]} for a page of sales, in two queries."""
    from apps.products.infrastructure.models import ProductTranslation

    lines = list(SaleLineItemModel.objects.filter(sale_id__in=sale_ids).values("sale_id", "product_id", "quantity"))
    names: dict = {}
    for tr in ProductTranslation.objects.filter(product_id__in={ln["product_id"] for ln in lines}).values("product_id", "locale_code", "name"):
        if tr["name"] and (tr["product_id"] not in names or tr["locale_code"] == locale):
            names[tr["product_id"]] = tr["name"]
    out: dict = defaultdict(list)
    for ln in lines:
        out[ln["sale_id"]].append((names.get(ln["product_id"], "—"), ln["quantity"]))
    return out


# ---------------------------------------------------------------- breakdowns


def by_branch(all_rows: list[dict]) -> list[dict]:
    groups: dict = defaultdict(list)
    for r in all_rows:
        groups[branch_key(r)].append(r)
    names = store_names(groups)
    out = [{"key": k, "name": names.get(k, "—"), **summary(v)} for k, v in groups.items()]
    return sorted(out, key=lambda x: x["revenue"], reverse=True)


def by_seller(all_rows: list[dict]) -> list[dict]:
    groups: dict = defaultdict(list)
    for r in all_rows:
        groups[(r["cashier_id"], branch_key(r))].append(r)
    people = people_names({k[0] for k in groups})
    stores = store_names({k[1] for k in groups})
    out = [{"name": people.get(k[0], "—"), "branch": stores.get(k[1], "—"), **summary(v)} for k, v in groups.items()]
    return sorted(out, key=lambda x: x["revenue"], reverse=True)


def by_method(all_rows: list[dict]) -> list[dict]:
    s = summary(all_rows)
    out = [{"code": m, "amount": s["by_method"][m]} for m in METHODS if s["by_method"][m]]
    if s["coins"]:
        out.append({"code": "coins", "amount": s["coins"]})
    total = sum((x["amount"] for x in out), ZERO) or Decimal("1")
    for x in out:
        x["share"] = int(round(x["amount"] / total * 100))
    return sorted(out, key=lambda x: x["amount"], reverse=True)


def top_products(qs, limit: int = 10, locale: str = "uz") -> list[dict]:
    from apps.products.infrastructure.models import ProductTranslation

    top = list(
        SaleLineItemModel.objects.filter(sale__in=qs.filter(status="completed").order_by().values("id"))
        .values("product_id").annotate(qty=Sum(F("quantity") - F("refunded_quantity")), revenue=Sum(F("unit_price_amount") * (F("quantity") - F("refunded_quantity"))))
        .filter(qty__gt=0).order_by("-revenue")[:limit]
    )
    names: dict = {}
    for tr in ProductTranslation.objects.filter(product_id__in=[t["product_id"] for t in top]).values("product_id", "locale_code", "name"):
        if tr["name"] and (tr["product_id"] not in names or tr["locale_code"] == locale):
            names[tr["product_id"]] = tr["name"]
    peak = top[0]["revenue"] if top else Decimal("1")
    return [{"name": names.get(t["product_id"], "—"), "qty": t["qty"], "revenue": t["revenue"], "share": int(t["revenue"] / peak * 100) if peak else 0} for t in top]


def series(all_rows: list[dict], grain: str, start, end) -> list[dict]:
    """Revenue per day / ISO week / month between start and end (store wall-clock time), empty buckets included."""
    def key(dt):
        d = timezone.localtime(dt, TZ).date()
        if grain == "month":
            return d.replace(day=1)
        if grain == "week":
            return d - timedelta(days=d.weekday())
        return d

    buckets: dict = {}
    cursor, last = key(start), key(end)
    while cursor <= last:
        buckets[cursor] = {"date": cursor, "revenue": ZERO, "count": 0, "paid": ZERO, "coins": ZERO}
        if grain == "month":
            cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        else:
            cursor += timedelta(days=7 if grain == "week" else 1)
    for r in all_rows:
        if r["status"] not in ("completed", "refunded") or not r["completed_at"]:
            continue
        b = buckets.get(key(r["completed_at"]))
        if b:
            b["revenue"] += r["revenue"]
            b["paid"] += r["paid"]
            b["coins"] += r["coins_kept"]
            b["count"] += 1 if r["status"] == "completed" else 0
    out = list(buckets.values())
    peak = max((b["revenue"] for b in out), default=ZERO) or Decimal("1")
    for b in out:
        b["share"] = int(b["revenue"] / peak * 100)
        b["label"] = b["date"].strftime("%m.%Y") if grain == "month" else b["date"].strftime("%d.%m")
    return out


def closed_sales():
    return SaleModel.objects.exclude(status__in=["open", "voided"])


# ---------------------------------------------------------------- dashboard: daily sales by store

CENTRAL_COLOR = "#94A3B8"
RANGES = ("today", "yesterday", "7d", "30d", "this_month", "prev_month", "custom")


def resolve_range(key: str, date_from=None, date_to=None):
    """(key, first_day, last_day) in store time; custom needs both dates (max 366 days)."""
    from datetime import date as date_cls

    today = timezone.localtime(timezone.now(), TZ).date()
    if key == "today":
        return key, today, today
    if key == "yesterday":
        d = today - timedelta(days=1)
        return key, d, d
    if key == "30d":
        return key, today - timedelta(days=29), today
    if key == "this_month":
        return key, today.replace(day=1), today
    if key == "prev_month":
        last = today.replace(day=1) - timedelta(days=1)
        return key, last.replace(day=1), last
    if key == "custom":
        try:
            a, b = date_cls.fromisoformat(str(date_from)), date_cls.fromisoformat(str(date_to))
        except (TypeError, ValueError):
            return resolve_range("7d")
        if a > b:
            a, b = b, a
        return key, max(a, b - timedelta(days=365)), b
    return "7d", today - timedelta(days=6), today


def daily_by_store(first_day, last_day) -> dict:
    """
    Net revenue per store per day (per hour for a single day) between two store-time dates, every
    active store included (a store with no sales is a flat zero line), each with its lifelong colour.
    Also the same totals for the equivalent previous period, for the change indicator.
    """
    from datetime import datetime, time

    from apps.stores.infrastructure.models import Store

    start = datetime.combine(first_day, time.min, tzinfo=TZ)
    end = datetime.combine(last_day + timedelta(days=1), time.min, tzinfo=TZ)
    hourly = first_day == last_day
    if hourly:
        buckets = [start + timedelta(hours=h) for h in range(24)]
        labels = [b.strftime("%H:00") for b in buckets]
        keys = [b.hour for b in buckets]
    else:
        days = (last_day - first_day).days + 1
        dates = [first_day + timedelta(days=i) for i in range(days)]
        labels = [d.isoformat() for d in dates]
        keys = dates

    data = rows(closed_sales().filter(channel="store", completed_at__gte=start, completed_at__lt=end))
    series: dict = defaultdict(lambda: [ZERO] * len(keys))
    counts: dict = defaultdict(int)
    index = {k: i for i, k in enumerate(keys)}
    for r in data:
        local = timezone.localtime(r["completed_at"], TZ)
        i = index.get(local.hour if hourly else local.date())
        if i is None:
            continue
        key = branch_key(r)
        series[key][i] += r["revenue"]
        if r["status"] == "completed":
            counts[key] += 1

    stores = []
    for s in Store.objects.filter(status="active", kind="store").order_by("created_at").values("id", "name", "color", "city"):
        key = str(s["id"])
        stores.append({"id": key, "name": s["name"], "city": s["city"], "color": s["color"] or CENTRAL_COLOR, "series": series.get(key, [ZERO] * len(keys)), "count": counts.get(key, 0)})
    known = {s["id"] for s in stores}
    # Only branches that sell are charted: the warehouse (and the dashboard till that sells from it) is left out.
    for key in [k for k in series if k not in known and k != CENTRAL]:  # the dashboard till, or a store that has since been closed
        name = store_names([key]).get(key, "—")
        colour = CENTRAL_COLOR if key == CENTRAL else (Store.objects.filter(id=key).values_list("color", flat=True).first() or CENTRAL_COLOR)
        stores.append({"id": key, "name": name, "city": "", "color": colour, "series": series[key], "count": counts.get(key, 0)})
    for s in stores:
        s["total"] = sum(s["series"], ZERO)
        s["series"] = [float(v) for v in s["series"]]
    stores.sort(key=lambda s: s["total"], reverse=True)
    total = sum((s["total"] for s in stores), ZERO)

    span = end - start
    prev = rows(closed_sales().filter(channel="store", completed_at__gte=start - span, completed_at__lt=start))
    prev_total = sum((r["revenue"] for r in prev), ZERO)
    top = stores[0] if stores and stores[0]["total"] > 0 else None
    return {
        "granularity": "hour" if hourly else "day",
        "from": first_day.isoformat(), "to": last_day.isoformat(),
        "labels": labels,
        "stores": [{**s, "total": float(s["total"]), "share": round(float(s["total"] / total * 100), 1) if total else 0} for s in stores],
        "totals": [float(sum((s["series"][i] for s in stores), 0.0)) for i in range(len(keys))],
        "summary": {
            "total": float(total), "sales": sum(s["count"] for s in stores), "stores_with_sales": sum(1 for s in stores if s["total"] > 0), "stores": len(stores),
            "top": {"name": top["name"], "color": top["color"], "total": float(top["total"])} if top else None,
            "previous_total": float(prev_total),
            "change_pct": round(float((total - prev_total) / prev_total * 100), 1) if prev_total else None,
        },
    }
