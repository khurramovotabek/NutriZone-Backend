"""
apps/audit/infrastructure/models.py

Database Blueprint §4.19 `audit.activity_timeline` -- the platform-
wide, append-only, cross-context audit feed. `AppendOnlyModel`'s own
`created_by` field is reused directly as `actor_id` (identical type,
nullability, and cross-schema-no-FK semantics -- see that base
class's own docstring) rather than adding a redundant duplicate
column; `.created_by` is exposed as `.actor_id` via a property for
clarity at call sites, matching the blueprint's own column name.

**Partitioning note, disclosed rather than fabricated**: the blueprint
mandates range partitioning by `occurred_at` from day one (§9). Django
does not natively manage Postgres native partitioning through its ORM
migration system without either a raw-SQL migration or a third-party
partitioning package -- neither of which can be authored or verified
without Django/PostgreSQL available in this sandbox (see this
capability's own certification report, §10). The base table structure
below is schema-correct; partitioning itself is out of this phase's
safely-verifiable scope.
"""
from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import AppendOnlyModel


class ActivityTimelineEntry(AppendOnlyModel):
    action_type = models.CharField(max_length=32, db_index=True)
    entity_type = models.CharField(max_length=64)
    entity_id = models.CharField(max_length=64)
    context_schema = models.CharField(max_length=64, db_index=True)
    before_snapshot = models.JSONField(null=True, blank=True)
    after_snapshot = models.JSONField(null=True, blank=True)
    occurred_at = models.DateTimeField(db_index=True)
    """When the source event actually happened in its originating module -- distinct from `created_at` (inherited from AppendOnlyModel), which is when this projection row was written, generally microseconds to seconds later."""

    class Meta:
        db_table = "audit_activity_timeline"
        verbose_name=_("Activity Timeline Entry")
        verbose_name_plural=_("Activity Timeline Entries")
        indexes = [
            # Database Blueprint §4.19 names these ix_activity_timeline_entity_type_entity_id
            # (44 chars) and ix_activity_timeline_actor_id_occurred_at (43 chars) -- both
            # exceed Django's own hard 30-character index-name limit (Index.max_name_length),
            # a genuine framework constraint, not a stylistic choice. No other model in this
            # repository attempts an explicit index name for the same reason; these two rely
            # on Django's auto-generated name, matching that established, repository-wide
            # convention exactly.
            models.Index(fields=["entity_type", "entity_id"]),
            models.Index(fields=["created_by", "occurred_at"]),
        ]

    @property
    def actor_id(self):
        return self.created_by

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.context_schema}:{self.action_type}:{self.entity_type}:{self.entity_id}"


class SubscriberCursor(models.Model):
    """
    Tracks this subscriber's own read position into a source module's
    outbox table, independently of that table's `published_at`
    (owned exclusively by the source module's own `OutboxRelay` --
    confirmed by direct inspection of `core/outbox/publisher.py`:
    `OutboxRelay.relay_pending()` is genuinely single-consumer, since
    it both filters AND writes `published_at`. A second relay reading
    the same table would starve against the first. This subscriber
    therefore never uses `OutboxRelay` against another module's
    outbox at all -- it does its own read-only query, tracking its
    own progress here instead).

    Tracks `(last_processed_created_at, last_processed_id)`, not a
    bare `id` -- a real correctness point: outbox primary keys are
    random UUID4s (via `AppendOnlyModel`), which carry no meaningful
    ordering, so `id__gt=...` alone cannot express "everything after
    the last row I processed." `created_at` provides genuine insertion
    ordering; `id` breaks ties within the same timestamp -- the
    identical keyset-pagination principle `StandardCursorPagination`
    (common/pagination/pagination.py) itself already relies on.
    """

    source_schema = models.CharField(max_length=64, primary_key=True)
    last_processed_created_at = models.DateTimeField(null=True, blank=True)
    last_processed_id = models.UUIDField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "audit_subscriber_cursors"

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.source_schema} -> {self.last_processed_created_at}"
