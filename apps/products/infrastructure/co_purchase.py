"""
"Ko'pincha birga olinadi" -- products bought together, mined from real baskets: every online order (that wasn't
cancelled / failed) and every completed store sale of the last year is one basket of distinct products.

Two products are related by how often they share a basket, normalised by how popular each is on its own
(cosine: co / sqrt(n_a * n_b)) -- so a best seller that is in every basket doesn't drown out a real pairing
(whey -> shaker), while a pair seen together often enough still ranks high. The pair table is built in one pass
and cached for CACHE_SECONDS.
"""
from __future__ import annotations

import math
import uuid
from collections import Counter
from datetime import timedelta
from itertools import combinations

from django.core.cache import cache
from django.utils import timezone

CACHE_KEY = "products:co_purchase:v1"
CACHE_SECONDS = 3600
LOOKBACK_DAYS = 365
MAX_BASKET = 30  # a bulk/wholesale order is not a signal of what goes together
BASKET_ORDER_STATUSES = ("confirmed", "processing", "shipped", "delivered", "completed")


def _baskets() -> list[frozenset]:
    from apps.ordering.infrastructure.models import OrderLineItemModel
    from apps.pos.infrastructure.models import SaleLineItemModel
    from apps.products.infrastructure.models import ProductVariant

    since = timezone.now() - timedelta(days=LOOKBACK_DAYS)
    lines = list(OrderLineItemModel.objects.filter(order__status__in=BASKET_ORDER_STATUSES, order__created_at__gte=since).exclude(status="cancelled").values_list("order_id", "product_variant_id"))
    product_of = dict(ProductVariant.all_objects.filter(id__in={v for _, v in lines}).values_list("id", "product_id"))
    by_basket: dict = {}
    for order_id, variant_id in lines:
        if variant_id in product_of:
            by_basket.setdefault(("o", order_id), set()).add(product_of[variant_id])
    for sale_id, product_id in SaleLineItemModel.objects.filter(sale__status="completed", sale__completed_at__gte=since).values_list("sale_id", "product_id"):
        by_basket.setdefault(("s", sale_id), set()).add(product_id)
    return [frozenset(b) for b in by_basket.values() if 1 < len(b) <= MAX_BASKET]


def _table() -> dict:
    """{"n": {product: baskets}, "pairs": {product: {other: score}}} -- cached."""
    table = cache.get(CACHE_KEY)
    if table is not None:
        return table
    baskets = _baskets()
    single: Counter = Counter()
    pair: Counter = Counter()
    for basket in baskets:
        single.update(basket)
        pair.update(combinations(sorted(basket, key=str), 2))
    scores: dict = {}
    for (a, b), co in pair.items():
        s = co / math.sqrt(single[a] * single[b])
        scores.setdefault(str(a), {})[str(b)] = s
        scores.setdefault(str(b), {})[str(a)] = s
    table = {"pairs": scores}
    cache.set(CACHE_KEY, table, CACHE_SECONDS)
    return table


def related(product_id, limit: int = 8) -> list[uuid.UUID]:
    """Products most often bought together with this one, best first."""
    scores = _table()["pairs"].get(str(product_id), {})
    return [uuid.UUID(p) for p, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:limit]]


def for_basket(product_ids, limit: int = 8) -> list[uuid.UUID]:
    """Cross-sell for a cart: summed affinity to everything in it, excluding what's already there."""
    have = {str(p) for p in product_ids}
    pairs = _table()["pairs"]
    total: Counter = Counter()
    for pid in have:
        for other, s in pairs.get(pid, {}).items():
            if other not in have:
                total[other] += s
    return [uuid.UUID(p) for p, _ in total.most_common(limit)]
