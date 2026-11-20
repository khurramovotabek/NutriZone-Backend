"""
"Birga arzonroq" -- buy a product together with its companion and the companion line gets a discount.

* `offer_for(product_id)`  the one companion offered on a product page: a staff pick (ProductBundle, Dashboard →
  Katalog → Birga arzonroq) wins; otherwise -- when BundleSettings.auto_enabled -- an in-stock add-on from another
  department (a shaker or creatine next to a protein, never a second protein; within `companion_categories` when
  set, priced at most `max_companion_share` of the main product): first what customers bought together with it,
  else the best seller of those departments; and only when the discounted price still clears the
  known purchase cost by `min_margin_percent`. Cached for an hour so the page and the cart agree.
* `cart_discount(lines)`  what checkout takes off for every (product, companion) pair actually in the cart:
  percent × the companion line's unit price × the units that have a partner. Each unit is discounted once.
"""
from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal

from django.core.cache import cache

from apps.products.infrastructure import models as orm

CACHE_TTL = 60 * 60
_KEY = "bundle:v2:{}"


def _settings() -> orm.BundleSettings:
    return orm.BundleSettings.load()


def invalidate(product_id=None) -> None:
    if product_id:
        cache.delete(_KEY.format(product_id))


def _sellable_default(product_id) -> tuple[uuid.UUID | None, int]:
    """The companion's default variant (else its first in-stock active variant) and how many units can be sold."""
    from apps.stores.infrastructure.availability import sellable

    variants = list(orm.ProductVariant.objects.filter(product_id=product_id, status="active").order_by("-is_default", "created_at").values_list("id", "is_default"))
    if not variants:
        return None, 0
    stock = sellable([v for v, _d in variants])
    for vid, _d in variants:
        if stock.get(vid, 0) > 0:
            return vid, stock.get(vid, 0)
    return variants[0][0], 0


def _variant_price(variant_id) -> Decimal | None:
    from apps.pricing.infrastructure.models import PriceListEntryModel

    entry = PriceListEntryModel.objects.filter(product_variant_id=variant_id).order_by("created_at").first()
    if entry is None:
        return None
    return entry.sale_price_amount if entry.sale_price_amount is not None else entry.base_price_amount


def _margin_ok(variant_id, price: Decimal, percent: Decimal, min_margin: Decimal) -> bool:
    """The discounted price must clear the best known purchase cost (receipt / catalog cost) by min_margin %; an
    unknown cost (only the selling price stands in) never blocks -- there is nothing to protect against."""
    from apps.stores.infrastructure.count_service import cost_info

    cost, source = cost_info([variant_id]).get(variant_id, (Decimal("0"), None))
    if source not in ("receipt", "catalog") or not cost:
        return True
    discounted = price * (Decimal("100") - percent) / Decimal("100")
    return discounted >= Decimal(cost) * (Decimal("100") + min_margin) / Decimal("100")


def _category_roots() -> dict[str, str]:
    """{category_id: its top-level ancestor id} for the whole tree (about a hundred rows, one query)."""
    parent = {str(c): (str(p) if p else None) for c, p in orm.Category.objects.values_list("id", "parent_id")}
    roots: dict[str, str] = {}
    for cid in parent:
        node, seen = cid, set()
        while parent.get(node) and node not in seen:
            seen.add(node)
            node = parent[node]
        roots[cid] = node
    return roots


def _compute(product_id) -> dict | None:
    pick = (orm.ProductBundle.objects.filter(product_id=product_id, is_active=True, companion__status="published", companion__is_deleted=False)
            .order_by("-updated_at").first())
    if pick is not None:
        variant_id, stock = _sellable_default(pick.companion_id)
        if variant_id and stock > 0:
            return {"companion_product_id": str(pick.companion_id), "companion_variant_id": str(variant_id), "percent": str(pick.discount_percent), "source": "curated"}

    cfg = _settings()
    if not cfg.auto_enabled:
        return None
    from apps.products.infrastructure.selectors import RecommendationSelector

    main = orm.Product.objects.filter(id=product_id).values("category_id").first()
    roots = _category_roots()
    main_root = roots.get(str(main["category_id"])) if main and main["category_id"] else None
    cards = RecommendationSelector().for_product(uuid.UUID(str(product_id)), limit=12)
    # a companion completes the purchase (shaker / creatine next to a protein) -- never a second product of the same
    # kind, so the automatic pair only takes products from another top-level category (whey isolate and whey blend
    # sit in different leaves of the same "Protein" branch), and one priced as an add-on (max_companion_share)
    if not main_root:
        return None
    allowed = _allowed_categories(cfg, roots)
    main_variant, _stock = _sellable_default(product_id)
    main_price = _variant_price(main_variant) if main_variant else None
    if not main_price:
        return None
    ceiling = main_price * cfg.max_companion_share / Decimal("100")

    def fits(category_id, price) -> bool:
        cid = str(category_id) if category_id else None
        if not cid or roots.get(cid) in (None, main_root):
            return False
        if allowed is not None and cid not in allowed:
            return False
        return bool(price) and Decimal(price) <= ceiling

    # 1) bought together with this product, 2) the best sellers of the companion departments
    for card in cards:
        if card.get("stock_status") == "out_of_stock" or not fits(card.get("category_id"), card.get("price")):
            continue
        variant_id, stock = _sellable_default(card["id"])
        price = _variant_price(variant_id) if variant_id and stock > 0 else None
        if price and _margin_ok(variant_id, price, cfg.auto_percent, cfg.min_margin_percent):
            return {"companion_product_id": str(card["id"]), "companion_variant_id": str(variant_id), "percent": str(cfg.auto_percent), "source": "auto"}
    for row in _companion_pool():
        if row["product_id"] == str(product_id) or not fits(row["category_id"], row["price"]):
            continue
        if _margin_ok(row["variant_id"], Decimal(row["price"]), cfg.auto_percent, cfg.min_margin_percent):
            return {"companion_product_id": row["product_id"], "companion_variant_id": row["variant_id"], "percent": str(cfg.auto_percent), "source": "auto"}
    return None


