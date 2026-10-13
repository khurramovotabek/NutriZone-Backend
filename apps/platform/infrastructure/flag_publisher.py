"""
apps/platform/infrastructure/flag_publisher.py

Implements `application/ports.py::FlagPublisher`, wrapping
`core.flags.providers.RedisFlagProvider` exactly as that module's own
docstring describes: "the future `platform` app's DB-backed admin UI
would write through (the DB row's save() would call
`RedisFlagProvider.set_definition()` to publish the change), keeping
evaluation fast (Redis-only on the hot path) while the database
remains the durable, auditable source of truth."
"""
from __future__ import annotations

from apps.platform.domain.aggregates import FeatureFlag
from core.flags.definitions import FlagDefinition
from core.flags.providers import RedisFlagProvider


def to_flag_definition(flag: FeatureFlag) -> FlagDefinition:
    """Shared by `RedisFlagPublisher.publish()` below and `infrastructure/composition.py`'s `build_evaluate_flags()` (which needs the identical translation to build its per-request evaluation closure) -- a single conversion, not duplicated at two call sites."""
    store_allowlist = flag.rollout_scope.get("store_allowlist")
    return FlagDefinition(
        key=flag.key,
        enabled=flag.is_globally_enabled,
        environments=None,
        store_allowlist=frozenset(store_allowlist) if store_allowlist else None,
        rollout_percentage=flag.rollout_percentage,
    )


class RedisFlagPublisher:
    def __init__(self) -> None:
        self._provider = RedisFlagProvider()

    def publish(self, flag: FeatureFlag) -> None:
        self._provider.set_definition(to_flag_definition(flag))
