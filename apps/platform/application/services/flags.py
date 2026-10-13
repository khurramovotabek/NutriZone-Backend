"""
apps/platform/application/services/flags.py

Domain Architecture Specification §2.18's `Application Services`:
`DefineFeatureFlag`, `EvaluateFlag` (per this phase's own scope note,
implemented here as `EvaluateFlags`, plural -- REST API Blueprint
§13.18's `GET /settings/feature-flags` returns every evaluated flag
for the current context in one call, matching its own "called by
every client at session bootstrap" description; a single-flag
`EvaluateFlag(flagKey, context)` variant is trivially derivable from
this but not separately exposed, since nothing in the confirmed API
contract calls for it).

`UpdateFeatureFlag` is this phase's own naming for the spec's implied
"update rollout rule" responsibility (REST API Blueprint §13.18
`PATCH /settings/feature-flags/{id}`) -- the spec's own Application
Services list doesn't name this one explicitly, but the API contract
requires it, so it is implemented following `DefineFeatureFlag`'s
identical shape.
"""
from __future__ import annotations

import uuid

from django.db import transaction

from apps.platform.application.ports import FeatureFlagRepository, FlagPublisher
from apps.platform.application.services._shared import PlatformServiceContext
from apps.platform.domain.aggregates import UNSET, FeatureFlag, _Unset
from apps.platform.domain.exceptions import DuplicateFlagKey
from common.exceptions import ResourceNotFound


class DefineFeatureFlag:
    """`POST /settings/feature-flags` -- staff-only, `platform.flag.manage`."""

    def __init__(self, repo: FeatureFlagRepository, publisher: FlagPublisher, ctx: PlatformServiceContext) -> None:
        self._repo = repo
        self._publisher = publisher
        self._ctx = ctx

    def execute(self, key: str, is_globally_enabled: bool = False, rollout_percentage: int | None = None, rollout_scope: dict | None = None) -> FeatureFlag:
        if self._repo.get_by_key(key) is not None:
            raise DuplicateFlagKey(f"A feature flag with key '{key}' already exists.")

        flag = FeatureFlag(id=uuid.uuid4(), key=key, is_globally_enabled=is_globally_enabled, rollout_percentage=rollout_percentage, rollout_scope=rollout_scope or {})
        with transaction.atomic():
            saved = self._repo.save(flag)
            self._publisher.publish(saved)
            self._ctx.stage_events([("FeatureFlagChanged", {"flag_id": str(saved.id), "key": saved.key, "is_globally_enabled": saved.is_globally_enabled})])
        self._ctx.audit().created(entity_type="FeatureFlag", entity_id=str(saved.id), after={"key": saved.key, "is_globally_enabled": saved.is_globally_enabled, "rollout_percentage": saved.rollout_percentage})
        return saved


class UpdateFeatureFlag:
    """`PATCH /settings/feature-flags/{id}` -- staff-only, `platform.flag.manage`."""

    def __init__(self, repo: FeatureFlagRepository, publisher: FlagPublisher, ctx: PlatformServiceContext) -> None:
        self._repo = repo
        self._publisher = publisher
        self._ctx = ctx

    def execute(self, flag_id: uuid.UUID, is_globally_enabled: bool | None = None, rollout_percentage: int | None | _Unset = UNSET, rollout_scope: dict | None = None) -> FeatureFlag:
        flag = self._repo.get_by_id(flag_id)
        if flag is None:
            raise ResourceNotFound("Feature flag not found.")

        before = {"is_globally_enabled": flag.is_globally_enabled, "rollout_percentage": flag.rollout_percentage}
        flag.update_rollout(is_globally_enabled=is_globally_enabled, rollout_percentage=rollout_percentage, rollout_scope=rollout_scope)
        with transaction.atomic():
            saved = self._repo.save(flag)
            self._publisher.publish(saved)
            self._ctx.stage_events([("FeatureFlagChanged", {"flag_id": str(saved.id), "key": saved.key, "is_globally_enabled": saved.is_globally_enabled})])
        self._ctx.audit().updated(entity_type="FeatureFlag", entity_id=str(saved.id), before=before, after={"is_globally_enabled": saved.is_globally_enabled, "rollout_percentage": saved.rollout_percentage})
        return saved


class EvaluateFlags:
    """
    `GET /settings/feature-flags` -- authenticated or anonymous, per
    REST API Blueprint §13.18. Evaluates every registered business
    flag against the caller's context (user/store/environment),
    returning a flat `{key: bool}` map -- exactly what a session-
    bootstrap client needs, nothing more (no rollout internals,
    percentages, or scope rules are exposed, matching Security §16's
    "do not expose... administrative metadata" instruction).
    """

    def __init__(self, repo: FeatureFlagRepository) -> None:
        self._repo = repo

    def execute(self, evaluate_fn) -> dict[str, bool]:
        """`evaluate_fn(flag: FeatureFlag) -> bool` is injected by the composition root (wrapping `core.flags.definitions.FlagDefinition.evaluate()` against the caller's real `FlagContext`) -- this service only orchestrates "evaluate every registered flag," never re-implements rollout-percentage/store-allowlist logic itself (that logic already exists, correctly, in `core.flags`)."""
        return {flag.key: evaluate_fn(flag) for flag in self._repo.list_all()}
