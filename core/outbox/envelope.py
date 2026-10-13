"""
Event envelope.

Every event staged via `core.outbox.stage_event()` is wrapped in an
`EventEnvelope` before it is written to a schema's outbox table. This
gives every event, regardless of which module emits it, a uniform
metadata shape:

  - `event_version`: schema version of *this event type's payload*
    (independent of the API's v1/v2 versioning, Enterprise REST API
    Blueprint §2) -- lets a payload shape evolve (a field added,
    renamed, or reinterpreted) without breaking a consumer that hasn't
    been updated yet, since the consumer can branch on `event_version`.
  - `correlation_id` / `causation_id`: sourced automatically from
    `core.observability.correlation` at staging time, giving every
    event the "what business transaction is this part of" / "what
    directly caused this" metadata the mission's "Domain Events"
    section requires, with zero manual plumbing at each call site.
  - `occurred_at`: via `core.clock.Clock`, never a raw timestamp call,
    so event timestamps are freezable in tests exactly like everything
    else that reasons about "now".

This shape is also what makes "replay compatibility / future Kafka
compatibility" (mission wording) realistic later: a Kafka producer
would serialize exactly this envelope as the message value, with
`correlation_id` as a natural partition/tracing key -- no structural
change needed to move from "Postgres outbox table + relay worker" to
"outbox table + relay worker that publishes to Kafka" (Django
Implementation Blueprint §8/§18's extraction-seam philosophy, applied
to the event transport specifically).
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from core.clock import Clock
from core.observability.correlation import get_causation_id, get_correlation_id


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    event_id: str
    event_type: str
    event_version: int
    occurred_at: str
    correlation_id: str | None
    causation_id: str | None
    payload: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def build(
        event_type: str,
        payload: dict[str, Any],
        event_version: int = 1,
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
    ) -> "EventEnvelope":
        return EventEnvelope(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            event_version=event_version,
            occurred_at=Clock.now().isoformat(),
            correlation_id=correlation_id or get_correlation_id(),
            causation_id=causation_id or get_causation_id(),
            payload=payload,
            metadata=metadata or {},
        )
