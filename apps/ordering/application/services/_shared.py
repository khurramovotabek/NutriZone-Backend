"""
Shared cross-cutting helpers for Ordering Application Services.

Matches every prior module's application/services/_shared.py pattern.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable, Protocol

from core.audit import AuditEventBuilder
from core.caching import cache_key, get_redis_client
from core.metrics import default_collector

StageEventsFn = Callable[[list[tuple[str, dict]]], None]
ACTOR_SEPARATOR = " \u2014 "  # "<reason> — <staff name>" in a status-history reason


class OrderStockPort(Protocol):
    """Location stock for online orders (implemented by stores.online_fulfilment.StoresStockBridge). lines = [(variant_id, qty)]."""

    def reserve(self, order_number: str, lines: list[tuple]) -> list[dict]: ...
    def release(self, order_number: str, lines: list[tuple] | None = None) -> int: ...
    def ship(self, order_number: str, lines: list[tuple], store_id=None): ...
    def restock(self, order_number: str, lines: list[tuple]) -> int: ...
    def has_shipped(self, order_number: str) -> bool: ...


@dataclass(slots=True)
class OrderingServiceContext:
    """Constructed once per request/task by infrastructure/composition.py, passed into every Application Service that needs the cross-cutting steps."""

    stage_events: StageEventsFn
    actor_id: uuid.UUID | None = None
    # None = no location-stock side effects (unit tests, scripts); production wiring passes the stores bridge.
    stock: OrderStockPort | None = None
    # Display name of a dashboard (staff) actor -- staff accounts have integer ids, which history.actor_id (a customer UUID) can't hold.
    actor_label: str = ""

    @property
    def by_customer(self) -> bool:
        """Customers act with their identity UUID; staff (dashboard, Telegram) don't -- channel alerts only care about the former."""
        return isinstance(self.actor_id, uuid.UUID) and not self.actor_label

    def stamp_actor(self, order) -> None:
        """Domain transitions don't know who triggered them; the history row they just appended gets the acting user."""
        if not order.status_history:
            return
        entry = order.status_history[-1]
        if isinstance(self.actor_id, uuid.UUID):
            entry.actor_id = entry.actor_id or self.actor_id
        elif self.actor_label and ACTOR_SEPARATOR not in (entry.reason or ""):
            entry.reason = f"{entry.reason or ''}{ACTOR_SEPARATOR}{self.actor_label}"

    def audit(self) -> AuditEventBuilder:
        return AuditEventBuilder(context_schema="ordering", actor_id=str(self.actor_id) if self.actor_id else None)

    def invalidate_ordering_cache(self) -> None:
        """
        `core.caching.CacheDomain` is a closed, validated list that
        does not include "ordering" (the same documented platform gap
        already found for `apps.inventory`/`apps.pricing`/`apps.cart`
        -- verified against the actual source, not assumed, each
        time this recurs). Uses the same self-contained, raw-Redis
        versioned-key mechanism every other affected module already
        established for its own cache groups.
        """
        client = get_redis_client()
        client.incr(cache_key("all", namespace="ordering:version"))

    def metric(self, name: str, value: float = 1.0, **labels: str) -> None:
        default_collector.counter(name, value, **labels)

    def timer(self, name: str, **labels: str):
        return default_collector.timer(name, **labels)
