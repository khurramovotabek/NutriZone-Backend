"""
"Birga arzonroq" -- buy a product together with its companion and the companion line gets a discount.

* `offer_for(product_id)`  the one companion offered on a product page: a staff pick (ProductBundle, Dashboard →
  Katalog → Birga arzonroq) wins; otherwise -- when BundleSettings.auto_enabled -- an in-stock add-on from a
  department that completes this one (COMPLEMENTS: creatine / a shaker next to a protein, omega next to a
  multivitamin; or the dashboard's `companion_categories`), priced at most `max_companion_share` of the main
  product, and only when the discounted price still clears the known purchase cost by `min_margin_percent`.
  Among those: the most natural department first, then the store's lead brands (PREFERRED_BRANDS), then the plain
  form (powder monohydrate, not gummies / capsules / blends). The few that tie are a shortlist and the page shows
  one of them -- a different one per product and per day (seeded, not random per request, so the page, the cache
  and the cart agree). Any shortlisted companion earns the discount in the cart, so a day change never takes it
  back. Cached for an hour.
* `cart_discount(lines)`  what checkout takes off for every (product, companion) pair actually in the cart:
  percent × the companion line's unit price × the units that have a partner. Each unit is discounted once.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
import uuid
from decimal import ROUND_HALF_UP, Decimal

from django.core.cache import cache

from apps.products.infrastructure import models as orm

CACHE_TTL = 60 * 60
_KEY = "bundle:v5:{}"
SHORTLIST = 10


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


# What completes a purchase from each department (the owner's category tree, uz slugs of the second level), most
# natural first. A department without an entry gets no automatic pair -- no pair beats a nonsense one.
COMPLEMENTS: dict[str, tuple[str, ...]] = {
    "proteinlar": ("kreatin", "shakerlar", "protein-sneklar", "aminokislotalar"),
    "geynerlar": ("kreatin", "shakerlar", "protein-sneklar"),
    "kreatin": ("shakerlar", "aminokislotalar", "pre-workout", "suv-idishlari"),
    "aminokislotalar": ("shakerlar", "hydration", "suv-idishlari"),
    "pre-workout": ("kreatin", "pump", "shakerlar"),
    "pump": ("pre-workout", "kreatin", "shakerlar"),
    "performance": ("hydration", "shakerlar", "suv-idishlari"),
    "hydration": ("suv-idishlari", "aminokislotalar"),
    "tiklanish": ("protein-sneklar", "shakerlar", "minerallar"),
    "yog-yoquvchilar": ("hydration", "suv-idishlari", "multivitaminlar"),
    "multivitaminlar": ("omega", "minerallar"),
    "vitaminlar-vitaminlar": ("minerallar", "omega", "multivitaminlar"),
    "minerallar": ("vitaminlar-vitaminlar", "omega", "multivitaminlar"),
    "omega": ("multivitaminlar", "vitaminlar-vitaminlar", "bogimlar-salomatligi"),
    "bogimlar-salomatligi": ("omega", "minerallar"),
    "soglom-uyqu": ("minerallar",),
    "testosteron": ("minerallar", "multivitaminlar"),
    "osimlik-ekstraktlari": ("multivitaminlar", "omega"),
    "salomatlik-aminokislotalari": ("multivitaminlar", "minerallar"),
    "protein-sneklar": ("shakerlar",),
    "soglom-ovqat": ("protein-sneklar",),
}


def _departments() -> tuple[dict[str, str], dict[str, str]]:
    """({category_id: its department id}, {department id: uz slug}). A department is the second level of the tree
    (Sport ozuqalari → Proteinlar); a top-level category is its own department. About a hundred rows, two queries."""
    from apps.products.infrastructure.models import CategoryTranslation

    parent = {str(c): (str(p) if p else None) for c, p in orm.Category.objects.values_list("id", "parent_id")}
    dept: dict[str, str] = {}
    for cid in parent:
        chain, node, seen = [cid], cid, set()
        while parent.get(node) and node not in seen:
            seen.add(node)
            node = parent[node]
            chain.append(node)
        dept[cid] = chain[-2] if len(chain) >= 2 else chain[-1]  # chain ends at the root
    slugs = {str(c): sl for c, sl in CategoryTranslation.objects.filter(locale_code="uz").values_list("category_id", "slug")}
    return dept, {d: slugs.get(d, "") for d in set(dept.values())}


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
    main = orm.Product.objects.filter(id=product_id).values("category_id").first()
    if not main or not main["category_id"]:
        return None
    dept, slug_of = _departments()
    main_dept = dept.get(str(main["category_id"]))
    allowed = _allowed_categories(cfg)
    if allowed is not None:  # the dashboard's own companion departments win over the built-in map
        rank = lambda cid: 0 if cid in allowed and dept.get(cid) != main_dept else None  # noqa: E731
    else:
        wanted = COMPLEMENTS.get(slug_of.get(main_dept, ""), ())
        if not wanted:
            return None
        order = {sl: i for i, sl in enumerate(wanted)}
        rank = lambda cid: order.get(slug_of.get(dept.get(cid, ""), ""))  # noqa: E731
    main_variant, _stock = _sellable_default(product_id)
    main_price = _variant_price(main_variant) if main_variant else None
    if not main_price:
        return None
    ceiling = main_price * cfg.max_companion_share / Decimal("100")

    from apps.products.infrastructure import gift_offer

    gift = gift_offer.gift_product_id()  # the Sovg'a aksiyasi shaker has its own card on the page -- never offered twice
    candidates = []
    for row in _companion_pool():
        r = rank(row["category_id"]) if row["category_id"] and row["product_id"] not in (str(product_id), gift) else None
        if r is None or Decimal(row["price"]) > ceiling:
            continue
        dept_slug = slug_of.get(dept.get(row["category_id"], ""), "")
        candidates.append(((r, row["brand"] not in PREFERRED_BRANDS, not _plain(dept_slug, row["name"])), row))
    candidates.sort(key=lambda x: x[0])  # stable: inside a tier the pool order (best sellers, then cheaper) stays
    ok = _margins_ok([row for _t, row in candidates], cfg.auto_percent, cfg.min_margin_percent)
    candidates = [(t, row) for t, row in candidates if row["variant_id"] in ok]
    if not candidates:
        return None
    best = candidates[0][0]
    shortlist = [row for t, row in candidates if t == best][:SHORTLIST]
    seed = int(hashlib.sha1(f"{product_id}:{dt.date.today().isoformat()}".encode()).hexdigest(), 16)
    row = shortlist[seed % len(shortlist)]
    return {"companion_product_id": row["product_id"], "companion_variant_id": row["variant_id"], "percent": str(cfg.auto_percent), "source": "auto",
            "alternates": [x["product_id"] for x in shortlist if x is not row]}


# The store's lead sports brands (uz brand names, lower case): an automatic companion comes from these when one fits.
PREFERRED_BRANDS = frozenset({
    "applied nutrition", "gat sport", "myprotein", "optimum nutrition", "allmax nutrition", "yava labs", "dy nutrition",
    "dymatize", "olimp sport nutrition", "mutant", "aps nutrition", "hi-tech pharmaceuticals", "maxler",
})
# The everyday form a companion should have, per department: creatine = plain powder monohydrate, not a gummy,
# chew, capsule, "for women" or a multi-ingredient system.
_ODD_FORM = {
    "kreatin": re.compile(r"gumm|chew|candy|chayna|caps|kapsul|tablet|women|ayollar|jetmass|nitraflex|3-in-1|charged|xplode|decanate|"
                          r"\bhcl\b|tri-creatine|alkalyn|\btcm\b|crea-lean|plus|cell-tech|creakong|-xs\b", re.I),
}


def _plain(dept_slug: str, name: str) -> bool:
    odd = _ODD_FORM.get(dept_slug)
    return not (odd and odd.search(name or ""))


def _margins_ok(rows: list[dict], percent: Decimal, min_margin: Decimal) -> set[str]:
    """The variant ids among `rows` whose discounted price clears the known purchase cost (one cost_info call)."""
    from apps.stores.infrastructure.count_service import cost_info

    if not rows:
        return set()
    costs = cost_info([uuid.UUID(r["variant_id"]) for r in rows])
    out = set()
    for r in rows:
        cost, source = costs.get(uuid.UUID(r["variant_id"]), (Decimal("0"), None))
        discounted = Decimal(r["price"]) * (Decimal("100") - percent) / Decimal("100")
        if source not in ("receipt", "catalog") or not cost or discounted >= Decimal(cost) * (Decimal("100") + min_margin) / Decimal("100"):
            out.add(r["variant_id"])
    return out


def _allowed_categories(cfg) -> set[str] | None:
    """The dashboard's companion departments with everything under them; None = use the built-in COMPLEMENTS map."""
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


