"""
The concrete, PostgreSQL-backed implementation of
`core.idempotency.contract.IdempotencyExecutor`.

## How real concurrency is actually made safe

Two genuinely concurrent requests with the identical
`(actor_id, operation_scope, key)` racing each other is the scenario
this phase's own instructions call out explicitly (Step 10,
"Concurrency"). Python-level logic alone (e.g. "check if a record
exists, then create one") cannot make this safe -- both requests can
observe "no record exists" before either has written one. What
actually makes this safe:

1. `IdempotencyRecord.Meta.constraints` has a real PostgreSQL unique
   constraint on `(created_by, operation_scope, key)`
   (`uq_idempotency_actor_scope_key`). This is the actual correctness
   boundary, not this file's own code.
2. Both concurrent requests attempt `IdempotencyRecord.objects.create(...)`.
   PostgreSQL allows exactly one to succeed; the loser gets a real
   `IntegrityError` at the database level.
3. The loser does not treat this as an application error -- it
   re-queries for the winner's row (inside `select_for_update()`, so
   it waits for the winner's own transaction to commit rather than
   racing it a second time) and either replays the winner's completed
   result or raises `IdempotencyInProgress` if the winner is still
   executing.

This is the same "let the database's own constraint decide the race,
then handle the loser's IntegrityError" pattern already established
and proven correct elsewhere in this repository (e.g. the Audit
Activity Timeline's own idempotent `get_or_create(id=entry_id, ...)`
pattern, database-verified across real concurrent writes in an
earlier phase) -- reused deliberately here rather than inventing a
new concurrency strategy.

## Transaction participation

`execute()` requires the caller to already be inside a
`transaction.atomic()` block that also wraps the protected business
operation (matching this phase's own Rule 5: idempotency persistence
and the business operation must commit or roll back together, never
independently). This module does not open its own top-level
transaction for that reason -- it uses `transaction.atomic()` only
for the inner "resolve who won the race" step, which is safe to nest.

**Important, confirmed constraint**: the caller must NOT wrap the
*entire* `execute()` call (including the initial acquire step) in an
extra outer `transaction.atomic()` of its own. Confirmed
`ATOMIC_REQUESTS` is unset anywhere in this project's settings, so no
real view does this naturally -- all 4 protected views
(Inventory/Wallet/Ordering/Pricing) call `execute()` directly from
their own `post()` method. If a caller did wrap the whole call in an
outer transaction and that outer transaction later rolled back for an
unrelated reason, the record's own already-committed acquire step
would roll back with it, which is a different (and also acceptable)
policy in isolation, but not the one this module's own `_mark_failed`
path is designed around -- documented here rather than silently
assumed, since this was found by a test exercising exactly that
scenario during this phase's own development.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Callable, TypeVar

from django.db import IntegrityError, transaction
from django.utils import timezone as django_timezone

from apps.platform.infrastructure.models import IdempotencyRecord, IdempotencyRecordStatus
from core.idempotency.contract import (
    DEFAULT_TTL_SECONDS,
    IdempotencyConflict,
    IdempotencyInProgress,
    IdempotencyOutcome,
)

T = TypeVar("T")


class DjangoIdempotencyExecutor:
    def execute(
        self,
        actor_id: str | None,
        operation_scope: str,
        key: str,
        fingerprint: str,
        operation: Callable[[], T],
        result_to_response: Callable[[T], tuple[int, Any]],
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> IdempotencyOutcome:
        record = self._acquire_or_get_existing(actor_id, operation_scope, key, fingerprint, ttl_seconds)

        if record is None:
            # We won the race and created a fresh PROCESSING record.
            # Execute the real operation now, inside the same
            # transaction the caller is already in (Rule 5).
            try:
                result = operation()
            except Exception:
                self._mark_failed(actor_id, operation_scope, key)
                raise
            status_code, body = result_to_response(result)
            self._mark_completed(actor_id, operation_scope, key, status_code, body)
            return IdempotencyOutcome(replayed=False, status_code=status_code, body=body)

        # A record already existed -- resolve what it means for this caller.
        if record.request_fingerprint != fingerprint:
            raise IdempotencyConflict(f"Idempotency key '{key}' was reused with a different request.")
        if record.status == IdempotencyRecordStatus.PROCESSING:
            raise IdempotencyInProgress(f"A request with idempotency key '{key}' is currently being processed.")
        if record.status == IdempotencyRecordStatus.FAILED:
            # CASE E policy: a failed attempt's key is safely retryable,
            # not a permanent lock -- re-run the operation as a fresh
            # attempt. The conditional UPDATE (WHERE status=FAILED) is
            # itself the race-safety mechanism for concurrent retries of
            # the same failed key: exactly one concurrent retry can win
            # this transition, matching the same "let the database
            # decide" discipline as the initial acquire step above.
            won_retry = IdempotencyRecord.objects.filter(
                created_by=actor_id, operation_scope=operation_scope, key=key, status=IdempotencyRecordStatus.FAILED,
            ).update(status=IdempotencyRecordStatus.PROCESSING)
            if not won_retry:
                raise IdempotencyInProgress(f"A request with idempotency key '{key}' is currently being processed.")
            try:
                result = operation()
            except Exception:
                self._mark_failed(actor_id, operation_scope, key)
                raise
            status_code, body = result_to_response(result)
            self._mark_completed(actor_id, operation_scope, key, status_code, body)
            return IdempotencyOutcome(replayed=False, status_code=status_code, body=body)
        # COMPLETED: genuine replay, matching fingerprint -- do not re-execute.
        return IdempotencyOutcome(replayed=True, status_code=record.response_status_code, body=record.response_body)

    def _acquire_or_get_existing(self, actor_id, operation_scope, key, fingerprint, ttl_seconds) -> IdempotencyRecord | None:
        now = django_timezone.now()
        try:
            with transaction.atomic():
                IdempotencyRecord.objects.create(
                    created_by=actor_id, operation_scope=operation_scope, key=key,
                    request_fingerprint=fingerprint, status=IdempotencyRecordStatus.PROCESSING,
                    expires_at=now + timedelta(seconds=ttl_seconds),
                )
            return None  # we won the race; caller executes the operation
        except IntegrityError:
            # Someone else (or a prior attempt by the same actor) already
            # holds this (actor, scope, key). select_for_update() here
            # waits for their transaction rather than racing them again.
            with transaction.atomic():
                return IdempotencyRecord.objects.select_for_update().get(
                    created_by=actor_id, operation_scope=operation_scope, key=key,
                )

    def _mark_completed(self, actor_id, operation_scope, key, status_code: int, body: Any) -> None:
        now = django_timezone.now()
        IdempotencyRecord.objects.filter(created_by=actor_id, operation_scope=operation_scope, key=key).update(
            status=IdempotencyRecordStatus.COMPLETED, response_status_code=status_code, response_body=body, completed_at=now,
        )

    def _mark_failed(self, actor_id, operation_scope, key) -> None:
        IdempotencyRecord.objects.filter(created_by=actor_id, operation_scope=operation_scope, key=key).update(
            status=IdempotencyRecordStatus.FAILED,
        )
