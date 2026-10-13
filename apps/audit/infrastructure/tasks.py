"""
apps/audit/infrastructure/tasks.py

Celery Beat-scheduled task. Unlike every other module's own
`relay_outbox_events` task (which relays *this* module's own outbox
via `core.outbox.OutboxRelay`), this task does not relay `audit`'s own
outbox -- `activity_timeline` is a pure projection with nothing of its
own to publish. It instead runs the subscribers that read *other*
modules' already-published outbox streams (see subscribers.py's own
scope note for which sources are wired, and which are confirmed
inactive/deferred).

Each source is synced independently -- one source's failure (see
`_sync_source()`'s own per-event failure handling) must not prevent
the others from running in the same task invocation.
"""
from __future__ import annotations

from celery import shared_task

from apps.audit.infrastructure.subscribers import (
    sync_cart_activity,
    sync_geo_activity,
    sync_identity_activity,
    sync_inventory_activity,
    sync_ordering_activity,
    sync_platform_activity,
    sync_pos_activity,
    sync_pricing_activity,
    sync_products_activity,
)

_SOURCES = (
    ("platform", sync_platform_activity),
    ("ordering", sync_ordering_activity),
    ("pricing", sync_pricing_activity),
    ("inventory", sync_inventory_activity),
    ("identity", sync_identity_activity),
    ("cart", sync_cart_activity),
    ("geo", sync_geo_activity),
    ("pos", sync_pos_activity),
    ("products", sync_products_activity),
)


@shared_task(queue="transactional", name="audit.sync_activity_timeline")
def sync_activity_timeline() -> dict:
    results = {}
    for name, sync_fn in _SOURCES:
        try:
            results[name] = sync_fn()
        except Exception as exc:  # noqa: BLE001 - one source's own unexpected failure must not prevent the others from syncing in the same task run
            results[name] = {"error": str(exc)}
    return results
