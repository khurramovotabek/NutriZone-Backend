"""
Shared cross-cutting helpers for Platform Application Services.

Matches every prior module's application/services/_shared.py pattern
exactly (Loyalty's `LoyaltyServiceContext`, Wallet's
`WalletServiceContext`, etc.).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable

from core.audit import AuditEventBuilder

StageEventsFn = Callable[[list[tuple[str, dict]]], None]


@dataclass(slots=True)
class PlatformServiceContext:
    """Constructed once per request/task by infrastructure/composition.py, passed into every Application Service that needs the cross-cutting steps."""

    stage_events: StageEventsFn
    actor_id: uuid.UUID | None = None

    def audit(self) -> AuditEventBuilder:
        return AuditEventBuilder(context_schema="platform", actor_id=str(self.actor_id) if self.actor_id else None)
