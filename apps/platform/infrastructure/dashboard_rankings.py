"""
Dashboard home → sales leaderboards for a period (7 / 30 / 90 days):
  * products  -- units sold through every channel (store tills + online orders), with revenue
  * branches  -- till revenue per branch (+ the online shop as its own row), sales count and share
  * cashiers  -- till revenue per seller (PIN cashiers, owners, Dashboard staff), sales and average receipt
Each list is computed independently and is cheap (aggregates over the period only).
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import F, Sum
from django.utils import timezone

ZERO = Decimal(0)
PERIODS = (7, 30, 90)


def _since(days: int):
    return timezone.now() - timedelta(days=days)


def _fmt(v) -> str:
    return f"{int(round(v or 0)):,}".replace(",", " ")


def products(days: int, limit: int = 8) -> list[dict]:
    from apps.ordering.infrastructure.models import OrderLineItemModel
    from apps.pos.infrastructure.models import SaleLineItemModel
    from apps.stores.infrastructure.stock_service import variant_infos

    since = _since(days)
    agg: dict = {}
    for r in SaleLineItemModel.objects.filter(sale__status__in=("completed", "refunded"), sale__completed_at__gte=since, product_variant_id__isnull=False).values("product_variant_id").annotate(
            q=Sum("quantity"), back=Sum("refunded_quantity"), rev=Sum(F("unit_price_amount") * (F("quantity") - F("refunded_quantity")))):
        a = agg.setdefault(r["product_variant_id"], {"units": 0, "revenue": ZERO, "pos": 0, "online": 0})
        units = (r["q"] or 0) - (r["back"] or 0)
        a["units"] += units
        a["pos"] += units
        a["revenue"] += r["rev"] or ZERO
    for r in OrderLineItemModel.objects.filter(order__created_at__gte=since).exclude(order__status__in=("cancelled", "draft", "pending_payment", "returned", "failed")).exclude(status="cancelled").values("product_variant_id").annotate(
            q=Sum("quantity"), rev=Sum(F("unit_price_amount") * F("quantity") - F("discount_amount"))):
        a = agg.setdefault(r["product_variant_id"], {"units": 0, "revenue": ZERO, "pos": 0, "online": 0})
        a["units"] += r["q"] or 0
        a["online"] += r["q"] or 0
        a["revenue"] += r["rev"] or ZERO
    top = sorted(((v, a) for v, a in agg.items() if a["units"] > 0), key=lambda kv: (-kv[1]["units"], -kv[1]["revenue"]))[:limit]
    infos = variant_infos([v for v, _a in top])
    lead = top[0][1]["units"] if top else 1
    return [{"name": infos[v].name if v in infos else "—", "size": infos[v].size if v in infos else "", "image": infos[v].image_url if v in infos else None,
             "units": a["units"], "pos": a["pos"], "online": a["online"], "revenue": _fmt(a["revenue"]), "pct": max(6, round(a["units"] * 100 / lead))} for v, a in top]


def _till_rows(days: int):
    from apps.pos.infrastructure import sales_reports as rep
    from apps.pos.infrastructure.models import SaleModel

    return rep.rows(SaleModel.objects.filter(status__in=("completed", "refunded"), completed_at__gte=_since(days)))


def branches(days: int, limit: int = 8, rows=None) -> list[dict]:
    from apps.ordering.infrastructure.models import OrderLineItemModel
    from apps.pos.infrastructure import sales_reports as rep
    from apps.stores.infrastructure.models import Store

    rows = _till_rows(days) if rows is None else rows
    agg: dict = {}
    for r in rows:
        a = agg.setdefault(rep.branch_key(r), {"revenue": ZERO, "sales": 0})
        a["revenue"] += r["revenue"]
        a["sales"] += r["status"] == "completed"
    names = rep.store_names(list(agg))
    colors = {str(k): v for k, v in Store.objects.values_list("id", "color")}
    out = [{"name": names.get(k, "—"), "color": colors.get(k) or "#64748b", "revenue_raw": a["revenue"], "sales": a["sales"], "online": False} for k, a in agg.items()]
    online = OrderLineItemModel.objects.filter(order__created_at__gte=_since(days)).exclude(order__status__in=("cancelled", "draft", "pending_payment", "returned", "failed")).exclude(status="cancelled")
    online_rev = online.aggregate(v=Sum(F("unit_price_amount") * F("quantity") - F("discount_amount")))["v"] or ZERO
    if online_rev:
        out.append({"name": "Onlayn do'kon", "color": "#6366f1", "revenue_raw": online_rev, "sales": online.values("order_id").distinct().count(), "online": True})
    out.sort(key=lambda b: -b["revenue_raw"])
    total = sum((b["revenue_raw"] for b in out), ZERO) or Decimal(1)
    for b in out:
        b["share"] = round(b["revenue_raw"] * 100 / total)
        b["revenue"] = _fmt(b.pop("revenue_raw"))
    return out[:limit]


def cashiers(days: int, limit: int = 8, rows=None) -> list[dict]:
    from apps.pos.infrastructure import sales_reports as rep

    rows = _till_rows(days) if rows is None else rows
    agg: dict = {}
    for r in rows:
        a = agg.setdefault(r["cashier_id"], {"revenue": ZERO, "sales": 0, "branches": {}})
        a["revenue"] += r["revenue"]
        a["sales"] += r["status"] == "completed"
        k = rep.branch_key(r)
        a["branches"][k] = a["branches"].get(k, 0) + 1
    names = rep.people_names(agg)
    stores = rep.store_names({k for a in agg.values() for k in a["branches"]})
    top = sorted(agg.items(), key=lambda kv: -kv[1]["revenue"])[:limit]
    lead = top[0][1]["revenue"] if top else Decimal(1)
    out = []
    for cid, a in top:
        name = names.get(cid) or "—"
        main = max(a["branches"], key=a["branches"].get) if a["branches"] else None
        out.append({"name": name, "initials": "".join(p[0] for p in name.split()[:2]).upper() or "?", "revenue": _fmt(a["revenue"]), "sales": a["sales"],
                    "avg": _fmt(a["revenue"] / a["sales"]) if a["sales"] else "0", "branch": stores.get(main, "") if main else "",
                    "pct": max(6, round(a["revenue"] * 100 / lead)) if lead else 6})
    return out


def build(days: int) -> dict:
    days = days if days in PERIODS else 30
    rows = _till_rows(days)
    return {"days": days, "periods": PERIODS, "products": products(days), "branches": branches(days, rows=rows), "cashiers": cashiers(days, rows=rows)}
