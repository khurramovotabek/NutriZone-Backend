"""
Abstract Outbox event base model.

Per Enterprise Database Blueprint §6 ("Note on the Outbox table itself"),
every schema that emits domain events owns its own concrete
`outbox_events` table. This module provides the ONE abstract base every
such concrete table inherits from, so the shape (and the guarantee that
it behaves like an AppendOnlyModel) is defined exactly once.

No concrete `OutboxEvent` table is created at foundation stage -- each
business module creates its own concrete subclass in its own
`infrastructure/models.py` when that module is implemented (MIC §1 step
16), living in that module's own schema per the "no cross-schema FK"
rule.
"""
from __future__ import annotations

from django.db import models

from common.models.base import AppendOnlyModel


class AbstractOutboxEvent(AppendOnlyModel):
    """
    Base shape for a schema's outbox table.

    Fields beyond the AppendOnlyModel base:
        event_type: matches an entry in the Domain Event Catalogue
            (Domain Architecture Specification §6).
        event_version: schema version of this event type's payload
            (core/outbox/envelope.py's EventEnvelope.event_version) --
            independent of API versioning, lets a payload shape evolve
            without breaking consumers pinned to an older version.
        payload: the event's JSON payload, matching the shape registered
            in shared/event_contracts/ for this event_type.
        correlation_id / causation_id: propagated automatically from
            core/observability/correlation.py at staging time -- see
            core/outbox/envelope.py for why both are needed.
        published_at: null until the relay worker successfully delivers
            the event; never set directly by the emitting code.
        publish_attempts: incremented by the relay worker on each
            attempt, backing the retry/backoff policy (Django
            Implementation Blueprint §8).
    """

    event_type = models.CharField(max_length=128, db_index=True)
    event_version = models.PositiveIntegerField(default=1)
    payload = models.JSONField()
    correlation_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    causation_id = models.CharField(max_length=64, null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    publish_attempts = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["published_at", "created_at"]),
            models.Index(fields=["correlation_id"]),
        ]
