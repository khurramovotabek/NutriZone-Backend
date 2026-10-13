"""
Products Celery tasks -- background jobs only (Django Implementation
Blueprint §3/§8): search-index sync, cache cleanup, Outbox retry,
catalog metrics. No business logic beyond the housekeeping itself.
"""
from __future__ import annotations

from celery import shared_task
from django.utils import timezone

from apps.products.infrastructure import models as orm
from core.outbox import OutboxRelay


@shared_task(queue="bulk", name="products.sync_search_index")
def sync_search_index() -> str:
    """
    No-op for the Postgres FTS backend (infrastructure/search.py's
    `PostgresSearchGateway.index_product()` docstring explains why --
    the GIN index on `catalog_product_translations` is always current).
    Kept as a real, scheduled task entry point so the eventual
    dedicated-search-engine swap-in has a stable task name to start
    doing real work under, per Domain Architecture Specification
    §2.16's extraction-seam philosophy.
    """
    return "no-op: Postgres FTS index is always current"


@shared_task(queue="scheduled", name="products.cleanup_cache")
def cleanup_cache() -> str:
    """Explicit cache-domain version bump on a schedule, as a safety net beyond the mutation-triggered invalidation every Application Service already performs -- catches any drift (e.g. a manual DB edit bypassing the application layer)."""
    from apps.products.infrastructure.cache import invalidate_all_product_caches, invalidate_search_cache

    invalidate_all_product_caches()
    invalidate_search_cache()
    return "ok"


@shared_task(queue="transactional", name="products.relay_outbox_events")
def relay_outbox_events() -> dict:
    """Celery Beat-scheduled Outbox relay for the `catalog` schema -- identical mechanics to `apps.identity.infrastructure.tasks::relay_outbox_events`."""
    relay = OutboxRelay(orm.ProductsOutboxEvent, max_attempts=5, batch_size=100)
    return relay.relay_pending(publish_fn=lambda event: True)


@shared_task(queue="scheduled", name="products.refresh_catalog_metrics")
def refresh_catalog_metrics() -> None:
    """Periodic gauge refresh for metrics that describe current catalog state rather than a discrete event (mission's `average_media_per_product`)."""
    from apps.products.infrastructure.metrics import record_average_media_per_product_gauge

    record_average_media_per_product_gauge()
