"""
"Siz uchun" -- personal recommendations for a signed-in customer, from everything they bought: store-till receipts
with their account attached and delivered / completed online orders.

Candidates, best first (each card carries a short `reason`):
  1. bought together   co_purchase.for_basket over the customer's recent products ("X bilan birga olinadi")
  2. same goal         in-stock products serving the training goal they buy for most ("Maqsadingiz: Mushak o'stirish")
  3. same category     best sellers of their favourite category
  4. popular           store best sellers (no history yet)
Never: something they bought in the last 21 days (the replenishment reminder covers re-buying), out-of-stock or
unpublished products. Cached per customer for 15 minutes.
"""
from __future__ import annotations

import uuid
from collections import Counter
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from apps.products.infrastructure import goals as goal_book

RECENT_DAYS = 21
HISTORY_DAYS = 365
CACHE_SECONDS = 900
REASONS = {
    "together": {"uz": "{name} bilan ko'p olinadi", "ru": "Часто берут вместе с {name}", "en": "Often bought with {name}"},
    "goal": {"uz": "Maqsadingiz: {goal}", "ru": "Ваша цель: {goal}", "en": "Your goal: {goal}"},
    "category": {"uz": "Sizga yoqqan toifadan", "ru": "Из вашей любимой категории", "en": "From a category you like"},
    "popular": {"uz": "Ko'p sotiladi", "ru": "Хит продаж", "en": "Best seller"},
}


def _history(customer_id) -> list[tuple]:
    """[(product_id, when)] for every unit-line the customer bought (newest first)."""
    from apps.ordering.infrastructure.models import OrderLineItemModel
    from apps.pos.infrastructure.models import SaleLineItemModel
    from apps.products.infrastructure.models import ProductVariant

    since = timezone.now() - timedelta(days=HISTORY_DAYS)
    rows = list(SaleLineItemModel.objects.filter(sale__customer_id=customer_id, sale__status__in=("completed", "refunded"), sale__completed_at__gte=since)
                .values_list("product_id", "product_variant_id", "sale__completed_at"))
    online = list(OrderLineItemModel.objects.filter(order__customer_id=customer_id, order__status__in=("delivered", "completed"), status="active", order__created_at__gte=since)
                  .values_list("product_variant_id", "order__placed_at", "order__created_at"))
    variant_product = dict(ProductVariant.objects.filter(id__in=[r[1] for r in rows if r[1]] + [o[0] for o in online]).values_list("id", "product_id"))
    out = [(variant_product.get(vid) or pid, at) for pid, vid, at in rows if at]
    out += [(variant_product[vid], placed or created) for vid, placed, created in online if vid in variant_product]
    return sorted(((p, at) for p, at in out if p), key=lambda x: x[1], reverse=True)


def _sellable_products(product_ids) -> set:
    """Products that can be bought: some variant has stock -- or the product's stock isn't tracked at all (no stock
    rows, the catalogue shows it without a stock badge). Tracked products that ran out are left out."""
    from apps.products.infrastructure.models import ProductVariant
    from apps.stores.infrastructure import availability
    from apps.stores.infrastructure.models import StoreProductStock

    vmap = {}
    for vid, pid in ProductVariant.objects.filter(product_id__in=list(product_ids), status="active").values_list("id", "product_id"):
        vmap.setdefault(pid, []).append(vid)
    all_variants = [v for vs in vmap.values() for v in vs]
    tracked = set(StoreProductStock.objects.filter(product_variant_id__in=all_variants).values_list("product_variant_id", flat=True))
    stock = availability.sellable(all_variants)
    return {pid for pid, vs in vmap.items() if any(stock.get(v, 0) > 0 for v in vs) or not any(v in tracked for v in vs)}


def _popular(limit: int) -> list:
    from apps.products.infrastructure import smart_search

    sold = smart_search._units_sold_by_product()
    return [uuid.UUID(pid) for pid, _n in sorted(sold.items(), key=lambda x: -x[1])[: limit * 3]]


