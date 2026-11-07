"""
What delivery costs the customer.

Two zones, both priced on the dashboard (DeliverySettings, Buyurtmalar -> Yetkazib berish narxlari):
- Tashkent city, delivered by Yandex Delivery: a starting price plus a price per km of (estimated) road distance from
  the nearest branch, never more than the cap ("30 000 so'mgacha"). An address without a map point pays the cap.
- Every other region (Tashkent region included), sent by BTS: a base price for a parcel up to N kg ("30 000 so'mdan"),
  then a price for every further started kilogram. The parcel weight comes from the variants' labelled weight
  (g / kg / ml / l), an assumed weight for items labelled in tablets/capsules, plus the packaging.
Picking the order up at a branch is always free and never reaches this module. An optional threshold makes delivery
free for large orders.

Checkout (apps/cart/interfaces/api/v1/views.py) freezes `quote_for_address()` onto the order
(OrderModel.shipping_amount / delivery_zone / delivery_carrier); the checkout preview shows the same quote, and
`public_options()` (GET /api/v1/orders/delivery-options) gives the storefront the "from / up to" prices.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

TASHKENT = "tashkent"
REGIONS = "regions"
# geo.Region codes that count as Tashkent city (the region "Toshkent viloyati" UZ-TO is a region, sent by BTS)
TASHKENT_REGION_CODES = frozenset({"TGCITYR"})
ROAD_FACTOR = 1.3  # straight line -> city road distance
_ROUND_TO = Decimal("1000")  # prices end in whole thousands of so'm

_KG_PER_UNIT = {"g": 0.001, "kg": 1.0, "ml": 0.001, "l": 1.0}


@dataclass(frozen=True)
class DeliveryQuote:
    zone: str
    carrier: str
    fee: Decimal  # what the customer pays (0 when the free threshold is reached)
    base_fee: Decimal  # the price before the free threshold
    eta: str
    free_from: Decimal | None
    weight_kg: float | None = None  # regions: the parcel weight the price is based on
    distance_km: float | None = None  # Tashkent: estimated road distance from the nearest branch

    @property
    def is_free(self) -> bool:
        return self.fee == 0


def zone_for_region_code(code: str | None) -> str:
    return TASHKENT if (code or "").upper() in TASHKENT_REGION_CODES else REGIONS


def _eta(cfg, zone: str, lang: str) -> str:
    lang = lang if lang in ("uz", "ru", "en") else "uz"
    return getattr(cfg, f"{zone}_eta_{lang}") or getattr(cfg, f"{zone}_eta_uz") or ""


def _round_up(value: Decimal) -> Decimal:
    return (value / _ROUND_TO).to_integral_value(rounding=ROUND_CEILING) * _ROUND_TO


def tashkent_fee(cfg, distance_km: float | None) -> Decimal:
    cap = Decimal(cfg.tashkent_fee or 0)
    if distance_km is None or not cfg.tashkent_per_km:
        return cap
    fee = Decimal(cfg.tashkent_min_fee or 0) + Decimal(cfg.tashkent_per_km) * Decimal(str(round(distance_km, 2)))
    return min(cap, max(Decimal(cfg.tashkent_min_fee or 0), _round_up(fee)))


def regions_fee(cfg, weight_kg: float | None, region_id=None) -> Decimal:
    """The region's own BTS rate (RegionDeliveryRate) when the dashboard has one, else the general regions tariff."""
    from apps.ordering.infrastructure.models import RegionDeliveryRate

    rate = RegionDeliveryRate.objects.filter(region_id=region_id).first() if region_id else None
    base = Decimal(rate.base_fee if rate else cfg.regions_fee or 0)
    per_kg = Decimal(rate.extra_per_kg if rate and rate.extra_per_kg is not None else cfg.regions_extra_per_kg or 0)
    if weight_kg is None:
        return base
    extra_kg = max(0, math.ceil(round(weight_kg - float(cfg.regions_base_kg or 0), 3)))
    return base + per_kg * extra_kg


def parcel_weight_kg(items, cfg=None) -> float:
    """items: [(variant_id, quantity)] -> estimated parcel weight in kg (labelled weights + assumed ones + packaging)."""
    from apps.ordering.infrastructure.models import DeliverySettings
    from apps.products.infrastructure.models import ProductVariant

    cfg = cfg or DeliverySettings.load()
    items = [(str(v), int(q)) for v, q in items if q]
    if not items:
        return 0.0
    rows = {str(r["id"]): r for r in ProductVariant.objects.filter(pk__in=[v for v, _q in items]).values("id", "weight_value", "weight_unit")}
    unknown = float(cfg.unknown_item_kg or 0)
    total = float(cfg.packaging_kg or 0)
    for variant_id, qty in items:
        r = rows.get(variant_id)
        per = _KG_PER_UNIT.get((r or {}).get("weight_unit") or "")
        kg = r["weight_value"] * per if r and per and r.get("weight_value") else unknown
        total += kg * qty
    return round(total, 3)


