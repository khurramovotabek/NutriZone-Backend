"""
In-memory fake implementing application/ports.py::ActivityTimelineRepository.
"""
from __future__ import annotations

import uuid
from datetime import datetime


class FakeActivityTimelineRepository:
    def __init__(self) -> None:
        self.entries: dict[uuid.UUID, dict] = {}

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
    ):
        if entry_id in self.entries:
            return self.entries[entry_id]  # idempotent, matching the real repository's get_or_create semantics
        entry = {
            "id": entry_id, "action_type": action_type, "entity_type": entity_type, "entity_id": entity_id,
            "context_schema": context_schema, "occurred_at": occurred_at, "actor_id": actor_id,
            "before_snapshot": before_snapshot, "after_snapshot": after_snapshot,
        }
        self.entries[entry_id] = entry
        return entry

    def queryset_for_listing(self, entity_type: str | None = None, entity_id: str | None = None, actor_id: uuid.UUID | None = None):
        results = list(self.entries.values())
        if entity_type is not None:
            results = [e for e in results if e["entity_type"] == entity_type]
        if entity_id is not None:
            results = [e for e in results if e["entity_id"] == entity_id]
        if actor_id is not None:
            results = [e for e in results if e["actor_id"] == actor_id]
        return results