class _Picker:
    """Collects ranked candidates once each, skipping recent buys and unpublished products."""

    def __init__(self, published: dict, skip: set):
        self.published, self.seen, self.picks = published, set(skip), []

    def take(self, pid, code: str, args: dict | None = None) -> None:
        if pid in self.published and pid not in self.seen:
            self.seen.add(pid)
            self.picks.append((pid, code, args or {}))


def _history_signals(picker: _Picker, bought: list, goals_of: dict, limit: int) -> None:
    from apps.products.infrastructure import co_purchase

    distinct = list(dict.fromkeys(bought))[:10]
    if not distinct:
        return
    for pid in co_purchase.for_basket(distinct, limit * 2):
        picker.take(pid, "together", {"product_id": distinct[0]})
    popular = _popular(limit * 2)
    goal_counts = Counter(g for p in bought for g in goals_of.get(p, []))
    if goal_counts:
        top_goal = goal_counts.most_common(1)[0][0]
        for pid in popular + [p for p, gs in goals_of.items() if top_goal in gs]:
            if top_goal in goals_of.get(pid, []):
                picker.take(pid, "goal", {"goal": top_goal})
    cats = Counter(picker.published.get(p) for p in bought if picker.published.get(p))
    if cats:
        top_cat = cats.most_common(1)[0][0]
        for pid in popular + sorted(p for p, c in picker.published.items() if c == top_cat):
            if picker.published.get(pid) == top_cat:
                picker.take(pid, "category")


def plan(customer_id, limit: int = 8) -> list[tuple]:
    """[(product_id, reason_code, reason_args)] -- the ranking, before cards are built."""
    from apps.products.infrastructure.models import Product

    history = _history(customer_id)
    recent_cut = timezone.now() - timedelta(days=RECENT_DAYS)
    published = dict(Product.objects.filter(status="published").values_list("id", "category_id"))
    goals_of = {pid: goal_book.clean(g) for pid, g in Product.objects.filter(status="published").values_list("id", "goals")}
    picker = _Picker(published, {p for p, at in history if at >= recent_cut})
    _history_signals(picker, [p for p, _at in history], goals_of, limit)
    for pid in _popular(limit * 2):
        picker.take(pid, "popular")
    if not history:  # a new shopper in a shop without sales yet: the newest published products
        for pid in sorted(published)[: limit * 2]:
            picker.take(pid, "popular")
    in_stock = _sellable_products([p for p, _c, _a in picker.picks])
    return [x for x in picker.picks if x[0] in in_stock][:limit]


def _reason(code: str, args: dict, locale: str, names: dict) -> str:
    text = REASONS[code].get(locale) or REASONS[code]["uz"]
    if code == "together":
        return text.format(name=names.get(args.get("product_id"), "…"))
    if code == "goal":
        return text.format(goal=goal_book.label(args.get("goal", ""), locale))
    return text


def for_customer(customer_id, locale: str = "uz", limit: int = 8) -> list[dict]:
    from apps.products.infrastructure.models import Product
    from apps.products.infrastructure.selectors import _cards_with_price_and_rating

    key = f"personal:v1:{customer_id}:{locale}:{limit}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    ranked = plan(customer_id, limit)
    ids = [p for p, _c, _a in ranked]
    anchors = {a.get("product_id") for _p, c, a in ranked if c == "together"}
    rows = {p.id: p for p in Product.objects.filter(id__in=ids + [a for a in anchors if a]).prefetch_related("translations", "media", "variants")}
    cards = {c["id"]: c for c in _cards_with_price_and_rating([rows[i] for i in ids if i in rows], locale)}
    names = {pid: next((t.name for t in rows[pid].translations.all() if t.locale_code == locale), None) or next((t.name for t in rows[pid].translations.all()), "") for pid in anchors if pid in rows}
    out = []
    for pid, code, args in ranked:
        card = cards.get(str(pid))
        if card:
            out.append({**card, "reason": _reason(code, args, locale, names), "reason_code": code})
    cache.set(key, out, CACHE_SECONDS)
    return out
