"""
"Narx tushsa xabar bering" -- customers watch a variant; a price drop notifies them once per drop.

The trigger is a post_save on PriceListEntryModel (connected in PricingConfig.ready): every way a price changes
(price list editor, bulk ops, repricing documents, the variant page) ends in that row being saved. The check runs
after the transaction commits, so a rolled-back price never notifies anyone.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.pricing.infrastructure.models import PriceListEntryModel, PriceWatchModel

logger = logging.getLogger("nutrizone.app")
MAX_WATCHES_PER_CUSTOMER = 100


def shop_price(variant_id) -> Decimal | None:
    entry = PriceListEntryModel.objects.filter(product_variant_id=variant_id).order_by("created_at").first()
    if entry is None:
        return None
    return entry.sale_price_amount if entry.sale_price_amount is not None else entry.base_price_amount


def watch(customer_id, variant_id) -> PriceWatchModel:
    price = shop_price(variant_id)
    if price is None:
        raise ValueError("Bu variantning narxi yo'q.")
    existing = PriceWatchModel.objects.filter(customer_id=customer_id, product_variant_id=variant_id).first()
    if existing:
        return existing
    if PriceWatchModel.objects.filter(customer_id=customer_id).count() >= MAX_WATCHES_PER_CUSTOMER:
        raise ValueError("Juda ko'p kuzatuv. Avval keraksizlarini o'chiring.")
    return PriceWatchModel.objects.create(customer_id=customer_id, product_variant_id=variant_id, baseline_amount=price)


def unwatch(customer_id, variant_id) -> bool:
    return PriceWatchModel.objects.filter(customer_id=customer_id, product_variant_id=variant_id).delete()[0] > 0


def check_variant(variant_id) -> int:
    """Notifies every watcher whose last seen price is above today's. Returns how many were told."""
    price = shop_price(variant_id)
    if price is None:
        return 0
    told = 0
    for w in PriceWatchModel.objects.filter(product_variant_id=variant_id):
        bar = w.notified_amount if w.notified_amount is not None else w.baseline_amount
        if price >= bar:
            continue
        _notify(w, bar, price)
        w.notified_amount = price
        w.notified_at = timezone.now()
        w.save(update_fields=["notified_amount", "notified_at"])
        told += 1
    return told


def _notify(w: PriceWatchModel, old: Decimal, new: Decimal) -> None:
    from apps.notifications.infrastructure.notify import fmt, notify
    from apps.products.infrastructure.models import ProductTranslation, ProductVariant

    product_id = ProductVariant.objects.filter(id=w.product_variant_id).values_list("product_id", flat=True).first()
    names, slug = {}, ""
    for locale, name, sl in ProductTranslation.objects.filter(product_id=product_id).values_list("locale_code", "name", "slug"):
        names[locale] = name
        if locale == "uz" or not slug:
            slug = sl
    percent = int(round((old - new) / old * 100)) if old else 0
    fallback = names.get("uz") or next(iter(names.values()), "mahsulot")
    i18n = {lang: {"product": names.get(lang) or fallback} for lang in ("uz", "ru", "en")}
    notify(
        w.customer_id, "price_drop",
        {"product": fallback, "i18n": i18n, "old": fmt(old), "new": fmt(new), "percent": percent},
        link=f"/products/{slug}?variant={w.product_variant_id}" if slug else "",
        dedupe_key=f"price_drop:{w.id}:{int(new)}",
    )


def on_entry_saved(sender, instance: PriceListEntryModel, **kwargs) -> None:
    variant_id = instance.product_variant_id
    if not PriceWatchModel.objects.filter(product_variant_id=variant_id).exists():
        return

    def _run():
        try:
            check_variant(variant_id)
        except Exception:  # a notification problem must never break a price save
            logger.exception("price watch check failed for %s", variant_id)

    transaction.on_commit(_run)
