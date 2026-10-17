"""
Catalog browse: smart search + filters + facets + sorting, in one place.

Backs `GET /products/search` for the storefront catalog, with or without
a query. Every filter the API accepts is actually applied here (before
this, the parser validated price/flavour/availability but the selector
silently ignored everything except brand and category):

    category_id          one category (and its direct sub-categories)
    brand_ids            any of several brands
    price {gte, lte}     some variant priced in the range
    rating_gte           minimum average rating (1..5)
    flavour_ids          any of several flavours
    sizes                any of several variant sizes ("250g", "2.27kg")

Size, flavour and price are judged on the product's variants together (a family is one variant per size x
flavour): "350 g + Chocolate + up to 300 000" matches only when ONE variant is all three. Their facet counts follow
the same rule, so picking a flavour narrows the sizes and the price range to what exists in that flavour.
    goals                any of several training goals (goals.py)
    in_stock             only products with units in any store

Facets follow the usual faceted-search rule: each dimension's counts are
computed with every *other* active filter applied but not its own, so
picking one brand still shows how many products the other brands have.

Candidate attributes are resolved in bulk for the whole candidate set
(a fixed number of queries), then filtered/counted in Python -- right
for a catalog of thousands of products, and it keeps every rule
explicit. Only the requested page is turned into full product cards.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from apps.products.domain.enums import ProductStatus
from apps.products.infrastructure import models as orm

SORTS = {"relevance", "-created_at", "created_at", "price", "-price", "-rating", "-popularity", "name", "-name", "-discount"}


@dataclass(frozen=True)
class Offer:
    """One purchasable variant as the filters see it."""
    size: str | None
    flavours: frozenset
    price: Decimal | None


class OfferTest:
    """A filter judged per variant (size / flavour / price) -- see _passes."""

    def __init__(self, test):
        self.test = test


@dataclass
class Candidate:
    id: uuid.UUID
    category_id: uuid.UUID | None
    brand_id: uuid.UUID | None
    created_at: object
    name: str = ""
    price: Decimal | None = None
    discount: int = 0  # whole-number % off the old price (0 = not marked down)
    rating: float | None = None
    rating_count: int = 0
    flavour_ids: set = field(default_factory=set)
    sizes: set = field(default_factory=set)
    goals: set = field(default_factory=set)
    stock: int = 0
    popularity: int = 0
    rank: int = 0  # position in the smart-search ranking (query only)
    offers: list = field(default_factory=list)
    price_from: Decimal | None = None  # lowest variant price -- the "from" price the card shows, used for sorting


def size_key(value, unit) -> str | None:
    """Canonical size id, e.g. (250, "g") -> "250g", (2.27, "kg") -> "2.27kg"."""
    if value in (None, "") or not unit:
        return None
    return f"{format(Decimal(str(value)).normalize(), 'f')}{unit}"


def _grams(key: str) -> float:
    """Sort key for sizes: mass units in grams, anything else after them."""
    units = {"mg": 0.001, "g": 1, "kg": 1000, "lb": 453.592, "oz": 28.3495}
    for unit in sorted(units, key=len, reverse=True):
        if key.endswith(unit):
            try:
                return float(key[: -len(unit)]) * units[unit]
            except ValueError:
                break
    return float("inf")


def _parse_decimal(raw) -> Decimal | None:
    if raw in (None, ""):
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None


def _load_candidates(product_ids: list | None, locale: str) -> dict:
    """All attributes needed to filter, count and sort -- bulk, for every candidate."""
    from apps.products.infrastructure.selectors import _bulk_default_variant_prices, _bulk_rating_summary
    from apps.products.infrastructure.smart_search import _units_sold_by_product

    qs = orm.Product.objects.filter(status=ProductStatus.PUBLISHED.value)
    if product_ids is not None:
        qs = qs.filter(id__in=product_ids)
    products = list(qs.prefetch_related("variants", "translations"))
    by_id = {p.id: _candidate(p, locale) for p in products}

    from apps.products.infrastructure.selectors import _discount_fields

    for product_id, price in _bulk_default_variant_prices(products).items():
        by_id[product_id].price = Decimal(price["amount"])
        by_id[product_id].discount = _discount_fields(price)["discount_percent"] or 0
    for product_id, summary in _bulk_rating_summary(list(by_id)).items():
        candidate = by_id.get(uuid.UUID(str(product_id)))
        if candidate is not None:
            candidate.rating, candidate.rating_count = summary.get("average"), summary.get("count") or 0
    for product_id, flavour_id in orm.ProductFlavour.objects.filter(product_id__in=by_id).values_list("product_id", "flavour_id"):
        by_id[product_id].flavour_ids.add(flavour_id)
    _attach_offers(by_id, products)
    for product_id, units in _units_sold_by_product().items():
        candidate = by_id.get(uuid.UUID(product_id))
        if candidate is not None:
            candidate.popularity = units
    _attach_stock(by_id)
    return by_id


def _attach_offers(by_id: dict, products: list) -> None:
    """Every active variant as (size, flavour, price); one price query for the whole catalog."""
    from apps.products.infrastructure.selectors import bulk_variant_prices

    active = [v for p in products for v in p.variants.all() if v.status == "active"]
    prices = bulk_variant_prices([v.id for v in active])
    for v in active:
        c = by_id[v.product_id]
        price = prices.get(v.id)
        # a variant without its own flavour carries the product's flavour tags (one-flavour-per-product data)
        flavours = frozenset({v.flavour_id}) if v.flavour_id else frozenset(c.flavour_ids)
        c.offers.append(Offer(size=size_key(v.weight_value, v.weight_unit), flavours=flavours, price=Decimal(price["amount"]) if price else None))
    for c in by_id.values():
        if not c.offers:  # no active variant: the product-level facts still count
            c.offers.append(Offer(size=None, flavours=frozenset(c.flavour_ids), price=c.price))
        priced = [o.price for o in c.offers if o.price is not None]
        c.price_from = min(priced) if priced else c.price


def _candidate(product, locale: str) -> Candidate:
    translations = list(product.translations.all())
    name = next((t.name for t in translations if t.locale_code == locale and t.name), None) or next((t.name for t in translations if t.name), "")
    sizes = {key for v in product.variants.all() if v.status == "active" and (key := size_key(v.weight_value, v.weight_unit))}
    return Candidate(id=product.id, category_id=product.category_id, brand_id=product.brand_id, created_at=product.created_at, name=name, sizes=sizes,
                     goals=set(product.goals or []))


def _attach_stock(by_id: dict) -> None:
    from apps.stores.infrastructure.availability import sellable

    product_by_variant = dict(orm.ProductVariant.objects.filter(product_id__in=by_id).values_list("id", "product_id"))
    for variant_id, units in sellable(list(product_by_variant)).items():
        by_id[product_by_variant[variant_id]].stock += units


def category_scope(category_id) -> set:
    """The category and every category below it (section → product type) -- a parent shows all its products."""
    if not category_id:
        return set()
    ids = {uuid.UUID(str(category_id))}
    frontier = set(ids)
    while frontier:  # the tree is 3 levels deep; one query per level
        frontier = set(orm.Category.objects.filter(parent_id__in=frontier, is_deleted=False).values_list("id", flat=True)) - ids
        ids |= frontier
    return ids


_category_scope = category_scope


def _predicates(filters: dict) -> dict:
    """{dimension: predicate(candidate) -> bool} for every active filter."""
    preds = {}
    scope = category_scope(filters.get("category_id"))
    if scope:
        preds["category"] = lambda c: c.category_id in scope
    brand_ids = {uuid.UUID(str(b)) for b in filters.get("brand_ids") or []}
    if brand_ids:
        preds["brand"] = lambda c: c.brand_id in brand_ids
    price = filters.get("price") or {}
    lo, hi = _parse_decimal(price.get("gte")), _parse_decimal(price.get("lte"))
    if lo is not None or hi is not None:
        preds["price"] = OfferTest(lambda o: o.price is not None and (lo is None or o.price >= lo) and (hi is None or o.price <= hi))
    rating = _parse_decimal(filters.get("rating_gte"))
    if rating is not None:
        preds["rating"] = lambda c: c.rating is not None and Decimal(str(c.rating)) >= rating
    flavour_ids = {uuid.UUID(str(f)) for f in filters.get("flavour_ids") or []}
    if flavour_ids:
        preds["flavour"] = OfferTest(lambda o: bool(o.flavours & flavour_ids))
    sizes = set(filters.get("sizes") or [])
    if sizes:
        preds["size"] = OfferTest(lambda o: o.size in sizes)
    goals = set(filters.get("goals") or [])
    if goals:
        preds["goal"] = lambda c: bool(c.goals & goals)
    if filters.get("in_stock"):
        preds["availability"] = lambda c: c.stock > 0
    if filters.get("on_sale"):
        preds["sale"] = lambda c: c.discount > 0
    return preds


def _offer_tests(preds: dict, skip: str | None = None) -> list:
    return [pred.test for dim, pred in preds.items() if dim != skip and isinstance(pred, OfferTest)]


def _matching_offers(candidate, preds: dict, skip: str | None = None) -> list:
    tests = _offer_tests(preds, skip)
    return [o for o in candidate.offers if all(t(o) for t in tests)]


def _passes(candidate, preds: dict, skip: str | None = None) -> bool:
    """Product-level filters on the product; size / flavour / price on one and the same variant."""
    for dim, pred in preds.items():
        if dim != skip and not isinstance(pred, OfferTest) and not pred(candidate):
            return False
    return not _offer_tests(preds, skip) or bool(_matching_offers(candidate, preds, skip))


def _sort(rows: list, sort: str) -> list:
    if sort == "relevance":
        return sorted(rows, key=lambda c: c.rank)
    if sort in ("price", "-price"):
        priced = sorted((c for c in rows if c.price_from is not None), key=lambda c: c.price_from, reverse=sort == "-price")
        return priced + [c for c in rows if c.price_from is None]  # unpriced always last
    if sort == "-rating":
        return sorted(rows, key=lambda c: (c.rating or 0, c.rating_count), reverse=True)
    if sort == "-discount":
        return sorted(rows, key=lambda c: (c.discount, c.created_at), reverse=True)
    if sort == "-popularity":
        return sorted(rows, key=lambda c: (c.popularity, c.stock > 0), reverse=True)
    if sort in ("name", "-name"):
        return sorted(rows, key=lambda c: c.name.lower(), reverse=sort == "-name")
    return sorted(rows, key=lambda c: c.created_at, reverse=sort != "created_at")


def _facets(candidates: list, preds: dict, locale: str) -> dict:
    from apps.products.infrastructure.goals import GOALS
    from apps.products.infrastructure.goals import label as goal_label
    from apps.products.infrastructure.selectors import _flavour_summary, _translated_name

    def pool(dim):
        return [c for c in candidates if _passes(c, preds, skip=dim)]

    brand_counts: dict = {}
    for c in pool("brand"):
        if c.brand_id:
            brand_counts[c.brand_id] = brand_counts.get(c.brand_id, 0) + 1
    category_counts: dict = {}
    for c in pool("category"):
        if c.category_id:
            category_counts[c.category_id] = category_counts.get(c.category_id, 0) + 1
    # variant dimensions: an option counts when a variant has it AND fits the other variant filters
    flavour_counts: dict = {}
    for c in pool("flavour"):
        for f in {f for o in _matching_offers(c, preds, skip="flavour") for f in o.flavours}:
            flavour_counts[f] = flavour_counts.get(f, 0) + 1
    size_counts: dict = {}
    for c in pool("size"):
        for s in {o.size for o in _matching_offers(c, preds, skip="size") if o.size}:
            size_counts[s] = size_counts.get(s, 0) + 1
    goal_counts: dict = {}
    for c in pool("goal"):
        for g in c.goals:
            goal_counts[g] = goal_counts.get(g, 0) + 1
    rating_pool = pool("rating")
    price_pool = [o.price for c in pool("price") for o in _matching_offers(c, preds, skip="price") if o.price is not None]

    brands = orm.Brand.objects.filter(id__in=brand_counts).prefetch_related("translations")
    categories = orm.Category.objects.filter(id__in=category_counts).prefetch_related("translations")
    flavours = orm.Flavour.objects.filter(id__in=flavour_counts, is_active=True).prefetch_related("translations").order_by("sort_order")
    return {
        "brand": sorted(({"id": str(b.id), "name": _translated_name(b), "count": brand_counts[b.id]} for b in brands), key=lambda x: (-x["count"], x["name"])),
        "category": sorted(({"id": str(c.id), "name": _category_name(c, locale), "count": category_counts[c.id]} for c in categories), key=lambda x: (-x["count"], x["name"])),
        "flavour": [{**_flavour_summary(f, locale), "count": flavour_counts[f.id]} for f in flavours],
        "size": [{"id": s, "count": n} for s, n in sorted(size_counts.items(), key=lambda kv: (_grams(kv[0]), kv[0]))],
        "goal": [{"id": code, "name": goal_label(code, locale), "count": goal_counts[code]} for code in GOALS if goal_counts.get(code)],
        "rating": [{"min": stars, "count": sum(1 for c in rating_pool if (c.rating or 0) >= stars)} for stars in (4, 3, 2, 1)],
        "price_range": {"min": str(min(price_pool)) if price_pool else None, "max": str(max(price_pool)) if price_pool else None},
        "in_stock_count": sum(1 for c in pool("availability") if c.stock > 0),
        "on_sale_count": sum(1 for c in pool("sale") if c.discount > 0),
    }


def _category_name(category, locale: str) -> str:
    translations = list(category.translations.all())
    t = next((x for x in translations if x.locale_code == locale), None) or next((x for x in translations if x.locale_code == "uz"), None) or (translations[0] if translations else None)
    return t.name if t else str(category.id)[:8]


def browse(query: str | None, filters: dict, sort: str, page: int, page_size: int, locale: str) -> dict:
    """{"ordered_ids": page ids in order, "total_count", "facets", "suggestion"} -- the caller renders the page's cards."""
    suggestion = None
    ranked_ids = None
    if query:
        from apps.products.infrastructure import smart_search

        outcome = smart_search.search(query)
        suggestion = outcome.suggestion
        ranked_ids = [uuid.UUID(pid) for pid in outcome.product_ids]
        ranked_ids += _description_matches(query, locale, exclude=set(ranked_ids))

    by_id = _load_candidates(ranked_ids, locale)
    if ranked_ids is not None:
        for position, pid in enumerate(ranked_ids):
            if pid in by_id:
                by_id[pid].rank = position
    candidates = list(by_id.values())

    preds = _predicates(filters)
    matching = [c for c in candidates if _passes(c, preds)]
    effective_sort = sort if sort in SORTS else "-created_at"
    if query and effective_sort == "-created_at":
        effective_sort = "relevance"  # a query's default order is relevance, not date
    if not query and effective_sort == "relevance":
        effective_sort = "-created_at"
    ordered = _sort(matching, effective_sort)
    start = (page - 1) * page_size
    return {
        "ordered_ids": [c.id for c in ordered[start : start + page_size]],
        "total_count": len(ordered),
        "facets": _facets(candidates, preds, locale),
        "suggestion": suggestion,
    }


def _description_matches(query: str, locale: str, exclude: set) -> list:
    """Secondary signal: Postgres FTS over the requester's own-locale name/description (the smart index covers names, not descriptions)."""
    from django.contrib.postgres.search import SearchQuery, SearchRank

    from apps.products.infrastructure.selectors import _fts_config_for_locale

    search_query = SearchQuery(query, config=_fts_config_for_locale(locale), search_type="websearch")
    ids = (
        orm.ProductTranslation.objects.filter(locale_code=locale, product__status=ProductStatus.PUBLISHED.value, search_vector=search_query)
        .annotate(rank=SearchRank("search_vector", search_query))
        .order_by("-rank")
        .values_list("product_id", flat=True)
    )
    out = []
    for pid in ids:
        if pid not in exclude:
            out.append(pid)
            exclude.add(pid)
    return out
