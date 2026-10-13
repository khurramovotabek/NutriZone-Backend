"""
Phase 02B's canonical request-level idempotency contract.

This module is the domain-light Port every business Application
Service depends on -- it has zero Django, zero DRF, and zero
PostgreSQL-specific knowledge, matching this project's own Clean
Architecture rule that domain/application code never depends on
infrastructure. The concrete, PostgreSQL-backed implementation lives
in `apps/platform/infrastructure/idempotency.py`.

**Superseded implementation, disclosed explicitly**: this repository
previously had `core/idempotency/decorators.py`, a Redis-only
decorator with zero real callers and zero tests anywhere (confirmed
directly before this phase began). It lacked an actor/principal
boundary (a plain `idempotency_key` + a static namespace string was
the entire uniqueness key -- two different authenticated users
reusing the same client-generated key would have collided) and had a
genuine read-then-write race with no database-level locking or
uniqueness enforcement (two concurrent identical requests could both
observe "no existing record" and both execute the protected
operation). Since nothing depended on it, it is replaced here rather
than left as a second, competing, insufficient primitive alongside a
correct one -- this repository's own established discipline
throughout Phases 01-02A has been to fix or replace unused,
insufficient infrastructure in place rather than accumulate
duplicates.

## The contract

CASE A — first request: execute the operation, persist the result,
return it.

CASE B — same key + same fingerprint, replayed after completion:
return the stored result without re-executing the operation.

CASE C — same key + different fingerprint: reject with
`IdempotencyConflict`. The operation is never executed.

CASE D — same key while the original request is still PROCESSING:
reject with `IdempotencyInProgress`. The database-level unique
constraint on `(actor_id, operation_scope, key)` is what actually
guarantees this is race-safe under real concurrency, not this
contract's own Python-level logic -- see the infrastructure
implementation's own docstring for exactly how.

CASE E — the original operation raised an exception: the record is
marked FAILED, not deleted and not left PROCESSING forever. The
key becomes safely retryable -- a fresh attempt with the same key and
the same fingerprint is treated as a new attempt, not blocked
forever by one failed try. This is the correctness-favoring choice
this phase's own instructions require for financial/inventory
operations: a customer whose payment/stock operation failed must be
able to retry with the same idempotency key, not be permanently
locked out by their own failed attempt.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Protocol, TypeVar

from common.exceptions import ConflictError, ValidationFailed

T = TypeVar("T")

DEFAULT_TTL_SECONDS = 24 * 60 * 60
MAX_KEY_LENGTH = 255


class IdempotencyConflict(ConflictError):
    """CASE C: the same (actor, scope, key) was reused with a different request fingerprint. Maps to 409, matching this project's own status-code convention for state-precondition conflicts (REST API Blueprint §5)."""

    code = "IDEMPOTENCY_KEY_CONFLICT"


class IdempotencyInProgress(ConflictError):
    """CASE D: a request with this exact (actor, scope, key) is currently being processed. Also 409 -- the caller's own retry is what will eventually resolve this, not a client-side input error."""

    code = "IDEMPOTENCY_REQUEST_IN_PROGRESS"


class IdempotencyKeyInvalid(ValidationFailed):
    """The supplied key is malformed (too long, empty, or otherwise unsafe to use). Maps to 422, matching every other structural-validation failure in this project."""

    code = "IDEMPOTENCY_KEY_INVALID"


@dataclass(frozen=True, slots=True)
class IdempotencyOutcome:
    """What the caller (an API view) needs to reconstruct a response: whether this was a fresh execution or a replay, plus the stored status/body for a replay."""

    replayed: bool
    status_code: int
    body: Any


def compute_fingerprint(payload: dict[str, Any]) -> str:
    """
    The canonical, deterministic request-fingerprinting strategy.
    `json.dumps(..., sort_keys=True)` guarantees the same fingerprint
    for semantically identical payloads regardless of key insertion
    order; `default=str` handles UUID/Decimal/datetime values the
    same way every Application Service in this repository already
    serializes them (matching the established `to_payload()`
    convention used throughout the outbox/event system). Only the
    fields the caller explicitly includes participate -- callers are
    responsible for excluding anything that legitimately varies
    between semantically-identical retries (e.g. a client-side
    request timestamp), matching this phase's own explicit "the
    fingerprint must be stable for semantically identical request
    payloads" requirement.
    """
    normalized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(normalized.encode()).hexdigest()


def validate_key(key: str) -> None:
    if not key or not key.strip():
        raise IdempotencyKeyInvalid("Idempotency key must not be empty.")
    if len(key) > MAX_KEY_LENGTH:
        raise IdempotencyKeyInvalid(f"Idempotency key must not exceed {MAX_KEY_LENGTH} characters.")


class IdempotencyExecutor(Protocol):
    """
    The Port every Application Service depends on. `execute()` is the
    only method business code calls -- it owns the full acquire/
    execute-or-replay/complete/fail lifecycle internally, so callers
    never see database locking, ORM models, or DRF request objects.
    """

    def execute(
        self,
        actor_id: str | None,
        operation_scope: str,
        key: str,
        fingerprint: str,
        operation: Callable[[], T],
        result_to_response: Callable[[T], tuple[int, Any]],
    ) -> IdempotencyOutcome: ...
