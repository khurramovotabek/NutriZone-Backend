"""
"Birga arzonroq" -- buy a product together with its companion and the companion line gets a discount.

* `offer_for(product_id)`  the one companion offered on a product page: a staff pick (ProductBundle, Dashboard →
  Katalog → Birga arzonroq) wins; otherwise -- when BundleSettings.auto_enabled -- the first in-stock product from
  the page's own recommendations (bought together) that is in another category (a shaker or creatine next to a
  protein, never a second protein), and only when the discounted price still clears the
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
    # sit in different leaves of the same "Protein" branch)
    for card in [c for c in cards if main_root and c.get("category_id") and roots.get(str(c["category_id"])) not in (None, main_root)]:
        if card.get("stock_status") == "out_of_stock":
            continue
        variant_id, stock = _sellable_default(card["id"])
        if not variant_id or stock <= 0:
            continue
        price = _variant_price(variant_id)
        if not price or price <= 0 or not _margin_ok(variant_id, price, cfg.auto_percent, cfg.min_margin_percent):
            continue
        return {"companion_product_id": str(card["id"]), "companion_variant_id": str(variant_id), "percent": str(cfg.auto_percent), "source": "auto"}
    return None


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
