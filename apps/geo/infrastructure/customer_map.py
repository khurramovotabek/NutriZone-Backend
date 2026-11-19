"""
Dashboard → Geo → Mijozlar xaritasi: who our customers are and where, on the map of Uzbekistan.

Each customer sits at the spot of their latest delivery (the point they marked at checkout), else at their saved
address point. Per customer: orders in the period (cancelled / returned / failed not counted), what they spent
(delivered + completed, the same rule as Analitika -- business_analytics.EARNED), the last order and a segment:

* VIP        -- the top 10 % by spend in the period (and at least VIP_MIN so'm)
* Doimiy     -- 2+ orders
* Yangi      -- one order
* Buyurtmasiz -- a saved address, no order in the period (a warm lead for a reminder / coupon)

Every point is attributed to a region by the nearest city centre we hold (87 cities), which also gives each
region its bubble: customers, orders, revenue, average check and the branches there -- where to open next.
Staff only (the page is permission-gated); nothing here is public.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django.urls import reverse
from django.utils import timezone

PERIODS = {"30d": ("So'nggi 30 kun", 30), "90d": ("So'nggi 90 kun", 90), "365d": ("So'nggi 1 yil", 365), "all": ("Butun davr", None)}
SEGMENTS = {  # key -> (label, colour)
    "vip": ("VIP", "#d97706"),
    "loyal": ("Doimiy", "#16a34a"),
    "new": ("Yangi", "#2563eb"),
    "lead": ("Buyurtmasiz", "#94a3b8"),
}
VIP_MIN = Decimal("1000000")
LOST = ("cancelled", "returned", "failed")


def _start(key: str) -> datetime | None:
    days = PERIODS.get(key, PERIODS["90d"])[1]
    return timezone.now() - timedelta(days=days) if days else None


def _haversine2(lat1, lng1, lat2, lng2) -> float:
    # squared-degree distance (with longitude scaled at Uzbekistan's latitude) -- enough to pick the nearest city
    return (lat1 - lat2) ** 2 + ((lng1 - lng2) * 0.76) ** 2


def build(period_key: str = "90d") -> dict:  # noqa: C901 - one pass: orders, points, regions, segments
    from apps.geo.infrastructure import models as geo
    from apps.geo.infrastructure.admin import uz_name
    from apps.identity.infrastructure.models import User
    from apps.ordering.infrastructure.models import OrderModel
    from apps.platform.infrastructure.business_analytics import EARNED, _online_orders
    from apps.stores.infrastructure.models import Store

    period_key = period_key if period_key in PERIODS else "90d"
    start = _start(period_key)
    now = timezone.now()

    # ---- orders in the period, per customer (amount = active lines, same as Analitika)
    rows = _online_orders(start or datetime(2000, 1, 1, tzinfo=UTC), now + timedelta(minutes=1))
    per: dict = defaultdict(lambda: {"orders": 0, "spent": Decimal(0), "last": None})
    for o in rows:
        if not o["customer_id"] or o["status"] in LOST:
            continue
        c = per[o["customer_id"]]
        c["orders"] += 1
        if o["status"] in EARNED:
            c["spent"] += o["amount"] or Decimal(0)
        c["last"] = max(c["last"], o["at"]) if c["last"] else o["at"]

    # ---- where: the latest delivery point, else a saved address point
    where: dict = {}
    for cid, lat, lng in (OrderModel.objects.exclude(status="draft").filter(customer_id__isnull=False, shipping_latitude__isnull=False, fulfilment_method="delivery")
                          .order_by("customer_id", "-created_at").values_list("customer_id", "shipping_latitude", "shipping_longitude")):
        where.setdefault(cid, (lat, lng, "order"))
    for owner, lat, lng in (geo.Address.objects.filter(coordinate_latitude__isnull=False).order_by("owner_id", "-is_default", "-updated_at")
                            .values_list("owner_id", "coordinate_latitude", "coordinate_longitude")):
        where.setdefault(owner, (lat, lng, "address"))

    ids = set(per) | set(where)
    users = {u.id: u for u in User.objects.filter(id__in=ids).only("id", "full_name", "phone_number", "username", "created_at")}

    # ---- regions: centroid of their cities; a point belongs to the nearest city's region
    cities = list(geo.City.objects.filter(center_latitude__isnull=False).select_related("region").prefetch_related("translations", "region__translations"))
    reg_points: dict = defaultdict(list)
    reg_name: dict = {}
    for c in cities:
        reg_points[c.region_id].append((c.center_latitude, c.center_longitude))
        reg_name[c.region_id] = uz_name(c.region)

    def region_of(lat, lng):
        best = min(cities, key=lambda c: _haversine2(lat, lng, c.center_latitude, c.center_longitude), default=None)
        return (best.region_id, uz_name(best)) if best else (None, "")

    spends = sorted((v["spent"] for v in per.values() if v["spent"] > 0), reverse=True)
    vip_cut = max(spends[max(0, len(spends) // 10 - 1)] if spends else VIP_MIN, VIP_MIN)

    customers, regions = [], defaultdict(lambda: {"customers": 0, "orders": 0, "revenue": Decimal(0), "buyers": 0, "leads": 0, "vip": 0})
    unplaced = 0
    for cid in ids:
        u = users.get(cid)
        if u is None:
            continue
        stats = per.get(cid, {"orders": 0, "spent": Decimal(0), "last": None})
        spot = where.get(cid)
        if not spot:
            unplaced += 1
            continue
        lat, lng, source = spot
        if stats["orders"] == 0:
            seg = "lead"
        elif stats["spent"] >= vip_cut:
            seg = "vip"
        elif stats["orders"] >= 2:
            seg = "loyal"
        else:
            seg = "new"
        rid, city = region_of(lat, lng)
        r = regions[rid]
        r["customers"] += 1
        r["orders"] += stats["orders"]
        r["revenue"] += stats["spent"]
        r["buyers"] += 1 if stats["orders"] else 0
        r["leads"] += 1 if seg == "lead" else 0
        r["vip"] += 1 if seg == "vip" else 0
        customers.append({
            "id": str(cid), "lat": round(lat, 6), "lng": round(lng, 6), "seg": seg, "src": source,
            "name": u.full_name or u.username or "Ismsiz mijoz", "phone": u.phone_number or "",
            "orders": stats["orders"], "spent": int(stats["spent"]), "last": timezone.localtime(stats["last"]).strftime("%d.%m.%Y") if stats["last"] else "",
            "city": city, "region": reg_name.get(rid, ""), "url": reverse("admin:identity_user_change", args=[cid]),
            "orders_url": reverse("admin:ordering_ordermodel_changelist") + "?" + urlencode({"q": u.phone_number}) if u.phone_number else "",
        })

    branches = list(Store.objects.filter(status="active", latitude__isnull=False, longitude__isnull=False).values("name", "kind", "latitude", "longitude", "city"))
    branch_count: dict = defaultdict(int)
    for b in branches:
        if b["kind"] != "warehouse":
            branch_count[region_of(b["latitude"], b["longitude"])[0]] += 1

    region_rows = []
    total_rev = sum((r["revenue"] for r in regions.values()), Decimal(0)) or Decimal(1)
    for rid, pts in reg_points.items():
        r = regions.get(rid, {"customers": 0, "orders": 0, "revenue": Decimal(0), "buyers": 0, "leads": 0, "vip": 0})
        region_rows.append({
            "id": str(rid), "name": reg_name[rid], "lat": round(sum(p[0] for p in pts) / len(pts), 5), "lng": round(sum(p[1] for p in pts) / len(pts), 5),
            "customers": r["customers"], "orders": r["orders"], "revenue": int(r["revenue"]), "vip": r["vip"], "leads": r["leads"],
            "avg": int(r["revenue"] / r["orders"]) if r["orders"] else 0, "share": round(float(r["revenue"] / total_rev) * 100, 1),
            "branches": branch_count.get(rid, 0),
        })
    region_rows.sort(key=lambda x: (-x["revenue"], -x["customers"], x["name"]))

    seg_n = defaultdict(int)
    for c in customers:
        seg_n[c["seg"]] += 1
    no_branch = [r["name"] for r in region_rows if r["customers"] and not r["branches"]]
    return {
        "period": period_key, "period_label": PERIODS[period_key][0],
        "customers": customers, "regions": region_rows,
        "branches": [{"name": b["name"], "lat": b["latitude"], "lng": b["longitude"], "kind": b["kind"]} for b in branches],
        "segments": [{"key": k, "label": v[0], "color": v[1], "n": seg_n.get(k, 0)} for k, v in SEGMENTS.items()],
        "totals": {"on_map": len(customers), "unplaced": unplaced, "buyers": sum(1 for c in customers if c["orders"]),
                   "revenue": int(sum((Decimal(c["spent"]) for c in customers), Decimal(0))), "regions_active": sum(1 for r in region_rows if r["customers"]),
                   "vip_cut": int(vip_cut), "no_branch": no_branch},
    }


def _allowed(user) -> bool:
    # customers' names and phones: the same right as opening the customer list
    return user.is_active and user.is_staff and (user.is_superuser or user.has_perm("identity.view_user"))


def customers_map_view(request):
    from django.contrib import admin
    from django.core.exceptions import PermissionDenied
    from django.shortcuts import render

    if not _allowed(request.user):
        raise PermissionDenied
    return render(request, "admin/geo_customers.html", {
        **admin.site.each_context(request), "title": "Mijozlar xaritasi",
        "periods": [{"key": k, "label": v[0]} for k, v in PERIODS.items()], "period": request.GET.get("p") if request.GET.get("p") in PERIODS else "90d",
    })


def customers_map_json(request):
    from django.core.cache import cache
    from django.core.exceptions import PermissionDenied
    from django.http import JsonResponse

    if not _allowed(request.user):
        raise PermissionDenied
    key = request.GET.get("p") if request.GET.get("p") in PERIODS else "90d"
    data = cache.get(f"geo:customers:v1:{key}")
    if data is None:
        data = build(key)
        cache.set(f"geo:customers:v1:{key}", data, 300)  # five minutes: a map, not a ledger
    return JsonResponse(data)
