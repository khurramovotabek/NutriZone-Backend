"""
Dashboard → Geo & Location → Manzillar xaritasi: customers' delivery addresses, the stores and the warehouses
(and, on request, the city centres) on one map with the same layer switcher as every geo page. Answers the
dispatcher's questions: where do our customers live, which store is nearest to each of them, which addresses are
far from every store, which have no point at all.
"""
from __future__ import annotations

import uuid

from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.urls import reverse

from apps.geo.infrastructure import models as orm
from apps.geo.infrastructure.admin import names, uz_name
from apps.geo.infrastructure.gateways.geocoder import haversine_km

KINDS = {  # kind → (label, color, shown at first)
    "address": ("Mijoz manzillari", "#4f46e5", True),
    "store": ("Do'konlar", "#ea580c", True),
    "warehouse": ("Omborlar", "#64748b", True),
    "city": ("Shahar markazlari", "#0d9488", False),
}
FAR_KM = 10  # an address farther than this from every store is flagged


def _uuid(value):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _region_q(region_id):
    from django.db.models import Q

    return Q(region_id=region_id) | Q(region__isnull=True, city__region_id=region_id)


def map_points(region_id=None) -> tuple[list[dict], dict]:
    from apps.identity.infrastructure.models import User
    from apps.stores.infrastructure.models import Store

    addresses = orm.Address.objects.filter(coordinate_latitude__isnull=False).select_related("city").prefetch_related("city__translations")
    cities = orm.City.objects.filter(center_latitude__isnull=False).prefetch_related("translations")
    if region_id:
        addresses, cities = addresses.filter(_region_q(region_id)), cities.filter(region_id=region_id)
    addresses = list(addresses[:2000])
    users = {u.id: u for u in User.objects.filter(id__in=[a.owner_id for a in addresses])}
    stores = list(Store.objects.filter(latitude__isnull=False, longitude__isnull=False).exclude(status="inactive"))
    shops = [s for s in stores if s.kind != "warehouse"]

    points, distances = [], []
    for a in addresses:
        u = users.get(a.owner_id)
        nearest = min(((haversine_km(a.coordinate_latitude, a.coordinate_longitude, s.latitude, s.longitude), s) for s in shops), default=None, key=lambda x: x[0])
        if nearest:
            distances.append(nearest[0])
        sub = " · ".join(x for x in ((u.full_name or u.phone_number) if u else "", uz_name(a.city, ""), f"eng yaqin do'kon: {nearest[1].name} ({nearest[0]:.1f} km)" if nearest else "") if x)
        points.append({"kind": "address", "kind_label": "Mijoz manzili", "lat": a.coordinate_latitude, "lng": a.coordinate_longitude, "title": a.line1, "subtitle": sub,
                       "url": reverse("admin:geo_address_change", args=[a.pk]), "color": "#dc2626" if nearest and nearest[0] > FAR_KM else KINDS["address"][1], "id": str(a.pk)})
    for s in stores:
        kind = "warehouse" if s.kind == "warehouse" else "store"
        points.append({"kind": kind, "kind_label": "Ombor" if kind == "warehouse" else "Do'kon", "lat": s.latitude, "lng": s.longitude, "title": s.name,
                       "subtitle": ", ".join(x for x in (s.address, s.district, s.city) if x), "url": reverse("admin:stores_store_change", args=[s.pk]), "color": KINDS[kind][1], "id": str(s.pk)})
    for c in cities:
        points.append({"kind": "city", "kind_label": "Shahar markazi", "lat": c.center_latitude, "lng": c.center_longitude, "title": uz_name(c),
                       "subtitle": " · ".join(v for k, v in names(c).items() if k != "uz"), "url": reverse("admin:geo_city_change", args=[c.pk]), "color": KINDS["city"][1], "id": str(c.pk)})
    stats = {
        "addresses": len(addresses), "without_point": orm.Address.objects.filter(coordinate_latitude__isnull=True).count(),
        "stores": len(shops), "warehouses": len(stores) - len(shops),
        "avg_km": round(sum(distances) / len(distances), 1) if distances else None, "far": sum(1 for d in distances if d > FAR_KM),
    }
    return points, stats


@staff_member_required
def geo_map_view(request):
    region_id = _uuid(request.GET.get("region"))
    points, stats = map_points(region_id)
    focus = request.GET.get("focus") or ""
    regions = [{"id": str(r.pk), "name": uz_name(r), "on": r.pk == region_id} for r in orm.Region.objects.prefetch_related("translations").order_by("code")]
    cards = [
        {"label": "Nuqtali manzillar", "value": stats["addresses"], "tone": "#4f46e5", "icon": "fa-house", "sub": f"{stats['without_point']} tasi nuqtasiz",
         "href": reverse("admin:geo_address_changelist") + "?coord=none"},
        {"label": "Do'konlar", "value": stats["stores"], "tone": "#ea580c", "icon": "fa-store", "sub": f"{stats['warehouses']} ta ombor", "href": reverse("admin:stores_store_changelist")},
        {"label": "Eng yaqin do'kongacha", "value": f"{stats['avg_km']} km" if stats["avg_km"] is not None else "—", "tone": "#0d9488", "icon": "fa-route", "sub": "o'rtacha, to'g'ri chiziqda"},
        {"label": f"{FAR_KM} km dan uzoq", "value": stats["far"], "tone": "#dc2626" if stats["far"] else "#16a34a", "icon": "fa-person-walking-arrow-right", "sub": "qizil pin — yangi do'kon uchun signal"},
    ]
    return render(request, "admin/geo_map.html", {
        **admin.site.each_context(request), "title": "Manzillar xaritasi", "points": points, "cards": cards, "regions": regions, "focus": focus,
        "kinds": [{"key": k, "label": v[0], "color": v[1], "on": v[2], "n": sum(1 for p in points if p["kind"] == k)} for k, v in KINDS.items()],
    })