def distance_to_nearest_branch_km(lat: float | None, lng: float | None) -> float | None:
    """Estimated road km from the nearest active branch/warehouse with a map point (straight line x ROAD_FACTOR)."""
    if lat is None or lng is None:
        return None
    from apps.stores.infrastructure.models import Store

    best = None
    for s_lat, s_lng in Store.objects.filter(status="active", latitude__isnull=False, longitude__isnull=False).values_list("latitude", "longitude"):
        d = _haversine_km(lat, lng, s_lat, s_lng)
        best = d if best is None or d < best else best
    return round(best * ROAD_FACTOR, 2) if best is not None else None


def _haversine_km(lat1, lng1, lat2, lng2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def quote(zone: str, goods_total: Decimal | int | str, lang: str = "uz", *, weight_kg: float | None = None, distance_km: float | None = None,
          region_id=None) -> DeliveryQuote:
    from apps.ordering.infrastructure.models import DeliverySettings

    cfg = DeliverySettings.load()
    zone = TASHKENT if zone == TASHKENT else REGIONS
    base = tashkent_fee(cfg, distance_km) if zone == TASHKENT else regions_fee(cfg, weight_kg, region_id)
    free_from = Decimal(cfg.free_from) if cfg.free_from else None
    fee = Decimal("0") if free_from is not None and Decimal(str(goods_total or 0)) >= free_from else base
    return DeliveryQuote(zone=zone, carrier=getattr(cfg, f"{zone}_carrier") or "", fee=fee, base_fee=base, eta=_eta(cfg, zone, lang), free_from=free_from,
                         weight_kg=weight_kg if zone == REGIONS else None, distance_km=distance_km if zone == TASHKENT else None)


def _address_row(address_id) -> dict | None:
    from apps.geo.infrastructure.models import Address

    return Address.objects.filter(pk=address_id).values("region_id", "region__code", "city__region_id", "city__region__code", "coordinate_latitude", "coordinate_longitude").first()


def region_code_for_address(address_id: uuid.UUID | str) -> str | None:
    """The address's region code -- its own region, else its city's region."""
    row = _address_row(address_id)
    return (row["region__code"] or row["city__region__code"]) if row else None


def quote_for_address(address_id: uuid.UUID | str, goods_total: Decimal | int | str, lang: str = "uz", items=()) -> DeliveryQuote:
    """items: [(variant_id, quantity)] -- the parcel the regions price is weighed on."""
    row = _address_row(address_id) or {}
    zone = zone_for_region_code(row.get("region__code") or row.get("city__region__code"))
    if zone == TASHKENT:
        return quote(zone, goods_total, lang, distance_km=distance_to_nearest_branch_km(row.get("coordinate_latitude"), row.get("coordinate_longitude")))
    return quote(zone, goods_total, lang, weight_kg=parcel_weight_kg(items) if items else None, region_id=row.get("region_id") or row.get("city__region_id"))


def public_options(lang: str = "uz") -> dict:
    """What the storefront shows before an address is known: Tashkent "up to" the cap, the regions "from" the base
    price (up to N kg), which region ids are Tashkent city (an address carries region_id), and the free threshold."""
    from apps.geo.infrastructure.models import Region
    from apps.ordering.infrastructure.models import DeliverySettings

    cfg = DeliverySettings.load()
    return {
        "currency": "UZS",
        "zones": {
            TASHKENT: {"pricing": "up_to", "fee": str(Decimal(cfg.tashkent_fee or 0)), "min_fee": str(Decimal(cfg.tashkent_min_fee or 0)),
                       "carrier": cfg.tashkent_carrier or "", "eta": _eta(cfg, TASHKENT, lang)},
            REGIONS: {"pricing": "from", "fee": str(min([Decimal(cfg.regions_fee or 0), *cfg.region_rates.values_list("base_fee", flat=True)])), "base_kg": str(Decimal(cfg.regions_base_kg or 0).normalize()),
                      "extra_per_kg": str(Decimal(cfg.regions_extra_per_kg or 0)), "carrier": cfg.regions_carrier or "", "eta": _eta(cfg, REGIONS, lang)},
        },
        "tashkent_region_ids": [str(pk) for pk in Region.objects.filter(code__in=TASHKENT_REGION_CODES).values_list("pk", flat=True)],
        "free_from": str(cfg.free_from) if cfg.free_from else None,
        "pickup_fee": "0",
    }
