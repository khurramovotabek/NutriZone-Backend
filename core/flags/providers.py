"""
Flag providers.

`FlagProvider` is the abstract interface every source of flag
configuration implements. Two concrete providers are supplied here:

  - `EnvironmentFlagProvider`: reads a static on/off value from Django
    settings/environment variables -- the correct home for a flag that
    genuinely needs a redeploy to change (Django Implementation
    Blueprint §7's "infrastructure toggle" case), and the safe default
    fallback when no runtime override exists.
  - `RedisFlagProvider`: reads a runtime-editable `FlagDefinition` from
    Redis, enabling the "Runtime enable/disable" requirement without a
    redeploy. This is the provider the future `platform` app's
    DB-backed admin UI would write through (the DB row's save() would
    call `RedisFlagProvider.set_definition()` to publish the change),
    keeping evaluation fast (Redis-only on the hot path) while the
    database remains the durable, auditable source of truth once
    `platform` exists.

`CachedFlagProvider` wraps any provider with a short in-process TTL
cache, so a hot code path evaluating the same flag many times per
second doesn't round-trip to Redis on every call -- the "Cached
evaluation" requirement.
"""
from __future__ import annotations

import json
import time
from typing import Protocol

from core.caching.redis_client import cache_key, get_redis_client
from core.flags.definitions import FlagDefinition


class FlagProvider(Protocol):
    def get_definition(self, flag_key: str) -> FlagDefinition | None: ...


class EnvironmentFlagProvider:
    """
    Static, settings-backed provider. `overrides` is typically sourced
    from `settings.NUTRIZONE_INFRA_FLAGS` (config/settings/base.py) at
    construction time.
    """

    def __init__(self, overrides: dict[str, bool] | None = None) -> None:
        self._overrides = overrides or {}

    def get_definition(self, flag_key: str) -> FlagDefinition | None:
        if flag_key not in self._overrides:
            return None
        return FlagDefinition(key=flag_key, enabled=self._overrides[flag_key])


_REDIS_NAMESPACE = "flags"


class RedisFlagProvider:
    """Runtime-editable flag store backed by Redis."""

    def __init__(self) -> None:
        self._client = get_redis_client()

    def _key(self, flag_key: str) -> str:
        return cache_key(flag_key, namespace=_REDIS_NAMESPACE)

    def get_definition(self, flag_key: str) -> FlagDefinition | None:
        raw = self._client.get(self._key(flag_key))
        if raw is None:
            return None
        payload = json.loads(raw)
        return FlagDefinition(
            key=flag_key,
            enabled=payload.get("enabled", False),
            environments=frozenset(payload["environments"]) if payload.get("environments") else None,
            store_allowlist=frozenset(payload["store_allowlist"]) if payload.get("store_allowlist") else None,
            rollout_percentage=payload.get("rollout_percentage"),
        )

    def set_definition(self, definition: FlagDefinition) -> None:
        payload = {
            "enabled": definition.enabled,
            "environments": sorted(definition.environments) if definition.environments else None,
            "store_allowlist": sorted(map(str, definition.store_allowlist)) if definition.store_allowlist else None,
            "rollout_percentage": definition.rollout_percentage,
        }
        self._client.set(self._key(definition.key), json.dumps(payload))

    def delete_definition(self, flag_key: str) -> None:
        self._client.delete(self._key(flag_key))


class CachedFlagProvider:
    """Wraps another provider with a short-TTL in-process cache."""

    def __init__(self, inner: FlagProvider, ttl_seconds: float = 5.0) -> None:
        self._inner = inner
        self._ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[float, FlagDefinition | None]] = {}

    def get_definition(self, flag_key: str) -> FlagDefinition | None:
        cached = self._cache.get(flag_key)
        now = time.monotonic()
        if cached is not None and (now - cached[0]) < self._ttl_seconds:
            return cached[1]
        definition = self._inner.get_definition(flag_key)
        self._cache[flag_key] = (now, definition)
        return definition

    def invalidate(self, flag_key: str) -> None:
        self._cache.pop(flag_key, None)

    def clear(self) -> None:
        self._cache.clear()


class ChainedFlagProvider:
    """
    Tries each provider in order, returns the first definition found.
    Typical chain: [CachedFlagProvider(RedisFlagProvider()), EnvironmentFlagProvider(...)]
    -- Redis (runtime-editable) takes precedence over the static
    environment default when both exist.
    """

    def __init__(self, providers: list[FlagProvider]) -> None:
        self._providers = providers

    def get_definition(self, flag_key: str) -> FlagDefinition | None:
        for provider in self._providers:
            definition = provider.get_definition(flag_key)
            if definition is not None:
                return definition
        return None
