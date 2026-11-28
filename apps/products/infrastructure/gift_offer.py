"""
Sovg'a aksiyasi -- the free NutriZone shaker (Dashboard → Katalog → Sovg'a aksiyasi, GiftOfferSettings):

* Rule: an order whose goods come to `min_goods_amount` or more (after coupon / bundle discounts, before coins and
  delivery) and that holds at least one product from a qualifying department (Proteinlar, Geynerlar by default) gets
  the gift product as an extra order line: 1 unit, unit price 0, `is_gift=True`. Only while the gift is in stock
  (at the chosen branch for pickup) -- an order never promises what the warehouse can't hand over.
* Where: website / Mini App / guest checkout (cart place_order) and the Telegram bot checkout call `attach()` inside
  the order's own transaction; checkout preview and the cart show `status()` ("yana X so'm — sheyker sovg'a").
* Product page: every qualifying product recommends the gift product (`pdp_card()`): buy it now, or get it free over
  the threshold.
The gift line is stock like any other line (reserved on confirm, sold on ship); revenue and coins see 0 so'm.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.core.cache import cache

from apps.products.infrastructure import models as orm

DEFAULT_DEPARTMENTS = ("proteinlar", "geynerlar")  # uz slugs of the second level of the owner's category tree
_CFG_KEY = "gift_offer:v1:cfg"
CACHE_TTL = 10 * 60


def invalidate() -> None:
    cache.delete(_CFG_KEY)


def _config() -> dict | None:
    """{variant_id, product_id, min, categories: set[str], recommend} of the active offer, else None (cached)."""
    hit = cache.get(_CFG_KEY)
    if hit is not None:
        return hit or None
    cfg = orm.GiftOfferSettings.load()
    out = None
    if cfg.enabled and cfg.gift_variant_id:
        variant = orm.ProductVariant.objects.filter(id=cfg.gift_variant_id, status="active").values("id", "product_id").first()
        if variant:
            out = {"variant_id": str(variant["id"]), "product_id": str(variant["product_id"]), "min": str(cfg.min_goods_amount),
                   "categories": sorted(_qualifying_categories(cfg)), "recommend": cfg.recommend_on_pdp}
    cache.set(_CFG_KEY, out or False, CACHE_TTL)
    return out


def _qualifying_categories(cfg) -> set[str]:
    """Every category id under the chosen ones (or under the default departments)."""
    parent = {str(c): (str(p) if p else None) for c, p in orm.Category.objects.values_list("id", "parent_id")}
    roots = {str(c) for c in cfg.qualifying_categories.values_list("id", flat=True)}
    if not roots:
        roots = {str(c) for c in orm.CategoryTranslation.objects.filter(locale_code="uz", slug__in=DEFAULT_DEPARTMENTS).values_list("category_id", flat=True)}
    out = set()
    for cid in parent:
        node, seen = cid, set()
        while node and node not in seen:
            if node in roots:
                out.add(cid)
                break
            seen.add(node)
            node = parent.get(node)
    return out


def _uuid(v):
    return v if isinstance(v, uuid.UUID) else uuid.UUID(str(v))


def gift_product_id() -> str | None:
    """The gift's product id while the offer runs (and recommends itself on product pages), else None."""
    cfg = _config()
    return cfg["product_id"] if cfg and cfg["recommend"] else None


def product_qualifies(product_id) -> bool:
    cfg = _config()
    if not cfg:
        return False
    cat = orm.Product.objects.filter(id=product_id).values_list("category_id", flat=True).first()
    return bool(cat) and str(cat) in set(cfg["categories"])


def _items_qualify(cfg, variant_ids) -> bool:
    ids = [_uuid(v) for v in variant_ids if v]
    if not ids:
        return False
    cats = {str(c) for c in orm.ProductVariant.objects.filter(id__in=ids).values_list("product__category_id", flat=True) if c}
    return bool(cats & set(cfg["categories"]))


