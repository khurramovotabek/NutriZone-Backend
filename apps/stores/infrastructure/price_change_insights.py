"""
Kassirlar nazorati for "Narx o'zgarishlari": how much each cashier gave away at the till over a window, relative to
what they sold, and who stands out.

  given      line price cuts (list → new price) × qty  +  whole-basket discounts, completed sales only
  revenue    what the cashier's completed sales brought (lines at the sold price, minus the basket discount)
  rate       given / (revenue + given) -- the share of the list value the cashier gave away
  below_cost line prices set under the variant's cost price (a sale at a loss)

Outliers use a robust rule (median + 3 × MAD × 1.4826 of the rates, at least 2 points above the median), so one
generous cashier can't hide behind an average that they inflated themselves. Read-only.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

ZERO = Decimal(0)
MIN_SALES = 5


def _median(values: list[float]) -> float:
    v = sorted(values)
    if not v:
        return 0.0
    m = len(v) // 2
    return v[m] if len(v) % 2 else (v[m - 1] + v[m]) / 2


def cashier_control(days: int = 30, now=None) -> dict:
    from apps.pos.infrastructure.models import SaleLineItemModel, SaleModel
    from apps.pricing.infrastructure.models import PriceListEntryModel
    from apps.stores.infrastructure.models import PosPriceChange

    now = now or timezone.now()
    since = now - timedelta(days=days)
    sales = {s["id"]: s for s in SaleModel.objects.filter(status="completed", completed_at__gte=since).values("id", "cashier_id", "discount_amount")}
    rows: dict = defaultdict(lambda: {"sales": 0, "revenue": ZERO, "given": ZERO, "basket": ZERO, "changes": 0, "down": 0, "up": 0, "below_cost": 0, "loss": ZERO, "name": ""})
    for s in sales.values():
        r = rows[s["cashier_id"]]
        r["sales"] += 1
        r["basket"] += s["discount_amount"] or ZERO
        r["revenue"] -= s["discount_amount"] or ZERO
    for ln in SaleLineItemModel.objects.filter(sale_id__in=list(sales)).values("sale_id", "unit_price_amount", "quantity", "refunded_quantity"):
        rows[sales[ln["sale_id"]]["cashier_id"]]["revenue"] += ln["unit_price_amount"] * (ln["quantity"] - (ln["refunded_quantity"] or 0))

    changes = list(PosPriceChange.objects.filter(sale_id__in=list(sales)).values("cashier_id", "cashier_name", "product_variant_id", "list_price", "new_price", "quantity"))
    costs = dict(PriceListEntryModel.objects.filter(product_variant_id__in={c["product_variant_id"] for c in changes if c["product_variant_id"]})
                 .exclude(cost_price_amount=None).values_list("product_variant_id", "cost_price_amount"))
    for c in changes:
        key = c["cashier_id"]
        if key is None:
            continue
        r = rows[key]
        r["name"] = r["name"] or c["cashier_name"]
        r["changes"] += 1
        if c["new_price"] < c["list_price"]:
            r["down"] += 1
            r["given"] += (c["list_price"] - c["new_price"]) * c["quantity"]
        elif c["new_price"] > c["list_price"]:
            r["up"] += 1
        cost = costs.get(c["product_variant_id"])
        if cost and c["new_price"] < cost:
            r["below_cost"] += 1
            r["loss"] += (cost - c["new_price"]) * c["quantity"]

    names = _names([k for k, r in rows.items() if not r["name"]])
    out = []
    for key, r in rows.items():
        given = r["given"] + r["basket"]
        base = r["revenue"] + given
        rate = float(given * 100 / base) if base > 0 else 0.0
        out.append({**r, "id": key, "name": r["name"] or names.get(key, "—"), "given_total": given, "rate": round(rate, 1)})

    eligible = [x["rate"] for x in out if x["sales"] >= MIN_SALES]
    med = _median(eligible)
    mad = _median([abs(v - med) for v in eligible]) * 1.4826
    limit = max(med + 3 * mad, med + 2.0)
    for x in out:
        x["flag"] = "loss" if x["below_cost"] else ("outlier" if x["sales"] >= MIN_SALES and len(eligible) >= 3 and x["rate"] > limit and x["given_total"] > 0 else "")
    out.sort(key=lambda x: (x["flag"] == "", -x["given_total"]))
    top = max((float(x["rate"]) for x in out), default=0) or 1
    for x in out:
        x["w"] = f"{min(100.0, x['rate'] * 100 / top):.1f}"
    total_given = sum((x["given_total"] for x in out), ZERO)
    total_rev = sum((x["revenue"] for x in out), ZERO)
    return {
        "days": days, "rows": out, "median": round(med, 1), "limit": round(limit, 1), "flags": sum(1 for x in out if x["flag"]),
        "given": total_given, "rate": round(float(total_given * 100 / (total_rev + total_given)), 1) if total_rev + total_given > 0 else 0.0,
        "below_cost": sum(x["below_cost"] for x in out), "loss": sum((x["loss"] for x in out), ZERO),
    }


def _names(ids) -> dict:
    if not ids:
        return {}
    from apps.identity.infrastructure.models import User

    return {u.id: (u.full_name or u.phone_number) for u in User.objects.filter(id__in=ids).only("id", "full_name", "phone_number")}
