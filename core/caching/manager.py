"""
CacheManager -- the single entry point combining CacheKeyBuilder, TTL
policy, and get/set/invalidate operations, so a module never has to
manually assemble a key + look up a TTL + call the Redis client
separately (three chances to get one of them wrong).

Enforces the "wallet is never cached" rule (Enterprise REST API
Blueprint §13.8) as an actual runtime guard, not just documentation --
`CacheManager(CacheDomain.WALLET).set(...)` raises.
"""
from __future__ import annotations

import json
from typing import Any

from core.caching.key_builder import CacheDomain, CacheKeyBuilder
from core.caching.redis_client import get_redis_client
from core.caching.ttl_policies import ttl_for


class NeverCacheDomainError(RuntimeError):
    """Raised when code attempts to cache a value in a domain whose TTL policy is 0 (never cache)."""


class CacheManager:
    def __init__(self, domain: str) -> None:
        self.domain = domain
        self._keys = CacheKeyBuilder(domain=domain)
        self._client = get_redis_client()
        self._ttl = ttl_for(domain)

    def get(self, *key_parts: Any) -> Any | None:
        raw = self._client.get(self._keys.build(*key_parts))
        if raw is None:
            return None
        return json.loads(raw)

    def set(self, *key_parts: Any, value: Any, ttl_override: int | None = None) -> None:
        ttl = ttl_override if ttl_override is not None else self._ttl
        if ttl <= 0:
            raise NeverCacheDomainError(
                f"Cache domain '{self.domain}' has a TTL policy of 0 (never cache) -- "
                f"see core/caching/ttl_policies.py. This is deliberate for wallet data "
                f"per Enterprise REST API Blueprint §13.8."
            )
        self._client.set(self._keys.build(*key_parts), json.dumps(value, default=str), ex=ttl)

    def delete(self, *key_parts: Any) -> None:
        self._client.delete(self._keys.build(*key_parts))

    def invalidate_domain(self) -> int:
        """Bulk-invalidates every key ever built for this domain (CacheKeyBuilder.bump_version)."""
        return self._keys.bump_version()


def product_cache() -> CacheManager:
    return CacheManager(CacheDomain.PRODUCT)


def search_cache() -> CacheManager:
    return CacheManager(CacheDomain.SEARCH)


def store_cache() -> CacheManager:
    return CacheManager(CacheDomain.STORE)


def analytics_cache() -> CacheManager:
    return CacheManager(CacheDomain.ANALYTICS)
