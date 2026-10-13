"""
Consumed-event handlers for Cart, plus the cache invalidation helper
functions they use.

Dispatch-table pattern, matching `apps.geo`/`apps.store`/
`apps.inventory`/`apps.pricing`'s identical architecture -- never a
giant if/else chain.
"""
from __future__ import annotations

from core.caching import get_redis_client
from core.metrics import default_collector

CACHE_GROUPS = ("cart_detail", "cart_items", "cart_list", "cart_snapshots")

_EVENT_TO_CACHE_GROUPS = {
    "CartCreated": ("cart_list",),
    "ItemAdded": ("cart_detail", "cart_items"),
    "ItemRemoved": ("cart_detail", "cart_items"),
    "ItemQuantityUpdated": ("cart_detail", "cart_items"),
    "CartCleared": ("cart_detail", "cart_items"),
    "CartMerged": ("cart_detail", "cart_items"),
    "CustomerAssigned": ("cart_detail", "cart_list"),
    "CouponReferenceApplied": ("cart_detail",),
    "CouponReferenceRemoved": ("cart_detail",),
    "PriceSnapshotAttached": ("cart_items",),
    "PriceSnapshotDetached": ("cart_items",),
    "ReservationAttached": ("cart_items",),
    "ReservationDetached": ("cart_items",),
    "CartSaved": ("cart_detail", "cart_list"),
    "CartArchivedEvent": ("cart_detail", "cart_list"),
    "CartExpiredEvent": ("cart_detail", "cart_list"),
    "CartRestored": ("cart_detail", "cart_list"),
    "CartLockedEvent": ("cart_detail",),
    "CartUnlocked": ("cart_detail",),
    "CartSnapshotCreated": ("cart_snapshots",),
    "CartSnapshotRestored": ("cart_detail", "cart_items", "cart_snapshots"),
    "CheckoutReadinessCalculated": (),
}

_EVENT_TO_METRIC = {
    "CartCreated": "carts_created_total",
    "ItemAdded": "cart_items_added_total",
    "CartMerged": "cart_merges_total",
    "CustomerAssigned": "carts_assigned_to_customer_total",
    "CartExpiredEvent": "carts_expired_total",
    "CartSnapshotCreated": "cart_snapshots_created_total",
}


def invalidate_cart_cache_group(group: str) -> None:
    if group not in CACHE_GROUPS:
        raise ValueError(f"Unknown cart cache group '{group}'. Must be one of {CACHE_GROUPS}.")
    client = get_redis_client()
    client.incr(f"nutrizone:cache-version:cart:{group}")


def handle_cart_event(event_type: str, payload: dict) -> None:
    """Called by the Outbox relay task (infrastructure/tasks.py) for each of this schema's own events -- invalidates cache, records metrics. Audit was already written synchronously by the emitting Application Service."""
    import logging

    logger = logging.getLogger("nutrizone.app")

    for group in _EVENT_TO_CACHE_GROUPS.get(event_type, ()):
        invalidate_cart_cache_group(group)

    metric_name = _EVENT_TO_METRIC.get(event_type)
    if metric_name:
        default_collector.counter(metric_name)

    logger.info("cart event handled: %s", event_type)