def _in_stock(cfg, store_id=None) -> bool:
    vid = _uuid(cfg["variant_id"])
    if store_id:
        from apps.stores.infrastructure.models import StoreProductStock

        row = StoreProductStock.objects.filter(store_id=store_id, product_variant_id=vid).values("quantity", "reserved_quantity").first()
        return bool(row) and row["quantity"] - row["reserved_quantity"] > 0
    from apps.stores.infrastructure.availability import sellable

    return sellable([vid]).get(vid, 0) > 0


def _card(cfg, locale: str | None = None) -> dict:
    """The gift product as a small card: names in 3 languages, slug, image, its normal price (its "value")."""
    from apps.products.infrastructure.bundles import _variant_price

    pid = _uuid(cfg["product_id"])
    rows = list(orm.ProductTranslation.objects.filter(product_id=pid).values_list("locale_code", "name", "slug"))
    names = {lc: n for lc, n, _s in rows}
    slugs = {lc: sl for lc, _n, sl in rows}
    from apps.products.infrastructure.selectors import _resolve_media_url

    media = orm.ProductMedia.objects.filter(product_id=pid).order_by("sort_order").values_list("storage_path", flat=True).first()
    image = _resolve_media_url(media) if media else None  # absolute, like every product card (the storefront derives thumbnails)
    lang = locale or "uz"
    price = _variant_price(_uuid(cfg["variant_id"]))
    return {"product_id": cfg["product_id"], "variant_id": cfg["variant_id"], "name": names.get(lang) or names.get("uz") or "",
            "names": names, "slug": slugs.get(lang) or slugs.get("uz") or "", "image_path": image,
            "value": str(Decimal(price).quantize(Decimal("1"))) if price else None}


def status(variant_ids, goods_amount, *, store_id=None, locale: str | None = None) -> dict | None:
    """For checkout preview / cart: is the gift earned, and if not, what is missing. None = no active offer.
    variant_ids = the cart's active lines; goods_amount = goods after discounts (no coins, no delivery)."""
    cfg = _config()
    if not cfg:
        return None
    threshold = Decimal(cfg["min"])
    amount = Decimal(goods_amount or 0)
    items_ok = _items_qualify(cfg, variant_ids)
    stock_ok = _in_stock(cfg, store_id)
    if not stock_ok:
        return None  # nothing to promise
    return {"earned": items_ok and amount >= threshold, "items_qualify": items_ok, "threshold": str(threshold.quantize(Decimal("1"))),
            "missing": str(max(threshold - amount, Decimal("0")).quantize(Decimal("1"))), "gift": _card(cfg, locale)}


def attach(order_id, variant_ids, goods_amount, *, store_id=None) -> bool:
    """Adds the gift line to a just-created order when it earned one. Call inside the order's transaction."""
    from apps.ordering.infrastructure.models import OrderLineItemModel

    cfg = _config()
    if not cfg or Decimal(goods_amount or 0) < Decimal(cfg["min"]) or not _items_qualify(cfg, variant_ids) or not _in_stock(cfg, store_id):
        return False
    if OrderLineItemModel.objects.filter(order_id=order_id, is_gift=True).exists():
        return False
    OrderLineItemModel.objects.create(order_id=order_id, product_variant_id=_uuid(cfg["variant_id"]), quantity=1,
                                      unit_price_amount=Decimal("0"), discount_amount=Decimal("0"), tax_amount=Decimal("0"),
                                      status="active", is_gift=True)
    return True


def pdp_card(product_id, locale: str | None = None) -> dict | None:
    """Product page: recommend the gift product on every qualifying product (not on the gift itself)."""
    cfg = _config()
    if not cfg or not cfg["recommend"] or str(product_id) == cfg["product_id"] or not product_qualifies(product_id):
        return None
    if not _in_stock(cfg):
        return None
    return {**_card(cfg, locale), "threshold": str(Decimal(cfg["min"]).quantize(Decimal("1")))}


def gift_line_ids(order_ids) -> set:
    from apps.ordering.infrastructure.models import OrderLineItemModel

    return set(OrderLineItemModel.objects.filter(order_id__in=list(order_ids), is_gift=True).values_list("id", flat=True))
