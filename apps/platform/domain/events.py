"""
apps/platform/domain/events.py

Domain Architecture Specification §2.18's "Domain Events (Emitted):
FeatureFlagChanged, ConfigValueChanged, LocaleAdded" -- only
`FeatureFlagChanged` is defined here, matching this phase's own
Feature-Flags-only scope (see aggregates.py's scope note).
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class FeatureFlagChanged:
    flag_id: uuid.UUID
    key: str
    is_globally_enabled: bool

    def to_payload(self) -> dict:
        return {**asdict(self), "flag_id": str(self.flag_id)}