def _allowed_categories(cfg, roots: dict[str, str]) -> set[str] | None:
    """The configured companion departments with everything under them; None = any other department."""
    picked = {str(c) for c in cfg.companion_categories.values_list("id", flat=True)} if cfg.pk else set()
    if not picked:
        return None
    parent = {str(c): (str(p) if p else None) for c, p in orm.Category.objects.values_list("id", "parent_id")}
    out = set()
    for cid in parent:
        node, seen = cid, set()
        while node and node not in seen:
            if node in picked:
                out.add(cid)
                break
            seen.add(node)
            node = parent.get(node)
    return out


POOL_KEY = "bundle:v2:pool"


def _companion_pool() -> list[dict]:
    """Every published, in-stock product's default variant with its price and units sold, best sellers first
    (cheaper first on a tie). Cached for an hour -- one pass over the catalog, shared by every product page."""
    hit = cache.get(POOL_KEY)
    if hit is not None:
        return hit
    from apps.pricing.infrastructure.models import PriceListEntryModel
    from apps.products.infrastructure.smart_search import _units_sold_by_product
    from apps.stores.infrastructure.availability import sellable

    variants = list(orm.ProductVariant.objects.filter(status="active", product__status="published", product__is_deleted=False)
                    .order_by("product_id", "-is_default", "created_at").values_list("id", "product_id", "product__category_id"))
    stock = sellable([v for v, _p, _c in variants])
    chosen: dict = {}
    for vid, pid, cid in variants:
        if pid not in chosen and stock.get(vid, 0) > 0:
            chosen[pid] = (vid, cid)
    prices = {}
    for e in PriceListEntryModel.objects.filter(product_variant_id__in=[v for v, _c in chosen.values()]).order_by("created_at"):
        prices.setdefault(e.product_variant_id, e.sale_price_amount if e.sale_price_amount is not None else e.base_price_amount)
    sold = _units_sold_by_product()
    pool = [{"product_id": str(pid), "variant_id": str(vid), "category_id": str(cid) if cid else None, "price": str(prices[vid]), "sold": sold.get(str(pid), 0)}
            for pid, (vid, cid) in chosen.items() if prices.get(vid)]
    pool.sort(key=lambda r: (-r["sold"], Decimal(r["price"])))
    cache.set(POOL_KEY, pool, CACHE_TTL)
    return pool


def offer_for(product_id) -> dict | None:
    """{companion_product_id, companion_variant_id, percent, source} or None (cached; `False` caches "no offer")."""
    key = _KEY.format(product_id)
    hit = cache.get(key)
    if hit is None:
        hit = _compute(product_id) or False
        cache.set(key, hit, CACHE_TTL)
    return hit or None


def cart_discount(lines: list[tuple]) -> tuple[Decimal, list[dict]]:
    """
    lines = [(variant_id, unit_amount: Decimal, quantity: int)] of the active cart lines.
    Returns (total discount, [{product_id, companion_product_id, percent, units, amount}]).
    """
    if len(lines) < 2:
        return Decimal("0"), []
    variant_ids = [uuid.UUID(str(v)) for v, _a, _q in lines]
    product_of = {str(v): str(p) for v, p in orm.ProductVariant.objects.filter(id__in=variant_ids).values_list("id", "product_id")}
    qty_by_product: dict[str, int] = {}
    companion_lines: dict[str, list[list]] = {}  # product -> [[unit_amount, free units]], cheapest discount first
    for v, amount, qty in lines:
        pid = product_of.get(str(v))
        if not pid or qty <= 0:
            continue
        qty_by_product[pid] = qty_by_product.get(pid, 0) + qty
        companion_lines.setdefault(pid, []).append([Decimal(amount), qty])
    if len(qty_by_product) < 2:
        return Decimal("0"), []

    total = Decimal("0")
    applied: list[dict] = []
    for pid, main_units in qty_by_product.items():
        offer = offer_for(pid)
        if not offer or offer["companion_product_id"] not in companion_lines or offer["companion_product_id"] == pid:
            continue
        percent = Decimal(offer["percent"])
        left = main_units
        amount = Decimal("0")
        units = 0
        for line in sorted(companion_lines[offer["companion_product_id"]], key=lambda x: x[0]):
            take = min(left, line[1])
            if take <= 0:
                continue
            amount += (line[0] * percent / Decimal("100") * take)
            line[1] -= take
            left -= take
            units += take
        amount = amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        if amount > 0:
            total += amount
            applied.append({"product_id": pid, "companion_product_id": offer["companion_product_id"], "percent": offer["percent"], "units": units, "amount": str(amount)})
    return total, applied
