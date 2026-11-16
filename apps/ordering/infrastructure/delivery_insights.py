"""
Yetkazib berish narxlari → analysis panels: what delivery actually earned and cost, where parcels go, and settings
that quietly make prices wrong (branches without a map point, products without a weight).

* Zone of an order = its frozen `delivery_zone`; older orders (before paid delivery) are placed by their shipping city
  through the geo reference (the same lookup as the dashboard regions map).
* Delivery income = `shipping_amount` frozen on delivered/completed delivery orders; courier cost = DeliveryAssignment
  fees of the same orders -- so the margin is honest only where courier fees are written down (shown as coverage).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.ordering.infrastructure import models as orm

ZERO = Decimal("0")
EARNED = ("delivered", "completed")


def summary(days: int = 90) -> dict:
    from apps.ordering.infrastructure.delivery_pricing import TASHKENT_REGION_CODES
    from apps.platform.infrastructure.regions_report import _resolve, region_index

    since = timezone.now() - timedelta(days=days)
    orders = list(orm.OrderModel.objects.exclude(status="draft").filter(placed_at__gte=since)
                  .values("id", "status", "fulfilment_method", "delivery_zone", "shipping_city", "shipping_region", "shipping_amount"))
    lookup, regions = region_index("uz")
    fees = dict(orm.DeliveryAssignment.objects.filter(order_id__in=[o["id"] for o in orders], fee__isnull=False).values_list("order_id", "fee"))
    zones = {k: {"orders": 0, "earned": 0, "income": ZERO, "cost": ZERO, "with_fee": 0, "free": 0} for k in ("tashkent", "regions", "pickup")}
    cities: dict = defaultdict(lambda: {"orders": 0, "income": ZERO})
    region_rows: dict = defaultdict(lambda: {"orders": 0, "income": ZERO})
    for o in orders:
        if o["fulfilment_method"] == "pickup":
            zone = "pickup"
        else:
            code = _resolve(lookup, o["shipping_city"], o["shipping_region"])
            zone = o["delivery_zone"] or ("tashkent" if code in TASHKENT_REGION_CODES else "regions")
        z = zones[zone]
        z["orders"] += 1
        if o["status"] not in EARNED:
            continue
        z["earned"] += 1
        fee = o["shipping_amount"] or ZERO
        z["income"] += fee
        if zone != "pickup" and fee == 0:
            z["free"] += 1
        if o["id"] in fees:
            z["cost"] += fees[o["id"]]
            z["with_fee"] += 1
        if zone != "pickup":
            city = (o["shipping_city"] or "—").strip() or "—"
            cities[city]["orders"] += 1
            cities[city]["income"] += fee
            code = _resolve(lookup, o["shipping_city"], o["shipping_region"])
            name = regions.get(code, {}).get("name") or "Aniqlanmagan"
            region_rows[name]["orders"] += 1
            region_rows[name]["income"] += fee
    total = sum(z["orders"] for z in zones.values())
    for z in zones.values():
        z["share"] = round(z["orders"] * 100 / total) if total else 0
        z["avg"] = (z["income"] / z["earned"]).quantize(Decimal("1")) if z["earned"] else ZERO
        z["margin"] = z["income"] - z["cost"] if z["with_fee"] else None
        z["coverage"] = round(z["with_fee"] * 100 / z["earned"]) if z["earned"] else 0
    return {"days": days, "total": total, "zones": zones,
            "regions": sorted(({"name": k, **v} for k, v in region_rows.items()), key=lambda r: (-r["orders"], r["name"]))[:8]}


def health(cfg) -> list[dict]:
    """Settings that make a price silently wrong -- each with what happens and how to fix it."""
    from apps.products.infrastructure.models import ProductVariant
    from apps.stores.infrastructure.models import Store

    out = []
    no_point = list(Store.objects.filter(status="active").filter(latitude__isnull=True).values_list("name", flat=True))
    with_point = Store.objects.filter(status="active", latitude__isnull=False, longitude__isnull=False).count()
    if not with_point:
        out.append({"level": "danger", "text": "Hech bir filialda xarita nuqtasi yo'q — Toshkent ichida masofa hisoblanmaydi, hamma maksimal narxni to'laydi.",
                    "fix": "Do'konlar → filial → koordinatalar", "url": "/django-admin/stores/store/"})
    elif no_point:
        out.append({"level": "warning", "text": f"{len(no_point)} ta faol filialda xarita nuqtasi yo'q. Masofa faqat nuqtasi bor filiallardan hisoblanadi.",
                    "names": ", ".join(no_point[:6]) + ("…" if len(no_point) > 6 else ""), "fix": "Koordinatalarni kiriting", "url": "/django-admin/stores/store/"})
    variants = ProductVariant.objects.filter(is_active=True) if hasattr(ProductVariant, "is_active") else ProductVariant.objects.all()
    total = variants.count()
    no_weight = variants.filter(weight_value__isnull=True).count()
    if total and no_weight:
        pct = round(no_weight * 100 / total)
        out.append({"level": "warning" if pct > 20 else "info",
                    "text": f"{no_weight} ta variantda ({pct}%) og'irlik kiritilmagan — viloyat posilkasida har biri {cfg.unknown_item_kg} kg deb olinadi.",
                    "fix": "Mahsulotlar → variant → og'irlik", "url": "/django-admin/products/product/"})
    if not cfg.free_from:
        out.append({"level": "info", "text": "Bepul yetkazish chegarasi o'rnatilmagan. Ko'p do'konlar katta xaridda yetkazishni bepul qiladi — o'rtacha chekni oshiradi.",
                    "fix": "«Bepul yetkazish» bo'limi", "url": "#id_free_from"})
    if getattr(cfg, "regions_pricing", "flat") == "bts" and cfg.bts_fuel_surcharge_percent:
        out.append({"level": "info", "text": f"BTS yoqilg'i ustamasi {cfg.bts_fuel_surcharge_percent}% qo'shilmoqda (qishki davr). Bahorda 0 ga qaytaring.",
                    "fix": "Viloyatlar bo'limi", "url": "#id_bts_fuel_surcharge_percent"})
    if not out:
        out.append({"level": "ok", "text": "Sozlamalar to'liq: filiallar xaritada, mahsulotlarda og'irlik bor.", "fix": "", "url": ""})
    return out


def calc_options() -> dict:
    """Regions and their cities for the calculator selects (Uzbek names)."""
    from apps.geo.infrastructure.models import CityTranslation, RegionTranslation

    regions = {code: name for code, name in RegionTranslation.objects.filter(locale_code="uz").values_list("region__code", "name")}
    cities = defaultdict(list)
    for rcode, ccode, name in CityTranslation.objects.filter(locale_code="uz").values_list("city__region__code", "city__code", "name"):
        cities[rcode].append({"code": ccode, "name": name})
    return {"regions": [{"code": c, "name": n, "cities": sorted(cities.get(c, []), key=lambda x: x["name"])} for c, n in sorted(regions.items(), key=lambda kv: kv[1])]}


def calculate(region_code: str, city_code: str = "", weight_kg: float | None = None, distance_km: float | None = None, goods_total=0) -> dict:
    """The price a shopper would see, with the parts it is made of."""
    from apps.geo.infrastructure.models import Region
    from apps.ordering.infrastructure import delivery_pricing as dp

    zone = dp.zone_for_region_code(region_code)
    region_id = Region.objects.filter(code=region_code).values_list("id", flat=True).first()
    q = dp.quote(zone, goods_total or 0, "uz", weight_kg=weight_kg, distance_km=distance_km, region_id=region_id, region_code=region_code, city_code=city_code or None)
    cfg = orm.DeliverySettings.load()
    parts = []
    if zone == dp.TASHKENT:
        if distance_km is None:
            parts.append(f"Masofa noma'lum — maksimal narx: {int(cfg.tashkent_fee):,} so'm".replace(",", " "))
        else:
            raw = Decimal(cfg.tashkent_min_fee or 0) + Decimal(cfg.tashkent_per_km or 0) * Decimal(str(distance_km))
            parts.append(f"{int(cfg.tashkent_min_fee):,} + {int(cfg.tashkent_per_km):,} × {distance_km} km = {int(raw):,} so'm".replace(",", " "))
            if q.base_fee >= Decimal(cfg.tashkent_fee or 0):
                parts.append(f"maksimal narx bilan cheklandi: {int(cfg.tashkent_fee):,} so'm".replace(",", " "))
    else:
        rate = orm.RegionDeliveryRate.objects.filter(region_id=region_id).first() if region_id else None
        if rate:
            parts.append("Viloyat uchun alohida tarif qo'llandi")
        elif getattr(cfg, "regions_pricing", "flat") == "bts":
            from apps.ordering.infrastructure import bts_tariff

            kg = weight_kg if weight_kg is not None else float(cfg.regions_base_kg or 1)
            billable = bts_tariff.billable_kg(kg, kg * float(cfg.parcel_cm3_per_kg or 0))
            parts.append(f"BTS {bts_tariff.zone_for(region_code)}-zona · hisoblanadigan og'irlik {billable} kg")
            parts.append("eshikkacha yetkazish" if cfg.bts_door_delivery else "BTS ofisigacha")
            if cfg.bts_fuel_surcharge_percent:
                parts.append(f"yoqilg'i ustamasi +{cfg.bts_fuel_surcharge_percent}%")
        else:
            parts.append(f"Oddiy qoida: {cfg.regions_base_kg} kg gacha {int(cfg.regions_fee):,} so'm, keyin har kg +{int(cfg.regions_extra_per_kg):,}".replace(",", " "))
    if q.fee == 0 and q.base_fee > 0:
        parts.append("buyurtma summasi bepul yetkazish chegarasidan yuqori — mijoz to'lamaydi")
    return {"zone": zone, "zone_label": "Toshkent shahri" if zone == dp.TASHKENT else "Viloyatlar", "carrier": q.carrier, "fee": int(q.fee), "base_fee": int(q.base_fee),
            "eta": q.eta, "parts": parts}
