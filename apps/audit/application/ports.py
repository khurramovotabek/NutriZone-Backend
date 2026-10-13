"""
apps/audit/application/ports.py

Domain Architecture Specification -- audit is a pure projection (see
infrastructure/models.py's own docstring), so this Port is narrower
than a typical aggregate-backed repository: no `get_by_id`/`save`
pair, just the two real operations this module performs (record one
projected entry, query the projection for listing).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol


class ActivityTimelineRepository(Protocol):
    def record(
        self,
        entry_id: uuid.UUID,
        action_type: str,
        entity_type: str,
        entity_id: str,
        context_schema: str,
        occurred_at: datetime,
        actor_id: uuid.UUID | None = None,
        before_snapshot: dict | None = None,
        after_snapshot: dict | None = None,
    ): ...

    def queryset_for_listing(self, entity_type: str | None = None, entity_id: str | None = None, actor_id: uuid.UUID | None = None): ...
