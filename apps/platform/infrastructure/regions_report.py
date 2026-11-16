"""
Dashboard → "Hududlar" (regions mode): sales of every region of Uzbekistan in one view.

* Online orders count in the region they ship to. Orders keep the city as typed / picked ("Tashkent", "Ташкент",
  "Toshkent") and no region, so the city is resolved through the geo reference: any language's city name ->
  City.region, then district names, then region names themselves. Unresolved cities stay visible as "Aniqlanmagan".
* Till sales count in the region of the branch that rang them up (Store.city resolved the same way).
* Money uses the Analitika formula (business_analytics): earned = delivered/completed online orders + kept till
  receipts; pipeline and lost online orders are shown beside it, never mixed in. A running period is compared
  with the same elapsed span before it.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.utils.translation import get_language
from django.utils.translation import gettext as _

from apps.platform.infrastructure import business_analytics as ba

ZERO = Decimal("0")
UNKNOWN = "unknown"
CENTRAL = "central"  # till sales rung up outside any branch (the dashboard / online kassa)

# Grid cartogram of Uzbekistan: (column, row) of each region tile, west -> east. Tashkent city sits beside its region.
TILES = {
    "UZ-QR": (0, 0), "UZ-XO": (1, 1), "UZ-NW": (2, 0), "UZ-BU": (2, 1), "UZ-SA": (3, 1), "UZ-QA": (3, 2),
    "UZ-SU": (4, 2), "UZ-JI": (4, 1), "UZ-SI": (5, 1), "UZ-TO": (5, 0), "TGCITYR": (6, 0), "UZ-NG": (7, 0),
    "UZ-FA": (7, 1), "UZ-AN": (8, 1),
}
SHORT = {  # tile captions (the full name is in the table and the tooltip)
    "UZ-QR": "Qoraqalpog'iston", "UZ-XO": "Xorazm", "UZ-NW": "Navoiy", "UZ-BU": "Buxoro", "UZ-SA": "Samarqand",
    "UZ-QA": "Qashqadaryo", "UZ-SU": "Surxondaryo", "UZ-JI": "Jizzax", "UZ-SI": "Sirdaryo", "UZ-TO": "Toshkent vil.",
    "TGCITYR": "Toshkent sh.", "UZ-NG": "Namangan", "UZ-FA": "Farg'ona", "UZ-AN": "Andijon",
}


def _key(name: str | None) -> str:
    return " ".join((name or "").replace("’", "'").replace("‘", "'").replace("`", "'").lower().split())


def region_index(lang: str = "uz") -> tuple[dict[str, str], dict[str, dict]]:
    """(name in any language -> region code, region code -> {code, name, short, col, row}) from the geo reference."""
    from apps.geo.infrastructure.models import CityTranslation, DistrictTranslation, Region, RegionTranslation

    names: dict[str, dict[str, str]] = defaultdict(dict)
    for code, loc, name in RegionTranslation.objects.values_list("region__code", "locale_code", "name"):
        names[code][loc] = name
    regions = {}
    for code in Region.objects.values_list("code", flat=True):
        col, row = TILES.get(code, (None, None))
        shown = names[code].get(lang) or names[code].get("uz") or code
        regions[code] = {"code": code, "name": shown, "short": SHORT.get(code, shown) if lang == "uz" else shown.split(" ")[0], "col": col, "row": row}
    lookup: dict[str, str] = {}
    for code, by_lang in names.items():  # "Toshkent viloyati" / "Samarqand" (region word dropped) -> region
        for name in by_lang.values():
            k = _key(name)
            lookup.setdefault(k, code)
            lookup.setdefault(k.split(" ")[0], code)
    for name, code in DistrictTranslation.objects.values_list("name", "district__region__code"):
        lookup[_key(name)] = code
    for name, code in CityTranslation.objects.values_list("name", "city__region__code"):  # cities win over the rest
        lookup[_key(name)] = code
    return lookup, regions


def _resolve(lookup: dict[str, str], city: str | None, region: str | None = None) -> str:
    for raw in (region, city):
        k = _key(raw)
        if not k:
            continue
        if k in lookup:
            return lookup[k]
        first = k.replace(",", " ").split(" ")[0]
        if first in lookup:
            return lookup[first]
    return UNKNOWN


def _online(start, end) -> list[dict]:
    from apps.ordering.infrastructure.models import OrderModel

    line_total = ExpressionWrapper(
        F("lines__unit_price_amount") * F("lines__quantity") - F("lines__discount_amount") + F("lines__tax_amount"),
        output_field=DecimalField(max_digits=16, decimal_places=2),
    )
    return list(
        OrderModel.objects.exclude(status="draft").filter(currency="UZS")
        .annotate(at=Coalesce("placed_at", "created_at")).filter(at__gte=start, at__lt=end)
        .annotate(amount=Sum(line_total, filter=Q(lines__status="active")))
        .values("id", "status", "amount", "customer_id", "shipping_city", "shipping_region", "shipping_amount", "fulfilment_method")
    )


def _blank() -> dict:
    return {"revenue": ZERO, "online_revenue": ZERO, "pos_revenue": ZERO, "orders": 0, "online_orders": 0, "pos_sales": 0,
            "pipeline_orders": 0, "pipeline_value": ZERO, "lost_orders": 0, "placed": 0, "customers": set(), "delivery_fees": ZERO,
            "cities": defaultdict(lambda: [0, ZERO])}


def _collect(start, end, lookup, store_region, branch_ids=frozenset()) -> dict[str, dict]:
    out: dict[str, dict] = defaultdict(_blank)
    for o in _online(start, end):
        code = _resolve(lookup, o["shipping_city"], o["shipping_region"])
        r = out[code]
        r["placed"] += 1
        amount = o["amount"] or ZERO
        if o["status"] in ba.EARNED:
            r["online_revenue"] += amount
            r["online_orders"] += 1
            r["delivery_fees"] += o["shipping_amount"] or ZERO
            if o["customer_id"]:
                r["customers"].add(o["customer_id"])
            city = (o["shipping_city"] or "—").strip() or "—"
            r["cities"][city][0] += 1
            r["cities"][city][1] += amount
        elif o["status"] in ba.PIPELINE:
            r["pipeline_orders"] += 1
            r["pipeline_value"] += amount
        elif o["status"] in ba.LOST:
            r["lost_orders"] += 1
    for s in ba._pos_rows(start, end):
        if s["status"] not in ("completed", "refunded"):
            continue
        code = store_region.get(s["branch_id"], CENTRAL if not s["branch_id"] or s["branch_id"] not in branch_ids else UNKNOWN)
        r = out[code]
        r["pos_revenue"] += s["revenue"]
        if s["status"] == "completed":
            r["pos_sales"] += 1
        if s["customer_id"]:
            r["customers"].add(s["customer_id"])
    for r in out.values():
        r["revenue"] = r["online_revenue"] + r["pos_revenue"]
        r["orders"] = r["online_orders"] + r["pos_sales"]
    return out


def report(key: str = "30d", date_from=None, date_to=None, lang: str = "uz") -> dict:
    from apps.stores.infrastructure.models import Store

    p = ba.period(key, date_from=date_from, date_to=date_to)
    lookup, regions = region_index(lang)
    stores = list(Store.objects.exclude(status="inactive").values("id", "name", "city"))
    store_region = {s["id"]: _resolve(lookup, s["city"]) for s in stores if s["city"]}
    branches: dict[str, list[str]] = defaultdict(list)
    for s in stores:
        if s["id"] in store_region:
            branches[store_region[s["id"]]].append(s["name"])

    branch_ids = frozenset(s["id"] for s in stores if s["city"])
    cur = _collect(p.start, p.end, lookup, store_region, branch_ids)
    prev = _collect(p.prev_start, p.prev_end, lookup, store_region, branch_ids)
    total = sum((r["revenue"] for r in cur.values()), ZERO)

    rows = []
    extra = {UNKNOWN: _("Aniqlanmagan manzil"), CENTRAL: _("Markaziy kassa (filialsiz)")}
    for code in list(regions) + [c for c in (CENTRAL, UNKNOWN) if c in cur]:
        r = cur.get(code) or _blank()
        before = prev.get(code) or _blank()
        meta = regions.get(code) or {"code": code, "name": str(extra[code]), "short": str(extra[code]), "col": None, "row": None}
        cities = sorted(r["cities"].items(), key=lambda kv: -kv[1][1])[:5]
        rows.append({
            **meta,
            "revenue": float(r["revenue"]), "online_revenue": float(r["online_revenue"]), "pos_revenue": float(r["pos_revenue"]),
            "orders": r["orders"], "online_orders": r["online_orders"], "pos_sales": r["pos_sales"],
            "average": float((r["revenue"] / r["orders"]).quantize(Decimal("1"))) if r["orders"] else 0,
            "customers": len(r["customers"]), "pipeline_orders": r["pipeline_orders"], "pipeline_value": float(r["pipeline_value"]),
            "lost_orders": r["lost_orders"], "loss_rate": round(r["lost_orders"] / r["placed"] * 100, 1) if r["placed"] else 0,
            "delivery_fees": float(r["delivery_fees"]),
            "share": round(float(r["revenue"] / total * 100), 1) if total else 0,
            "previous_revenue": float(before["revenue"]), "change": ba.change(r["revenue"], before["revenue"])["pct"],
            "branches": branches.get(code, []),
            "cities": [{"city": c, "orders": v[0], "revenue": float(v[1])} for c, v in cities],
        })
    rows.sort(key=lambda x: (-x["revenue"], -x["orders"], x["name"]))
    active = [r for r in rows if r["orders"]]
    tashkent = sum(r["revenue"] for r in rows if r["code"] == "TGCITYR")
    prev_total = sum((r["revenue"] for r in prev.values()), ZERO)
    return {
        "range": p.key, "title": p.title, "period": p.range_text(), "compare": p.compare_label,
        "summary": {
            "revenue": float(total), "previous_revenue": float(prev_total), "change": ba.change(total, prev_total)["pct"],
            "orders": sum(r["orders"] for r in rows), "customers": sum(r["customers"] for r in rows),
            "regions_active": len([r for r in active if r["code"] not in extra]), "regions_total": len(regions),
            "top": active[0]["name"] if active else None, "top_share": active[0]["share"] if active else 0,
            "tashkent_share": round(tashkent / float(total) * 100, 1) if total else 0,
            "pipeline_orders": sum(r["pipeline_orders"] for r in rows), "pipeline_value": sum(r["pipeline_value"] for r in rows),
            "branches": len(store_region),
        },
        "regions": rows,
    }


@staff_member_required
def regions_json(request):
    return JsonResponse(report(request.GET.get("range", "30d"), request.GET.get("from"), request.GET.get("to"), (get_language() or "uz")[:2]))
