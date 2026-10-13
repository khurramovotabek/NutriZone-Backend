"""
Shared cross-cutting helpers for Geo & Location Application Services.

Matches `apps/products/application/services/_shared.py`'s exact
pattern and rationale -- every service performs all nine steps
(validate -> load aggregate -> execute domain logic -> persist ->
stage Outbox event -> write audit -> invalidate cache -> record
metrics -> return DTO); steps 5-8 are factored here since they're
identical in shape across ~28 services.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable

from core.audit import AuditEventBuilder
from core.caching import cache_key, get_redis_client
from core.metrics import default_collector

StageEventsFn = Callable[[list[tuple[str, dict]]], None]

_GEO_CACHE_NAMESPACE = "geo"


@dataclass(slots=True)
class GeoServiceContext:
    """Constructed once per request/task by infrastructure/composition.py, passed into every Application Service that needs the cross-cutting steps."""

    stage_events: StageEventsFn
    actor_id: uuid.UUID | None = None

    def audit(self) -> AuditEventBuilder:
        return AuditEventBuilder(context_schema="geo", actor_id=str(self.actor_id) if self.actor_id else None)

    def invalidate_geo_cache(self, scope: str = "all") -> None:
        """
        Bumps a per-scope cache "version" counter in Redis (the same
        O(1) versioned-key pattern `core.caching.CacheKeyBuilder` uses
        platform-wide) -- `scope` is one of "country"/"region"/
        "district"/"city"/"neighborhood"/"address"/"all", so e.g.
        creating a District doesn't have to invalidate the (much
        larger, more expensive to rebuild) Country list cache.
        """
        client = get_redis_client()
        client.incr(cache_key(scope, namespace=f"{_GEO_CACHE_NAMESPACE}:version"))
        if scope != "all":
            client.incr(cache_key("all", namespace=f"{_GEO_CACHE_NAMESPACE}:version"))

    def metric(self, name: str, value: float = 1.0, **labels: str) -> None:
        default_collector.counter(name, value, **labels)

    def timer(self, name: str, **labels: str):
        return default_collector.timer(name, **labels)
