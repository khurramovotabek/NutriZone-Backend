"""
Shared cross-cutting helpers for Chat Application Services.

Matches every prior module's application/services/_shared.py pattern
exactly (Notifications' `NotificationServiceContext`, Loyalty's
`LoyaltyServiceContext`, Wallet's `WalletServiceContext`, Ordering's
`OrderingServiceContext`).

Phase 03B's own first real Application Service context for Chat --
confirmed by direct inspection that `apps/chat/application/services/`
contained only an empty `__init__.py` before this phase, and that
`views.py`/`consumers.py` both explicitly, honestly disclosed "zero
Application Services currently exist for the Chat module."
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable

from core.audit import AuditEventBuilder
from core.metrics import default_collector

StageEventsFn = Callable[[list[tuple[str, dict]]], None]


@dataclass(slots=True)
class ChatServiceContext:
    """Constructed once per request by infrastructure/composition.py, passed into every Application Service that needs the cross-cutting steps."""

    stage_events: StageEventsFn
    actor_id: uuid.UUID | None = None

    def audit(self) -> AuditEventBuilder:
        return AuditEventBuilder(context_schema="chat", actor_id=str(self.actor_id) if self.actor_id else None)

    def metric(self, name: str, value: float = 1.0, **labels: str) -> None:
        default_collector.counter(name, value, **labels)
