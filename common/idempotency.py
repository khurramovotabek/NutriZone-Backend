"""
The API-layer half of Phase 02B's idempotency foundation. The
domain-light contract and PostgreSQL-backed executor live in
`core/idempotency/contract.py` and
`apps/platform/infrastructure/idempotency.py` respectively -- this
module is deliberately the only place DRF-specific concerns (the
`Idempotency-Key` header, `Response` construction) are allowed to
live, matching this project's own Clean Architecture rule that
Application Services never import `rest_framework`.

## Canonical header

`Idempotency-Key` (matching this repository's existing header-naming
convention, e.g. `Authorization`, `X-Request-Id` where present).
Format: any non-empty opaque string up to 255 characters -- UUID is
not required, since some clients (this task's own stated concern)
have simpler natural idempotency tokens available (e.g. a mobile
client's own locally-generated operation ID) and forcing UUID would
be an arbitrary extra constraint with no correctness benefit.

## Which endpoints require the header

Only the specific views that opt in via `protect_with_idempotency()`
-- this is deliberately opt-in per view, not global middleware,
matching this phase's own explicit instruction not to put business
idempotency logic into middleware. A missing header on a protected
endpoint is a 422 `IDEMPOTENCY_KEY_REQUIRED` validation failure, not
a silent pass-through, since silently allowing an unprotected
duplicate on an endpoint this module's own caller decided needed
protection would defeat the entire point.
"""
from __future__ import annotations

from typing import Any, Callable

from rest_framework.request import Request

from apps.platform.infrastructure.composition import build_idempotency_executor
from common.exceptions import ValidationFailed
from common.responses import success_response
from core.idempotency.contract import compute_fingerprint, validate_key

IDEMPOTENCY_HEADER = "Idempotency-Key"


def protect_with_idempotency(
    request: Request,
    actor_id: Any,
    operation_scope: str,
    fingerprint_payload: dict[str, Any],
    operation: Callable[[], Any],
    result_to_payload: Callable[[Any], Any],
    success_status_code: int = 200,
):
    """
    Wraps a view's existing `<application service>.execute(...)` call.
    `fingerprint_payload` should be the serializer's own
    `validated_data` (or an equivalent explicit dict) -- never the
    raw request body, so that semantically-identical requests with
    incidental formatting differences (key order, whitespace) still
    fingerprint identically, per `compute_fingerprint()`'s own
    documented guarantee.

    Returns a DRF `Response` ready to be returned directly from the
    view, preserving the existing `{"success": true, "data": ...}`
    envelope for both fresh executions and replays.
    """
    key = request.headers.get(IDEMPOTENCY_HEADER)
    if not key:
        raise ValidationFailed(f"The '{IDEMPOTENCY_HEADER}' header is required for this operation.", details={"fields": [{"field": IDEMPOTENCY_HEADER, "code": "REQUIRED"}]})
    validate_key(key)

    fingerprint = compute_fingerprint(fingerprint_payload)
    actor_id_str = str(actor_id) if actor_id is not None else None

    outcome = build_idempotency_executor().execute(
        actor_id=actor_id_str,
        operation_scope=operation_scope,
        key=key,
        fingerprint=fingerprint,
        operation=operation,
        result_to_response=lambda result: (success_status_code, result_to_payload(result)),
    )
    return success_response(data=outcome.body, status_code=outcome.status_code, meta_extra={"idempotent_replay": outcome.replayed} if outcome.replayed else None)
