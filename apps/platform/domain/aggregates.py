"""
apps/platform/domain/aggregates.py

Domain Architecture Specification §2.18 -- FeatureFlag aggregate root.

**Scope note**: Platform's full spec covers three sub-capabilities --
Feature Flags, Config Values, and Locale registry. This phase
implements Feature Flags only, the one explicitly documented as a
universal dependency of every other bounded context (§2.18's own
"Incoming Dependencies: Every context" line, and REST API Blueprint
§13.18's "the one endpoint every other module implicitly depends on").
Config Values and Locale registry remain genuinely unimplemented,
disclosed explicitly in this phase's certification report rather than
silently left unmentioned.

This aggregate is the durable, auditable source of truth (Database
Blueprint §4.18 `platform.feature_flags`) behind `core.flags`'s
already-existing evaluation engine -- see `core/flags/keys.py` and
`core/flags/providers.py`'s own docstrings, which already describe
this exact relationship before this module existed.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from apps.platform.domain.exceptions import InvalidRolloutPercentage


class _Unset:
    """A real PATCH-semantics distinction, matching the identical fix already proven in the Identity module: `rollout_percentage` is the one field here with a genuine nullable-clear meaning (`None` = "no rollout gating," a real Domain state) -- `UNSET` means "not supplied, leave unchanged," while an explicit `None` means "clear the rollout percentage.\""""

    def __repr__(self) -> str:  # pragma: no cover
        return "UNSET"


UNSET = _Unset()


@dataclass(slots=True)
class FeatureFlag:
    """
    Root. A business-defined flag, distinct from `core.flags.FlagKey`'s
    fixed enum of infrastructure-level master switches (see that
    module's own docstring) -- this aggregate's `key` is an arbitrary,
    staff-defined string, not required to be a `FlagKey` member.
    """

    id: uuid.UUID
    key: str
    is_globally_enabled: bool = False
    rollout_percentage: int | None = None
    rollout_scope: dict = field(default_factory=dict)
    """JSONB-backed store/user-segment targeting rules (Database Blueprint §4.18) -- kept as a plain dict, matching the blueprint's own "JSONB used narrowly and deliberately" guidance rather than modeling a speculative VO hierarchy for open-ended targeting data."""

    def __post_init__(self) -> None:
        self._validate_rollout_percentage()

    def _validate_rollout_percentage(self) -> None:
        if self.rollout_percentage is not None and not (0 <= self.rollout_percentage <= 100):
            raise InvalidRolloutPercentage("rollout_percentage must be between 0 and 100.")

    def update_rollout(self, is_globally_enabled: bool | None = None, rollout_percentage: int | None | _Unset = UNSET, rollout_scope: dict | None = None) -> None:
        """Matches REST API Blueprint §13.18's `PATCH /settings/feature-flags/{id}` ("Update rollout rule") exactly. `is_globally_enabled`/`rollout_scope` are non-nullable in this Domain, so `None` unambiguously means "not supplied" for them. `rollout_percentage` is genuinely nullable (`None` = no rollout gating) -- it alone uses the `UNSET` sentinel so an explicit `rollout_percentage=None` can clear it, distinct from not mentioning it at all."""
        if is_globally_enabled is not None:
            self.is_globally_enabled = is_globally_enabled
        if rollout_percentage is not UNSET:
            self.rollout_percentage = rollout_percentage
        if rollout_scope is not None:
            self.rollout_scope = rollout_scope
        self._validate_rollout_percentage()
