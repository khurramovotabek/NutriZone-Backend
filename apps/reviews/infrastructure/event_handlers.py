"""
Consumed-event handlers for Reviews, plus the cache invalidation
helper functions they use.

Dispatch-table pattern, matching every prior module's identical
architecture -- never a giant if/else chain.
"""
from __future__ import annotations

import logging

from core.caching import get_redis_client
from core.metrics import default_collector

CACHE_GROUPS = ("review_detail", "product_review_list", "customer_review_list")

_EVENT_TO_CACHE_GROUPS = {
    "ReviewCreated": (),
    "ReviewSubmitted": ("review_detail",),
    "ReviewApproved": ("review_detail",),
    "ReviewRejected": ("review_detail",),
    "ReviewPublished": ("review_detail", "product_review_list", "customer_review_list"),
    "ReviewHidden": ("review_detail", "product_review_list", "customer_review_list"),
    "ReviewEdited": ("review_detail", "product_review_list"),
    "ReviewWithdrawn": ("review_detail", "product_review_list", "customer_review_list"),
    "ReviewMediaAttached": ("review_detail",),
}

_EVENT_TO_METRIC = {
    "ReviewSubmitted": "reviews_submitted_total",
    "ReviewApproved": "reviews_approved_total",
    "ReviewRejected": "reviews_rejected_total",
    "ReviewPublished": "reviews_published_total",
    "ReviewWithdrawn": "reviews_withdrawn_total",
}


def invalidate_review_cache_group(group: str) -> None:
    if group not in CACHE_GROUPS:
        raise ValueError(f"Unknown reviews cache group '{group}'. Must be one of {CACHE_GROUPS}.")
    client = get_redis_client()
    client.incr(f"nutrizone:cache-version:reviews:{group}")


def handle_review_event(event_type: str, payload: dict) -> None:
    """Called by the Outbox relay task (infrastructure/tasks.py) for each of this schema's own events -- invalidates cache, records metrics."""
    logger = logging.getLogger("nutrizone.app")

    for group in _EVENT_TO_CACHE_GROUPS.get(event_type, ()):
        invalidate_review_cache_group(group)

    metric_name = _EVENT_TO_METRIC.get(event_type)
    if metric_name:
        default_collector.counter(metric_name)

    logger.info("review event handled: %s", event_type)
