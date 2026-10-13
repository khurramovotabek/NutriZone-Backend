"""
Products metrics integration -- named metric constants + thin
recording helpers over `core.metrics.default_collector` (Foundation
Hardening phase). `application/services/_shared.py::ProductServiceContext.
metric()` already calls `default_collector` directly for the common
counter case; this module exists for the two metrics that don't fit a
simple "+1 counter" shape (`publish_duration_seconds`, a histogram/
timer, and `average_media_per_product`, a computed gauge sourced from
`infrastructure/selectors.py::StatisticsSelector`).
"""
from __future__ import annotations

from apps.products.infrastructure.selectors import StatisticsSelector
from core.metrics import default_collector

METRIC_PRODUCTS_CREATED = "products_created_total"
METRIC_PRODUCTS_UPDATED = "products_updated_total"
METRIC_PRODUCTS_PUBLISHED = "products_published_total"
METRIC_PRODUCTS_ARCHIVED = "products_archived_total"
METRIC_VARIANTS_CREATED = "variants_created_total"
METRIC_MEDIA_UPLOADED = "media_uploaded_total"
METRIC_CATALOG_QUERIES = "catalog_queries_total"
METRIC_CATALOG_SEARCH = "catalog_search_total"
METRIC_PUBLISH_DURATION = "publish_duration_seconds"
METRIC_AVERAGE_MEDIA_PER_PRODUCT = "average_media_per_product"


def record_catalog_query() -> None:
    default_collector.counter(METRIC_CATALOG_QUERIES)


def record_average_media_per_product_gauge() -> None:
    """
    Called periodically (infrastructure/tasks.py's scheduled metrics
    refresh), not per-request -- an average across the whole catalog is
    a gauge computed from current state, not an event to count on every
    request.
    """
    average = StatisticsSelector().average_media_per_product()
    default_collector.gauge(METRIC_AVERAGE_MEDIA_PER_PRODUCT, average)


def publish_duration_timer():
    """Context manager -- `with publish_duration_timer(): ...` records a `publish_duration_seconds` histogram observation on exit. `application/services/lifecycle.py::PublishProduct` already uses `ProductServiceContext.timer()` for this; exposed here too as the named, discoverable entry point this module's brief asks for."""
    return default_collector.timer(METRIC_PUBLISH_DURATION.removesuffix("_seconds"))
