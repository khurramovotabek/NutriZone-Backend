"""
apps/platform/application/ports.py

Domain Architecture Specification §2.18.
"""
from __future__ import annotations

import uuid
from typing import Protocol

from apps.platform.domain.aggregates import FeatureFlag


class FeatureFlagRepository(Protocol):
    def get_by_id(self, flag_id: uuid.UUID) -> FeatureFlag | None: ...

    def get_by_key(self, key: str) -> FeatureFlag | None: ...

    def list_all(self) -> list[FeatureFlag]: ...
    """Backs `EvaluateFlags` -- "evaluated flags for current context" (REST API Blueprint §13.18) means every registered business flag, not one at a time."""

    def save(self, flag: FeatureFlag) -> FeatureFlag: ...


class FlagPublisher(Protocol):
    """
    Matches `core.flags.providers.RedisFlagProvider`'s own documented
    role exactly (see that module's docstring: "the future `platform`
    app's DB-backed admin UI would write through... keeping evaluation
    fast (Redis-only on the hot path) while the database remains the
    durable, auditable source of truth"). A narrow Protocol so
    Application never imports `core.flags` (an Infrastructure-adjacent
    module) directly -- composition root wires the real
    `RedisFlagProvider` in, translating this aggregate into that
    module's own `FlagDefinition` shape.
    """

    def publish(self, flag: FeatureFlag) -> None: ...
