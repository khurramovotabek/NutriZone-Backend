"""
"How was it?" -- a few days after a customer received their goods (an online order delivered, or a store sale on
their account), one message per purchase asking for a review of what they haven't reviewed yet. Reviews were
missing almost everywhere on the storefront; they are what other shoppers and search results trust.

Window: received ask_after_days..ask_until_days ago (time to actually try the product, not so late it is forgotten) --
ReviewRequestSettings, editable in Dashboard → Sharhlar (default 5..14); switching it off stops the daily task.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.utils import timezone


@dataclass
class ReviewAsk:
    customer_id: object
    ref: str  # "order:<id>" / "sale:<id>" -- one message per purchase
    product_ids: list = field(default_factory=list)


def due(now: datetime | None = None) -> list[ReviewAsk]:
    from apps.ordering.infrastructure.replenishment import purchases
    from apps.products.infrastructure.models import Product
    from apps.reviews.infrastructure.models import ReviewModel, ReviewRequestSettings

    cfg = ReviewRequestSettings.load()
    if not cfg.enabled:
        return []
    after, until = cfg.ask_after_days, max(cfg.ask_until_days, cfg.ask_after_days + 1)
    now = now or timezone.now()
    window = [p for p in purchases(since=now - timedelta(days=until + 30))
              if now - timedelta(days=until) <= p.at <= now - timedelta(days=after)]
    if not window:
        return []
    reviewed = set(ReviewModel.objects.filter(customer_id__in={p.customer_id for p in window}).values_list("customer_id", "product_id"))
    published = set(Product.objects.filter(id__in={p.product_id for p in window}, status="published").values_list("id", flat=True))
    asks: dict[str, ReviewAsk] = {}
    for p in sorted(window, key=lambda p: p.at):
        if p.product_id not in published or (p.customer_id, p.product_id) in reviewed:
            continue
        ask = asks.setdefault(p.ref, ReviewAsk(p.customer_id, p.ref))
        if p.product_id not in ask.product_ids:
            ask.product_ids.append(p.product_id)
    return list(asks.values())
