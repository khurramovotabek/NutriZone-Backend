"""
Consumed-event handlers for Pricing, plus the cache invalidation
helper functions they use.

Dispatch-table pattern, matching `apps.geo`/`apps.store`/
`apps.inventory`'s identical architecture -- never a giant if/else
chain. Pricing consumes its OWN Outbox stream (async self-consumption
for cache invalidation / metrics), not another bounded context's
events -- that would require a Domain Architecture Specification
Communication Matrix amendment, not made here.
"""
from __future__ import annotations

from core.caching import get_redis_client
from core.metrics import default_collector

CACHE_GROUPS = ("price_list_detail", "price_list_entries", "pricing_rules", "campaigns", "coupons", "price_history")

_EVENT_TO_CACHE_GROUPS = {
    "PriceListCreated": ("price_list_detail",),
    "PriceListActivated": ("price_list_detail",),
    "PriceListArchivedEvent": ("price_list_detail",),
    "PriceSet": ("price_list_entries", "price_history"),
    "PricingRuleCreated": ("pricing_rules",),
    "PricingRuleActivated": ("pricing_rules",),
    "PricingRuleArchived": ("pricing_rules",),
    "CampaignCreated": ("campaigns",),
    "CampaignActivated": ("campaigns",),
    "CampaignEnded": ("campaigns",),
    "CampaignCancelled": ("campaigns",),
    "CouponCreated": ("coupons",),
    "CouponRedeemed": ("coupons",),
    "CouponRevoked": ("coupons",),
    "PriceLocked": (),
    "PriceSnapshotConsumed": (),
    "PriceSnapshotReleased": (),
    "CashbackCalculated": (),
}

_EVENT_TO_METRIC = {
    "PriceListCreated": "price_lists_created_total",
    "PriceSet": "prices_set_total",
    "PricingRuleCreated": "pricing_rules_created_total",
    "CampaignCreated": "campaigns_created_total",
    "CampaignActivated": "campaigns_activated_total",
    "CouponCreated": "coupons_created_total",
    "CouponRedeemed": "coupons_redeemed_total",
    "PriceLocked": "price_snapshots_locked_total",
}


def invalidate_pricing_cache_group(group: str) -> None:
    if group not in CACHE_GROUPS:
        raise ValueError(f"Unknown pricing cache group '{group}'. Must be one of {CACHE_GROUPS}.")
    client = get_redis_client()
    client.incr(f"nutrizone:cache-version:pricing:{group}")


def handle_pricing_event(event_type: str, payload: dict) -> None:
    """Called by the Outbox relay task (infrastructure/tasks.py) for each of this schema's own events -- invalidates cache, records metrics. Audit was already written synchronously by the emitting Application Service."""
    import logging

    logger = logging.getLogger("nutrizone.app")

    for group in _EVENT_TO_CACHE_GROUPS.get(event_type, ()):
        invalidate_pricing_cache_group(group)

    metric_name = _EVENT_TO_METRIC.get(event_type)
    if metric_name:
        default_collector.counter(metric_name)

    logger.info("pricing event handled: %s", event_type)
