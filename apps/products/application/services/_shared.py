"""
Shared cross-cutting helpers for Products Application Services.

Every service in this package follows the same nine-step flow this
module's brief mandates (validate -> load aggregate -> execute domain
logic -> persist -> stage Outbox event -> write audit -> invalidate
cache -> record metrics -> return DTO). Steps 5-8 are cross-cutting
and identical in shape across ~30 services, so they're factored into
`ProductServiceContext` here rather than re-implemented per service --
this is a composition choice, not a skipped step: every service still
performs all nine steps, they just share one small, well-tested helper
for the four cross-cutting ones instead of duplicating the same four
lines thirty times.

`stage_events` is injected as a callable (never a concrete Outbox
model imported here) -- exactly matching
`apps/identity/application/services/*`'s pattern, since
`application/` may depend only on `core/` (generic, framework-adjacent
infrastructure) and Protocols, never on
`apps.products.infrastructure.models` directly (Django Implementation
Blueprint §4). The concrete `stage_events` callable that actually
knows about `orm.ProductsOutboxEvent` is constructed in
`infrastructure/composition.py`, exactly as
`apps.identity.infrastructure.composition::stage_identity_events` does.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable

from core.audit import AuditEventBuilder
from core.caching import CacheDomain, CacheKeyBuilder
from core.metrics import default_collector

StageEventsFn = Callable[[list[tuple[str, dict]]], None]


@dataclass(slots=True)
class ProductServiceContext:
    """Constructed once per request/task by infrastructure/composition.py, passed into every Application Service that needs the cross-cutting steps."""

    stage_events: StageEventsFn
    actor_id: uuid.UUID | None = None

    def audit(self) -> AuditEventBuilder:
        """Step 6."""
        return AuditEventBuilder(context_schema="products", actor_id=str(self.actor_id) if self.actor_id else None)

    def invalidate_product_cache(self) -> None:
        """
        Step 7: bumps the PRODUCT cache domain's version (O(1)
        bulk-invalidation, per core.caching.CacheKeyBuilder --
        Foundation Hardening phase). A per-product bump is deliberately
        NOT more granular than a full-domain version bump: individual
        per-product cache-key deletion would require tracking every
        derived cache entry (catalog listings, search results,
        filter-metadata) that embeds this product, which is exactly
        the invalidation-tracking complexity CacheKeyBuilder's
        versioning scheme exists to avoid.
        """
        CacheKeyBuilder(domain=CacheDomain.PRODUCT).bump_version()

    def metric(self, name: str, value: float = 1.0, **labels: str) -> None:
        """Step 8."""
        default_collector.counter(name, value, **labels)

    def timer(self, name: str, **labels: str):
        return default_collector.timer(name, **labels)
