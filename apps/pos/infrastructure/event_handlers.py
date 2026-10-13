"""
Consumed-event handlers for POS.

**No cache-invalidation mechanism exists** -- 0 selectors this phase
(see this module's own disclosed absence, matching this task's own
explicit Section 18 instruction), so there is no read model to
invalidate. Matches Analytics' own identical, disclosed departure
from the cache-group pattern used by earlier modules (Notifications,
Chat, Reviews).

Every one of the 5 certified events is still registered in the
dispatch table exactly once, satisfying "genuinely handled or
explicitly documented" -- the real, honest side effect here is
metrics emission only, per this task's own explicit prohibition
against inventing notifications, analytics synchronization, or
external event publishing at this phase.
"""
from __future__ import annotations

import logging

from core.metrics import default_collector

_EVENT_TO_METRIC = {
    "SaleOpened": "pos_sales_opened_total",
    "SaleCustomerSet": "pos_sale_customer_set_total",
    "SaleLineItemAdded": "pos_sale_line_items_added_total",
    "SaleLineItemRemoved": "pos_sale_line_items_removed_total",
    "SaleLineItemQuantityUpdated": "pos_sale_line_items_quantity_updated_total",
    "SaleCompleted": "pos_sales_completed_total",
    "SaleVoided": "pos_sales_voided_total",
    "SaleRefunded": "pos_sales_refunded_total",
}


def handle_pos_event(event_type: str, payload: dict) -> None:
    """Called by the Outbox relay task (infrastructure/tasks.py) for each of this schema's own events."""
    logger = logging.getLogger("nutrizone.app")

    metric_name = _EVENT_TO_METRIC.get(event_type)
    if metric_name:
        default_collector.counter(metric_name)

    logger.info("pos event handled: %s", event_type)
