"""
apps/audit/application/services/timeline.py

`RecordActivity` is the write side the subscriber (infrastructure/
subscribers.py) calls for each consumed business event.
`ListActivityTimeline` is the read side `GET /internal/audit/activity`
calls. Both are deliberately thin -- this module is a pure projection
(see infrastructure/models.py's own docstring); there is no business
invariant to enforce here beyond what the repository's own
idempotent-by-id `record()` already guarantees.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from apps.audit.application.ports import ActivityTimelineRepository


class RecordActivity:
    def __init__(self, repo: ActivityTimelineRepository) -> None:
        self._repo = repo

    def execute(
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
        return self._repo.record(
            entry_id=entry_id, action_type=action_type, entity_type=entity_type, entity_id=entity_id,
            context_schema=context_schema, occurred_at=occurred_at, actor_id=actor_id,
            before_snapshot=before_snapshot, after_snapshot=after_snapshot,
        )


class ListActivityTimeline:
    """Backs `GET /internal/audit/activity` -- returns a QuerySet for the view to hand to `StandardCursorPagination`, never a materialized list (see repository's own `queryset_for_listing` docstring)."""

    def __init__(self, repo: ActivityTimelineRepository) -> None:
        self._repo = repo

    def execute(self, entity_type: str | None = None, entity_id: str | None = None, actor_id: uuid.UUID | None = None):
        return self._repo.queryset_for_listing(entity_type=entity_type, entity_id=entity_id, actor_id=actor_id)
