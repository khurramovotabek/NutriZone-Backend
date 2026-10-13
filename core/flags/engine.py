"""
FeatureFlags facade -- the typed, single entry point every module uses.

Usage:

    from core.flags import FeatureFlags, FlagKey, FlagContext

    if FeatureFlags.is_enabled(FlagKey.ENABLE_CHAT, FlagContext(store_id=store.id)):
        ...

Configured once at process start via `configure()` (called from an
AppConfig.ready() hook or settings, see core/flags/apps_wiring.py) with
the provider chain described in providers.py; falls back to a safe
all-disabled provider if never configured (e.g. in an isolated unit
test that doesn't need flags), so `is_enabled()` never raises just
because wiring hasn't happened yet.
"""
from __future__ import annotations

from core.flags.definitions import FlagContext, FlagDefinition
from core.flags.keys import FlagKey
from core.flags.providers import FlagProvider

_UNCONFIGURED_DEFAULT = FlagDefinition(key="__unconfigured__", enabled=False)


class _NullProvider:
    def get_definition(self, flag_key: str) -> FlagDefinition | None:
        return None


class FeatureFlags:
    """Process-wide facade. Not instantiated -- all methods are static."""

    _provider: FlagProvider = _NullProvider()

    @classmethod
    def configure(cls, provider: FlagProvider) -> None:
        cls._provider = provider

    @classmethod
    def is_enabled(cls, key: FlagKey, context: FlagContext | None = None) -> bool:
        context = context or FlagContext()
        definition = cls._provider.get_definition(key.value)
        if definition is None:
            return False  # fail closed: an unconfigured/unknown flag is off, never on
        return definition.evaluate(context)

    @classmethod
    def get_definition(cls, key: FlagKey) -> FlagDefinition:
        return cls._provider.get_definition(key.value) or FlagDefinition(key=key.value, enabled=False)
