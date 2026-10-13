"""
`decorators.py` (the pre-Phase-02B, Redis-only implementation) has
been removed and replaced by `contract.py`. Confirmed before removal:
zero real callers and zero tests existed anywhere in the repository,
so this is not a breaking change to any working code -- see
`contract.py`'s own module docstring for the full reasoning.
"""
from core.idempotency.contract import (
    DEFAULT_TTL_SECONDS,
    MAX_KEY_LENGTH,
    IdempotencyConflict,
    IdempotencyExecutor,
    IdempotencyInProgress,
    IdempotencyKeyInvalid,
    IdempotencyOutcome,
    compute_fingerprint,
    validate_key,
)

__all__ = [
    "DEFAULT_TTL_SECONDS", "MAX_KEY_LENGTH", "IdempotencyConflict", "IdempotencyExecutor",
    "IdempotencyInProgress", "IdempotencyKeyInvalid", "IdempotencyOutcome", "compute_fingerprint", "validate_key",
]
