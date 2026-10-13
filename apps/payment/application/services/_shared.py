from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable

from core.audit import AuditEventBuilder

StageEventsFn = Callable[[list[tuple[str, dict]]], None]


@dataclass(frozen=True, slots=True)
class PaymentServiceContext:
    stage_events: StageEventsFn
    actor_id: uuid.UUID | None = None

    def audit(self) -> AuditEventBuilder:
        return AuditEventBuilder(context_schema="payment", actor_id=str(self.actor_id) if self.actor_id else None)
