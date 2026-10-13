"""
Shared cross-cutting helpers for Notifications Application Services.

Matches every prior module's application/services/_shared.py pattern
exactly (Loyalty's `LoyaltyServiceContext`, Wallet's
`WalletServiceContext`, Ordering's `OrderingServiceContext`, etc.).

This is Phase 02G's own first Application Service context for
Notifications -- confirmed by direct inspection that
`apps/notifications/application/services/` contained only an empty
`__init__.py` before this phase (`apps/notifications/application/
ports.py`'s own docstring explicitly disclosed "zero Application
Services, zero service context").
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
class NotificationServiceContext:
    """Constructed once per request/task by infrastructure/composition.py, passed into every Application Service that needs the cross-cutting steps."""

    stage_events: StageEventsFn
    actor_id: uuid.UUID | None = None

    def audit(self) -> AuditEventBuilder:
        return AuditEventBuilder(context_schema="notifications", actor_id=str(self.actor_id) if self.actor_id else None)

    def invalidate_notification_cache(self) -> None:
        """Matches every prior module's own self-contained, raw-Redis versioned-key mechanism -- reuses `apps.notifications.infrastructure.event_handlers`'s own already-existing CACHE_GROUPS/invalidation helper rather than duplicating cache-invalidation logic here."""
        from apps.notifications.infrastructure.event_handlers import invalidate_notification_cache_group
        for group in ("notification_list", "notification_statistics"):
            invalidate_notification_cache_group(group)

    def metric(self, name: str, value: float = 1.0, **labels: str) -> None:
        default_collector.counter(name, value, **labels)

    def timer(self, name: str, **labels: str):
        return default_collector.timer(name, **labels)
