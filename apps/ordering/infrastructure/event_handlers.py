"""
Consumed-event handlers for Ordering, plus the cache invalidation
helper functions they use.

Dispatch-table pattern, matching every prior module's identical
architecture -- never a giant if/else chain. Handlers are idempotent:
cache invalidation and metric increments are safe to run more than
once for the same event (the Outbox relay's own `publish_attempts`
retry mechanism could in principle re-deliver), so no handler here
performs a non-idempotent side effect.
"""
from __future__ import annotations

from core.caching import get_redis_client
from core.metrics import default_collector

CACHE_GROUPS = ("order_detail", "order_list", "return_detail", "cancellation_detail")

_EVENT_TO_CACHE_GROUPS = {
    "OrderCreated": ("order_list",),
    "OrderConfirmed": ("order_detail", "order_list"),
    "OrderProcessingStarted": ("order_detail",),
    "OrderShipped": ("order_detail",),
    "OrderDelivered": ("order_detail",),
    "OrderCompleted": ("order_detail", "order_list"),
    "OrderCancelled": ("order_detail", "order_list"),
    "OrderFailedEvent": ("order_detail", "order_list"),
    "LineItemCancelled": ("order_detail",),
    "LineItemReturned": ("order_detail",),
    "PaymentReferenceAdded": ("order_detail",),
    "PaymentStatusUpdated": ("order_detail",),
    "FulfillmentReferenceAdded": ("order_detail",),
    "FulfillmentStatusUpdated": ("order_detail",),
    "InvoiceIssued": ("order_detail",),
    "ReturnRequested": ("return_detail",),
    "ReturnApproved": ("return_detail",),
    "ReturnRejected": ("return_detail",),
    "ReturnReceived": ("return_detail",),
    "ReturnRefunded": ("return_detail",),
    "CancellationRequested": ("cancellation_detail",),
    "CancellationApproved": ("cancellation_detail",),
    "CancellationRejected": ("cancellation_detail",),
    "CancellationCompleted": ("cancellation_detail",),
    "OrderLockedEvent": ("order_detail",),
    "OrderUnlocked": ("order_detail",),
    "OrderArchivedEvent": ("order_detail", "order_list"),
    "OrderRestored": ("order_detail", "order_list"),
}

_EVENT_TO_METRIC = {
    "OrderCreated": "orders_created_total",
    "OrderConfirmed": "orders_confirmed_total",
    "OrderCompleted": "orders_completed_total",
    "OrderCancelled": "orders_cancelled_total",
    "OrderFailedEvent": "orders_failed_total",
    "ReturnRequested": "returns_requested_total",
    "ReturnRefunded": "returns_refunded_total",
    "CancellationRequested": "cancellations_requested_total",
    "CancellationCompleted": "cancellations_completed_total",
    "InvoiceIssued": "invoices_issued_total",
}


def invalidate_ordering_cache_group(group: str) -> None:
    if group not in CACHE_GROUPS:
        raise ValueError(f"Unknown ordering cache group '{group}'. Must be one of {CACHE_GROUPS}.")
    client = get_redis_client()
    client.incr(f"nutrizone:cache-version:ordering:{group}")


def handle_ordering_event(event_type: str, payload: dict) -> None:
    """Called by the Outbox relay task (infrastructure/tasks.py) for each of this schema's own events -- invalidates cache, records metrics. Audit was already written synchronously by the emitting Application Service."""
    import logging

    logger = logging.getLogger("nutrizone.app")

    for group in _EVENT_TO_CACHE_GROUPS.get(event_type, ()):
        invalidate_ordering_cache_group(group)

    metric_name = _EVENT_TO_METRIC.get(event_type)
    if metric_name:
        default_collector.counter(metric_name)

    logger.info("ordering event handled: %s", event_type)
