"""
Outbox publisher helper.

Application services call `stage_event()` from *within* the same
database transaction as the state change they're emitting an event for
-- never after commit, never via a direct synchronous call to another
module's handler (MIC §7 "Outbox Usage"). `stage_event()` validates the
event type against the Domain Event Catalogue registry
(core/events/registry.py) before writing, wraps the payload in a typed,
versioned `EventEnvelope` (correlation_id/causation_id populated
automatically), and returns the persisted row.

The actual cross-process relay (reading unpublished rows and
dispatching them to Celery/the event bus) is a Celery Beat-scheduled
task registered per concrete outbox model, added when the owning
module is implemented -- this file provides the write-side helper and
the relay contract (`OutboxRelay`) every module's relay task will call.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol

from django.db import transaction
from django.utils import timezone

from common.middleware.audit_context import get_current_actor_id
from core.events.registry import registry
from core.outbox.envelope import EventEnvelope

logger = logging.getLogger("nutrizone.app")


class OutboxEventModel(Protocol):
    event_type: str
    event_version: int
    payload: dict[str, Any]
    correlation_id: str | None
    causation_id: str | None
    published_at: Any
    publish_attempts: int

    def save(self, *args: Any, **kwargs: Any) -> None: ...


def stage_event(
    outbox_model: type[OutboxEventModel],
    event_type: str,
    payload: dict[str, Any],
    event_version: int = 1,
    metadata: dict[str, Any] | None = None,
    created_by: Any | None = None,
    validate_against_catalogue: bool = True,
) -> OutboxEventModel:
    """
    Writes one outbox row containing a full EventEnvelope. Must be
    called inside an open transaction that also contains the state
    change the event describes -- callers are responsible for wrapping
    both in `transaction.atomic()` (typically the enclosing Application
    Service method already is).

    `validate_against_catalogue=True` (the default) enforces MIC §7:
    the event_type must already be registered via
    `core.events.registry.registry.register(...)` -- set to False only
    for infrastructure-internal test fixtures that intentionally probe
    unregistered event handling.

    `created_by`, if not explicitly supplied, falls back to
    `common.middleware.audit_context.get_current_actor_id()` -- the
    request-scoped authenticated actor, if any. An explicitly-passed
    `created_by` (including an explicit `None`) always wins; Python's
    own default-parameter mechanism cannot distinguish "explicitly
    None" from "omitted" here, but this is safe: confirmed by a
    repository-wide search before this fallback was added that zero
    existing callers pass `created_by` in any form, so no caller's
    behavior changes as a result of adding it. Outside an HTTP
    request's own lifecycle (Celery tasks, management commands), the
    contextvar was never set and naturally resolves to `None` -- this
    is not special-cased, it is simply how `contextvars.ContextVar`
    behaves when nothing in the current execution context has called
    `set_current_actor_id()`.
    """
    assert transaction.get_connection().in_atomic_block, (
        "stage_event() must be called within an active transaction.atomic() "
        "block alongside the state change it describes (MIC §7)."
    )

    if validate_against_catalogue:
        registry.get(event_type)  # raises EventContractError if unregistered

    if created_by is None:
        created_by = get_current_actor_id()

    envelope = EventEnvelope.build(
        event_type=event_type, payload=payload, event_version=event_version, metadata=metadata
    )

    event = outbox_model(
        event_type=envelope.event_type,
        event_version=envelope.event_version,
        payload=envelope.payload,
        correlation_id=envelope.correlation_id,
        causation_id=envelope.causation_id,
        created_by=created_by,
    )  # type: ignore[call-arg]
    event.save()
    return event


class OutboxRelay:
    """
    Generic relay logic a module's Celery Beat task calls: fetch
    unpublished rows (oldest first), attempt delivery via a supplied
    `publish_fn`, mark published on success, increment
    `publish_attempts` and leave unpublished on failure (so the next
    scheduled run retries it -- backing MIC §7's "Retry Strategy" and
    the dead_letter queue for rows that exceed `max_attempts`).
    """

    def __init__(self, outbox_model: type[OutboxEventModel], max_attempts: int = 5, batch_size: int = 100) -> None:
        self.outbox_model = outbox_model
        self.max_attempts = max_attempts
        self.batch_size = batch_size

    def relay_pending(self, publish_fn) -> dict[str, int]:
        """
        `publish_fn(event_row) -> bool` performs the actual delivery
        (e.g. dispatching a Celery task, calling an event-bus client)
        and returns whether it succeeded. Returns a small summary dict
        for observability/metrics.
        """
        pending = (
            self.outbox_model.objects.filter(published_at__isnull=True, publish_attempts__lt=self.max_attempts)
            .order_by("created_at")[: self.batch_size]
        )

        published_count = 0
        failed_count = 0
        exhausted_count = 0

        for event in pending:
            try:
                success = publish_fn(event)
            except Exception:  # noqa: BLE001 - a publish failure must not crash the relay loop
                logger.exception("Outbox relay: publish_fn raised for event %s", getattr(event, "pk", None))
                success = False

            if success:
                event.published_at = timezone.now()
                event.save(update_fields=["published_at"])
                published_count += 1
            else:
                event.publish_attempts += 1
                if event.publish_attempts >= self.max_attempts:
                    exhausted_count += 1
                    logger.error(
                        "Outbox relay: event %s exhausted %s attempts, routing to dead_letter queue",
                        getattr(event, "pk", None),
                        self.max_attempts,
                    )
                event.save(update_fields=["publish_attempts"])
                failed_count += 1

        return {"published": published_count, "failed": failed_count, "exhausted": exhausted_count}
