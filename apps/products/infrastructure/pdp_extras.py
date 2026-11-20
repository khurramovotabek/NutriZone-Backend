"""
The product page's "extras" in one cheap call (`GET /api/v1/products/<slug>/extras`):

* bundle         "Birga arzonroq" -- the companion product, its variant, both prices and the discount (bundles.py)
* trust          brand is an official distributor (Brand.is_official_distributor) + per variant the expiry of the
                 batch a customer would get now (the earliest non-expired batch on hand, FEFO), when batches are kept
* price_history  per active variant: the shop price over the last 180 days from the price-change journal, with
                 min / max / current and whether today's price is the lowest of the last 90 days
* watching       the signed-in customer's "tell me when it's cheaper" variants
"""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from django.utils import timezone

from apps.products.infrastructure import bundles
from apps.products.infrastructure import models as orm

HISTORY_DAYS = 180
LOWEST_WINDOW_DAYS = 90


def _money(v) -> str | None:
    return None if v is None else str(Decimal(v).quantize(Decimal("1")))


def _bundle(product, locale) -> dict | None:
    offer = bundles.offer_for(product.id)
    if not offer:
        return None
    from apps.products.infrastructure.selectors import _cards_with_price_and_rating

    companion = orm.Product.objects.filter(id=offer["companion_product_id"], status="published").prefetch_related("translations", "media", "variants").first()
    if companion is None:
        return None
    card = _cards_with_price_and_rating([companion], locale)[0]
    variant = orm.ProductVariant.objects.filter(id=offer["companion_variant_id"]).select_related("flavour").first()
    price = bundles._variant_price(offer["companion_variant_id"])
    if variant is None or not price:
        return None
    percent = Decimal(offer["percent"])
    bundle_price = (price * (Decimal("100") - percent) / Decimal("100")).quantize(Decimal("1"))
    weight = f"{format(Decimal(str(variant.weight_value)).normalize(), "f")} {variant.weight_unit}" if variant.weight_value else ""
    flavour = ""
    if variant.flavour_id:
        rows = {t.locale_code: t.name for t in variant.flavour.translations.all()} if hasattr(variant.flavour, "translations") else {}
        flavour = rows.get(locale or "uz") or rows.get("uz") or ""
    return {
        "source": offer["source"],
        "percent": format(percent.normalize(), "f"),
        "product": {k: card.get(k) for k in ("id", "slug", "name", "primary_image_path", "brand_id", "rating_average", "rating_count")},
        "variant_id": offer["companion_variant_id"],
        "variant_label": " · ".join(x for x in (weight.strip(), flavour) if x),
        "price": _money(price),
        "bundle_price": _money(bundle_price),
        "saving": _money(price - bundle_price),
    }


def _trust(product, variant_ids) -> dict:
    from apps.stores.infrastructure.models import StockBatch

    today = timezone.localdate()
    official = False
    if product.brand_id:
        official = bool(orm.Brand.objects.filter(id=product.brand_id).values_list("is_official_distributor", flat=True).first())
    expiry: dict[str, str] = {}
    rows = (StockBatch.objects.filter(product_variant_id__in=variant_ids, quantity__gt=0, expiry_date__gt=today, store__status="active")
            .exclude(expiry_date__year__lt=today.year - 2)
            .values_list("product_variant_id", "expiry_date").order_by("expiry_date"))
    for vid, exp in rows:
        expiry.setdefault(str(vid), exp.isoformat())
    return {"official_distributor": official, "expiry": expiry}


def _price_history(variant_ids) -> dict:
    from apps.pricing.infrastructure.models import PriceHistoryEntryModel, PriceListEntryModel

    now = timezone.now()
    start = now - dt.timedelta(days=HISTORY_DAYS)
    current = {}
    for e in PriceListEntryModel.objects.filter(product_variant_id__in=variant_ids).order_by("created_at"):
        current.setdefault(e.product_variant_id, e.sale_price_amount if e.sale_price_amount is not None else e.base_price_amount)
    entries: dict = {}
    for vid, old, new, at in (PriceHistoryEntryModel.objects.filter(product_variant_id__in=variant_ids, price_type="base")
                              .order_by("changed_at").values_list("product_variant_id", "old_amount", "new_amount", "changed_at")):
        entries.setdefault(vid, []).append((old, new, at))
    out = {}
    for vid in variant_ids:
        now_price = current.get(vid)
        if now_price is None:
            continue
        hist = entries.get(vid, [])
        before = [h for h in hist if h[2] < start]
        inside = [h for h in hist if h[2] >= start]
        points: list[list] = []
        opening = before[-1][1] if before else (inside[0][0] if inside and inside[0][0] is not None else None)
        if opening is not None:
            points.append([start.date().isoformat(), _money(opening)])
        last_day = None
        for _old, new, at in inside:
            day = timezone.localtime(at).date().isoformat()
            if points and points[-1][0] == day:
                points[-1][1] = _money(new)
            else:
                points.append([day, _money(new)])
            last_day = day
        today = timezone.localdate().isoformat()
        if not points or points[-1][1] != _money(now_price) or last_day != today:
            points.append([today, _money(now_price)])
        values = [Decimal(p[1]) for p in points]
        window_start = (timezone.localdate() - dt.timedelta(days=LOWEST_WINDOW_DAYS)).isoformat()
        recent = [Decimal(p[1]) for p in points if p[0] >= window_start] + ([Decimal(p[1]) for p in points if p[0] < window_start][-1:])
        out[str(vid)] = {
            "points": points,
            "min": _money(min(values)),
            "max": _money(max(values)),
            "current": _money(now_price),
            "changes": len(inside),
            "lowest_90d": len(set(recent)) > 1 and Decimal(now_price) <= min(recent),
        }
    return out


def extras(product_id, *, customer_id=None, locale: str | None = None) -> dict:
    product = orm.Product.objects.filter(id=product_id).first()
    if product is None:
        return {}
    variant_ids = list(orm.ProductVariant.objects.filter(product_id=product_id, status="active").values_list("id", flat=True))
    watching: list[str] = []
    if customer_id:
        from apps.pricing.infrastructure.models import PriceWatchModel

        watching = [str(v) for v in PriceWatchModel.objects.filter(customer_id=customer_id, product_variant_id__in=variant_ids).values_list("product_variant_id", flat=True)]
    try:
        bundle = _bundle(product, locale)
    except Exception:  # a broken companion never takes the product page down
        import logging

        logging.getLogger("nutrizone.app").exception("bundle offer failed for %s", product_id)
        bundle = None
    return {
        "bundle": bundle,
        "trust": _trust(product, variant_ids),
        "price_history": _price_history(variant_ids),
        "watching": watching,
    }


def as_uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None
