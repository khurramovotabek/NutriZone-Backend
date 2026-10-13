"""
Consumed-event handlers for Inventory, plus the cache invalidation
helper functions they use.

Scope note (matching `apps.geo`/`apps.store`'s identical pattern):
Inventory consumes its OWN Outbox stream (async self-consumption for
cache invalidation / metrics), not another bounded context's events --
that would require a Domain Architecture Specification Communication
Matrix amendment (MIC §7).
"""
from __future__ import annotations

from core.caching import get_redis_client
from core.metrics import default_collector

# Cache groups this module's own reads are keyed under.
CACHE_GROUPS = ("inventory_detail", "inventory_list", "warehouse_summary", "stock_levels", "reservations", "ledger", "batches", "snapshots")

_EVENT_TO_CACHE_GROUPS = {
    "InventoryCreated": ("inventory_list",),
    "InventoryUpdated": ("inventory_detail", "inventory_list"),
    "InventoryArchivedEvent": ("inventory_detail", "inventory_list"),
    "InventoryRestored": ("inventory_detail", "inventory_list"),
    "StockReceived": ("stock_levels", "warehouse_summary"),
    "StockReserved": ("stock_levels", "reservations"),
    "ReservationReleased": ("stock_levels", "reservations"),
    "StockTransferred": ("stock_levels", "warehouse_summary"),
    "StockAdjusted": ("stock_levels",),
    "StockExpired": ("stock_levels",),
    "StockDamaged": ("stock_levels",),
    "BatchCreated": ("batches",),
    "SerialRegistered": ("batches",),
    "ReservationCreated": ("reservations", "stock_levels"),
    "ReservationCancelled": ("reservations", "stock_levels"),
    "ReservationExpiredEvent": ("reservations", "stock_levels"),
    "CycleCountStarted": (),
    "CycleCountCompleted": ("stock_levels",),
    "PhysicalInventoryStarted": (),
    "PhysicalInventoryCompleted": ("stock_levels",),
    "InventorySnapshotCreated": ("snapshots",),
}

_EVENT_TO_METRIC = {
    "InventoryCreated": "inventory_items_created_total",
    "StockReceived": "stock_received_total",
    "StockReserved": "stock_reserved_total",
    "StockTransferred": "stock_transferred_total",
    "StockAdjusted": "stock_adjustments_total",
    "StockExpired": "stock_expired_total",
    "StockDamaged": "stock_damaged_total",
    "BatchCreated": "batches_created_total",
    "SerialRegistered": "serials_registered_total",
    "ReservationCreated": "reservations_created_total",
    "CycleCountStarted": "cycle_counts_started_total",
    "CycleCountCompleted": "cycle_counts_completed_total",
    "PhysicalInventoryStarted": "physical_inventories_started_total",
    "PhysicalInventoryCompleted": "physical_inventories_completed_total",
    "InventorySnapshotCreated": "inventory_snapshots_created_total",
}


def invalidate_inventory_cache_group(group: str) -> None:
    if group not in CACHE_GROUPS:
        raise ValueError(f"Unknown inventory cache group '{group}'. Must be one of {CACHE_GROUPS}.")
    client = get_redis_client()
    client.incr(f"nutrizone:cache-version:inventory:{group}")


def handle_inventory_event(event_type: str, payload: dict) -> None:
    """
    Called by the Outbox relay task (infrastructure/tasks.py) for each
    of this schema's own events -- invalidates cache, records metrics.
    Audit was already written synchronously by the emitting
    Application Service; this handler does not duplicate that write.
    """
    import logging

    logger = logging.getLogger("nutrizone.app")

    for group in _EVENT_TO_CACHE_GROUPS.get(event_type, ()):
        invalidate_inventory_cache_group(group)

    metric_name = _EVENT_TO_METRIC.get(event_type)
    if metric_name:
        default_collector.counter(metric_name)

    logger.info("inventory event handled: %s", event_type)
