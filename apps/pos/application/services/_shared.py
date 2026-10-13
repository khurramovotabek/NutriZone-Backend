"""
Shared cross-cutting helpers for POS Application Services.

Matches Analytics' own `application/services/_shared.py` pattern
exactly -- the closest real, verified precedent for a single-
aggregate module's Application layer in this codebase (re-verified
directly this phase, not assumed from memory).

**The identical, disclosed departure from Loyalty's own precedent**:
`PosServiceContext` has NO `invalidate_*_cache()` method. Infrastructure
(Phase 2) explicitly certified zero selectors exist for POS -- there
is no cache-backed read model to invalidate.

**`actor_id` is carried for audit-trail purposes only** -- it is never
passed into any `Sale` method. The certified Domain contract
(`Sale.open(sale_id, branch_id, cashier_id, at, customer_id)`, etc.)
has no actor parameter, and this phase's own Section 10 explicitly
forbids inventing one on Domain; `cashier_id` (not `actor_id`) is
already the certified Domain field representing who is operating the
sale.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable

from core.audit import AuditEventBuilder
from core.metrics import default_collector

StageEventsFn = Callable[[list[tuple[str, dict]]], None]


@dataclass(slots=True)
class PosServiceContext:
    """Constructed once per request/task by infrastructure/composition.py, passed into every Application Service that needs the cross-cutting steps."""

    stage_events: StageEventsFn
    actor_id: uuid.UUID | None = None

    def audit(self) -> AuditEventBuilder:
        return AuditEventBuilder(context_schema="pos", actor_id=str(self.actor_id) if self.actor_id else None)

    def metric(self, name: str, value: float = 1.0, **labels: str) -> None:
        default_collector.counter(name, value, **labels)

    def timer(self, name: str, **labels: str):
        return default_collector.timer(name, **labels)
