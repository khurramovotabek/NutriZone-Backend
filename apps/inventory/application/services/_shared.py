"""
Shared cross-cutting helpers for Inventory Application Services.

Matches every prior module's application/services/_shared.py pattern
-- every service performs all nine steps (validate -> load aggregate
-> execute domain logic -> persist -> stage Outbox event -> write
audit -> invalidate cache -> record metrics -> return DTO); steps 5-8
are factored here since they're identical in shape across every
service.
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
class InventoryServiceContext:
    """Constructed once per request/task by infrastructure/composition.py, passed into every Application Service that needs the cross-cutting steps."""

    stage_events: StageEventsFn
    actor_id: uuid.UUID | None = None

    def audit(self) -> AuditEventBuilder:
        return AuditEventBuilder(context_schema="inventory", actor_id=str(self.actor_id) if self.actor_id else None)

    def invalidate_inventory_cache(self) -> None:
        """
        `core.caching.CacheDomain` (Foundation Hardening) is a closed,
        validated list of exactly five domains (product/search/store/
        wallet/analytics) -- verified by reading its actual source
        before writing this, not assumed. `CacheKeyBuilder(domain=
        "inventory")` would raise `ValueError` at construction time,
        since "inventory" isn't in that closed set. Rather than modify
        Foundation Hardening's already-locked `key_builder.py` (a
        platform-wide file, not this module's to amend unilaterally),
        this uses the same self-contained, raw-Redis versioned-key
        mechanism `apps.geo.infrastructure.event_handlers` and
        `apps.store.infrastructure.event_handlers` already established
        for their own cache groups -- a real, documented platform gap
        (no `CacheDomain.INVENTORY` member exists) worth closing in a
        future Foundation Hardening amendment, not something this
        module can fix by editing a locked file.
        """
        client = get_redis_client()
        client.incr(cache_key("all", namespace="inventory:version"))

    def metric(self, name: str, value: float = 1.0, **labels: str) -> None:
        default_collector.counter(name, value, **labels)

    def timer(self, name: str, **labels: str):
        return default_collector.timer(name, **labels)
