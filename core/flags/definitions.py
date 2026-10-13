"""
Flag definitions and evaluation context.

`FlagDefinition` is the shape a `FlagProvider` (providers.py) returns.
`FlagContext` is what a caller supplies to evaluate a flag against --
user, store, and environment scoping, per the mission's "Global flags /
Environment flags / Per-store flags (future-ready) / Percentage
rollout (future-ready)" requirements.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class FlagContext:
    """Evaluation context supplied by the caller."""

    user_id: Any | None = None
    store_id: Any | None = None
    environment: str | None = None  # e.g. "development", "staging", "production"
    extra: dict[str, Any] = field(default_factory=dict)

    def bucketing_key(self, flag_key: str) -> str:
        """
        Deterministic identity used for percentage-rollout bucketing.
        Prefers store_id (rollout is most often store-scoped for a
        retail platform), falls back to user_id, falls back to a
        constant so an anonymous/contextless evaluation is still
        deterministic within a single flag.
        """
        identity = self.store_id or self.user_id or "anonymous"
        return f"{flag_key}:{identity}"


@dataclass(frozen=True, slots=True)
class FlagDefinition:
    """
    A flag's full configuration, as returned by a FlagProvider.

    Evaluation precedence (see engine.py):
        1. `enabled=False` at the global level -> always off, short-circuits
        2. `environments` restriction, if set -> must match FlagContext.environment
        3. `store_allowlist`, if set -> FlagContext.store_id must be a member
        4. `rollout_percentage` -> deterministic bucket check
        5. otherwise -> `enabled`
    """

    key: str
    enabled: bool = False
    environments: frozenset[str] | None = None  # None = all environments
    store_allowlist: frozenset[Any] | None = None  # None = all stores
    rollout_percentage: int | None = None  # None = no rollout gating (0-100)

    def evaluate(self, context: FlagContext) -> bool:
        if not self.enabled:
            return False

        if self.environments is not None and context.environment not in self.environments:
            return False

        if self.store_allowlist is not None:
            if context.store_id is None or context.store_id not in self.store_allowlist:
                return False

        if self.rollout_percentage is not None:
            if self.rollout_percentage >= 100:
                return True
            if self.rollout_percentage <= 0:
                return False
            bucket = self._bucket(context.bucketing_key(self.key))
            return bucket < self.rollout_percentage

        return True

    @staticmethod
    def _bucket(identity: str) -> int:
        """Stable 0-99 bucket for a given identity string."""
        digest = hashlib.sha256(identity.encode()).digest()
        return int.from_bytes(digest[:2], byteorder="big") % 100
