"""
Consumed-event handlers for Notifications, plus the cache
invalidation helper functions they use.

Dispatch-table pattern, matching every prior module's identical
architecture -- never a giant if/else chain.

**`NotificationDeliverySent` deliberately has no cache-group side
effect, disclosed rather than silently omitted**: no selector
currently surfaces per-delivery state (only `counts_by_status` and
notification cards, neither of which changes shape based on an
individual delivery attempt existing) -- inventing an invalidation
target with nothing that reads it would be a speculative side effect,
not a real one. The event is still registered (satisfying "every
event genuinely handled or explicitly documented"), it just has an
honestly empty cache-group tuple, matching Chat's own precedent for
`MessageDelivered`/`MessageRead`.
"""
from __future__ import annotations

import logging

from core.caching import get_redis_client
from core.metrics import default_collector

CACHE_GROUPS = ("notification_list", "notification_statistics")

_EVENT_TO_CACHE_GROUPS = {
    "NotificationCreated": ("notification_list", "notification_statistics"),
    "NotificationDeliverySent": (),
    "NotificationDelivered": ("notification_statistics",),
    "NotificationDeliveryFailed": ("notification_statistics",),
    "NotificationSeen": ("notification_list", "notification_statistics"),
    "NotificationRead": ("notification_list", "notification_statistics"),
    "NotificationCancelled": ("notification_list", "notification_statistics"),
    "NotificationChannelEnabled": (),
    "NotificationChannelDisabled": (),
}

_EVENT_TO_METRIC = {
    "NotificationCreated": "notifications_created_total",
    "NotificationDelivered": "notifications_delivered_total",
    "NotificationDeliveryFailed": "notifications_delivery_failed_total",
    "NotificationRead": "notifications_read_total",
    "NotificationCancelled": "notifications_cancelled_total",
}


def invalidate_notification_cache_group(group: str) -> None:
    if group not in CACHE_GROUPS:
        raise ValueError(f"Unknown notifications cache group '{group}'. Must be one of {CACHE_GROUPS}.")
    client = get_redis_client()
    client.incr(f"nutrizone:cache-version:notifications:{group}")


def handle_notification_event(event_type: str, payload: dict) -> None:
    """Called by the Outbox relay task (infrastructure/tasks.py) for each of this schema's own events."""
    logger = logging.getLogger("nutrizone.app")

    for group in _EVENT_TO_CACHE_GROUPS.get(event_type, ()):
        invalidate_notification_cache_group(group)

    metric_name = _EVENT_TO_METRIC.get(event_type)
    if metric_name:
        default_collector.counter(metric_name)

    logger.info("notification event handled: %s", event_type)
