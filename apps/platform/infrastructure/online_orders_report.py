"""
Dashboard → "Online orders" chart: storefront orders by day, split into what is already earned,
what is still in the pipeline and what was lost -- from the order lines (subtotal − discount + tax,
the same formula as Order.compute_total), dated by when the customer placed the order.

    earned    delivered + completed
    pipeline  pending payment, confirmed, processing, shipped
    lost      cancelled, returned, failed
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.utils import timezone

TZ = ZoneInfo("Asia/Tashkent")
EARNED = ("delivered", "completed")
PIPELINE = ("pending_payment", "confirmed", "processing", "shipped")
LOST = ("cancelled", "returned", "failed")
ZERO = Decimal("0")


def _orders(start, end):
    from apps.ordering.infrastructure.models import OrderModel

    line_total = ExpressionWrapper(
        F("lines__unit_price_amount") * F("lines__quantity") - F("lines__discount_amount") + F("lines__tax_amount"),
        output_field=DecimalField(max_digits=16, decimal_places=2),
    )
    return list(
        OrderModel.objects.exclude(status="draft").filter(currency="UZS")
        .annotate(at=Coalesce("placed_at", "created_at"))
        .filter(at__gte=start, at__lt=end)
        .annotate(amount=Sum(line_total, filter=Q(lines__status="active")))
        .values("id", "status", "at", "amount", "shipping_city", "customer_id")
    )


def _city_names(lang: str) -> dict[str, str]:
    """Any language's name of a reference city (lower-case) -> its name in `lang`: the shop records the city as the
    customer typed / picked it, so "Toshkent", "Tashkent" and "Ташкент" are one city in the report."""
    from apps.geo.infrastructure.models import CityTranslation

    by_city: dict = defaultdict(dict)
    for city_id, code, name in CityTranslation.objects.values_list("city_id", "locale_code", "name"):
        by_city[city_id][code] = name
    out: dict[str, str] = {}
    for names in by_city.values():
        shown = names.get(lang) or names.get("uz") or next(iter(names.values()))
        for name in names.values():
            out.setdefault(name.strip().lower(), shown)
    return out


def report(first_day, last_day, lang: str = "uz") -> dict:
    start = datetime.combine(first_day, time.min, tzinfo=TZ)
    end = datetime.combine(last_day + timedelta(days=1), time.min, tzinfo=TZ)
    rows = _orders(start, end)
    days = (last_day - first_day).days + 1
    dates = [first_day + timedelta(days=i) for i in range(days)]
    index = {d: i for i, d in enumerate(dates)}
    earned, pipeline, lost, count = ([0.0] * days for _ in range(4))
    by_status: dict = defaultdict(int)
    cities: dict = defaultdict(lambda: [0, ZERO])
    city_names = _city_names(lang)
    for r in rows:
        amount = r["amount"] or ZERO
        by_status[r["status"]] += 1
        i = index.get(timezone.localtime(r["at"], TZ).date())
        if i is None:
            continue
        count[i] += 1
        if r["status"] in EARNED:
            earned[i] += float(amount)
            typed = (r["shipping_city"] or "").strip()
            city = city_names.get(typed.lower(), typed) or "—"
            cities[city][0] += 1
            cities[city][1] += amount
        elif r["status"] in PIPELINE:
            pipeline[i] += float(amount)
        elif r["status"] in LOST:
            lost[i] += float(amount)

    earned_rows = [r for r in rows if r["status"] in EARNED]
    revenue = sum((r["amount"] or ZERO for r in earned_rows), ZERO)
    span = min(end, timezone.now()) - start  # a running period is compared with the same elapsed span before it
    prev = _orders(start - span, start) if span.total_seconds() > 0 else []
    prev_revenue = sum((r["amount"] or ZERO for r in prev if r["status"] in EARNED), ZERO)
    placed = len(rows)
    lost_count = sum(1 for r in rows if r["status"] in LOST)
    top_cities = sorted(({"city": c, "orders": v[0], "revenue": float(v[1])} for c, v in cities.items()), key=lambda x: -x["revenue"])[:6]
    return {
        "from": first_day.isoformat(), "to": last_day.isoformat(),
        "labels": [d.isoformat() for d in dates],
        "series": {"earned": earned, "pipeline": pipeline, "lost": lost, "orders": count},
        "summary": {
            "revenue": float(revenue), "orders": placed, "earned_orders": len(earned_rows),
            "average": float((revenue / len(earned_rows)).quantize(Decimal("1"))) if earned_rows else 0,
            "pipeline_orders": sum(1 for r in rows if r["status"] in PIPELINE),
            "pipeline_value": float(sum((r["amount"] or ZERO for r in rows if r["status"] in PIPELINE), ZERO)),
            "lost_orders": lost_count, "loss_rate": round(lost_count / placed * 100, 1) if placed else 0,
            "customers": len({r["customer_id"] for r in rows if r["customer_id"]}),
            "previous_revenue": float(prev_revenue),
            "change_pct": round(float((revenue - prev_revenue) / prev_revenue * 100), 1) if prev_revenue else None,
        },
        "statuses": dict(by_status),
        "cities": top_cities,
    }


@staff_member_required
def online_orders_json(request):
    from apps.pos.infrastructure.sales_reports import resolve_range

    key, first, last = resolve_range(request.GET.get("range", "30d"), request.GET.get("from"), request.GET.get("to"))
    if key in ("today", "yesterday"):  # a one-day chart of online orders says little -- widen to the week ending that day
        first = last - timedelta(days=6)
    from django.utils.translation import get_language

    return JsonResponse({"range": key, **report(first, last, (get_language() or "uz")[:2])})
