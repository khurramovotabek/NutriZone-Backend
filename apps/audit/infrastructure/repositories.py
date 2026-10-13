"""
apps/audit/infrastructure/repositories.py

Database Blueprint §4.19. No ORM exception leaks past this layer,
matching every prior module's established convention.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from django.db import IntegrityError

from apps.audit.infrastructure import models as orm
from common.exceptions import ConflictError


class DjangoActivityTimelineRepository:
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
    ) -> orm.ActivityTimelineEntry:
        """
        Idempotent by `entry_id` -- the *source outbox event's own*
        `id` (e.g. `PlatformOutboxEvent.id`), not an `AuditEvent.id`
        (no module anywhere actually stages an `AuditEvent`-shaped
        payload -- confirmed by repository-wide search; see this
        capability's own certification report for that finding). The
        subscriber may re-process the same source event more than
        once (e.g. after a task retry), and this must never create a
        duplicate row for it. `AppendOnlyModel.save()` refuses updates
        to an existing row (see that class's own docstring), so a
        plain `get_or_create` keyed on the primary key is the correct,
        safe idempotency mechanism here -- not an upsert. Genuinely
        race-safe, not merely "usually fine": Django's `get_or_create`
        retries the lookup on an `IntegrityError` from the underlying
        unique constraint, and `id` is the primary key, so this holds
        under concurrent processing, not only sequential retries.
        """
        try:
            entry, _created = orm.ActivityTimelineEntry.objects.get_or_create(
                id=entry_id,
                defaults={
                    "action_type": action_type, "entity_type": entity_type, "entity_id": entity_id,
                    "context_schema": context_schema, "occurred_at": occurred_at, "created_by": actor_id,
                    "before_snapshot": before_snapshot, "after_snapshot": after_snapshot,
                },
            )
        except IntegrityError as exc:
            raise ConflictError("This activity timeline entry already exists.") from exc
        return entry

    def queryset_for_listing(self, entity_type: str | None = None, entity_id: str | None = None, actor_id: uuid.UUID | None = None):
        """
        Returns a QuerySet, not a materialized list -- `StandardCursorPagination`
        (common/pagination/pagination.py, the already-established, repository-
        wide cursor-pagination mechanism the REST API Blueprint's own §5
        pagination-strategy table names for this exact table) needs a QuerySet
        to apply its own LIMIT/cursor-window logic; materializing here would
        defeat that.
        """
        qs = orm.ActivityTimelineEntry.objects.all()
        if entity_type is not None:
            qs = qs.filter(entity_type=entity_type)
        if entity_id is not None:
            qs = qs.filter(entity_id=entity_id)
        if actor_id is not None:
            qs = qs.filter(created_by=actor_id)
        return qs
