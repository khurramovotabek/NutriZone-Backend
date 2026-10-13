"""
Shared cross-cutting helpers for Pricing Application Services.

Matches every prior module's application/services/_shared.py pattern.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable

from core.audit import AuditEventBuilder
from core.caching import cache_key, get_redis_client
from core.metrics import default_collector

StageEventsFn = Callable[[list[tuple[str, dict]]], None]


@dataclass(slots=True)
class PricingServiceContext:
    """Constructed once per request/task by infrastructure/composition.py, passed into every Application Service that needs the cross-cutting steps."""

    stage_events: StageEventsFn
    actor_id: uuid.UUID | None = None

    def audit(self) -> AuditEventBuilder:
        return AuditEventBuilder(context_schema="pricing", actor_id=str(self.actor_id) if self.actor_id else None)

    def invalidate_pricing_cache(self) -> None:
        """
        `core.caching.CacheDomain` is a closed, validated list that
        does not include "pricing" (the same real, documented platform
        gap already found for `apps.inventory` -- verified against the
        actual source before writing this, not assumed). Uses the same
        self-contained, raw-Redis versioned-key mechanism `apps.geo`/
        `apps.store`/`apps.inventory` already established for their own
        cache groups.
        """
        client = get_redis_client()
        client.incr(cache_key("all", namespace="pricing:version"))

    def metric(self, name: str, value: float = 1.0, **labels: str) -> None:
        default_collector.counter(name, value, **labels)

    def timer(self, name: str, **labels: str):
        return default_collector.timer(name, **labels)