POOL_KEY = "bundle:v5:pool"


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
    from apps.products.infrastructure.models import BrandTranslation, ProductTranslation

    brand_of = dict(orm.Product.objects.filter(id__in=list(chosen)).values_list("id", "brand_id"))
    brand_name = {b: n.strip().lower() for b, n in BrandTranslation.objects.filter(locale_code="uz").values_list("brand_id", "name")}
    names = dict(ProductTranslation.objects.filter(product_id__in=list(chosen), locale_code="uz").values_list("product_id", "name"))
    pool = [{"product_id": str(pid), "variant_id": str(vid), "category_id": str(cid) if cid else None, "price": str(prices[vid]), "sold": sold.get(str(pid), 0),
             "brand": brand_name.get(brand_of.get(pid), ""), "name": names.get(pid, "")}
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
        if not offer:
            continue
        # the companion shown today first, then any other shortlisted one (the page may have shown it yesterday)
        partners = [c for c in [offer["companion_product_id"], *offer.get("alternates", ())] if c in companion_lines and c != pid]
        if not partners:
            continue
        percent = Decimal(offer["percent"])
        left = main_units
        amount = Decimal("0")
        units = 0
        for line in [ln for c in partners for ln in sorted(companion_lines[c], key=lambda x: x[0])]:
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
            applied.append({"product_id": pid, "companion_product_id": partners[0], "percent": offer["percent"], "units": units, "amount": str(amount)})
    return total, applied
