"""
Correlation / causation ID propagation.

`correlation_id` identifies one end-to-end business operation as it
crosses process/transport boundaries (an HTTP request -> an Outbox
event -> a Celery task -> another Outbox event...). `causation_id`
identifies the *immediate* predecessor that caused this specific
step -- the difference matters for the "Domain Events: replay
compatibility / future Kafka compatibility" requirement, since a
Kafka-style event log needs both "what business transaction is this
part of" (correlation) and "what directly triggered this" (causation)
to reconstruct a causal chain, not just a flat list of same-correlation
events.

Reuses the same contextvars mechanism as
common/middleware/audit_context.py's request-ID tracking (extended
here to a dedicated correlation/causation pair, since request_id and
correlation_id are related but not identical concepts: a single
correlation_id can span many HTTP requests + async task hops, while
request_id is scoped to one HTTP request only).
"""
from __future__ import annotations

import contextlib
import contextvars
import uuid
from typing import Iterator

_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("correlation_id", default=None)
_causation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("causation_id", default=None)


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def get_causation_id() -> str | None:
    return _causation_id.get()


def new_correlation_id() -> str:
    return str(uuid.uuid4())


@contextlib.contextmanager
def correlation_scope(correlation_id: str | None = None, causation_id: str | None = None) -> Iterator[str]:
    """
    Opens a correlation scope for the duration of the `with` block.

    Usage at an entrypoint (an API view, a Celery task, an event
    handler):

        with correlation_scope(correlation_id=incoming_id) as cid:
            ...  # everything inside sees get_correlation_id() == cid

    When starting a *new* business operation with no incoming
    correlation id (e.g. an API request that begins a fresh
    transaction), pass `correlation_id=None` and one is generated.
    """
    resolved = correlation_id or new_correlation_id()
    corr_token = _correlation_id.set(resolved)
    caus_token = _causation_id.set(causation_id)
    try:
        yield resolved
    finally:
        _correlation_id.reset(corr_token)
        _causation_id.reset(caus_token)
