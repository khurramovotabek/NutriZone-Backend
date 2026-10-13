"""
TTL policies.

Maps each cache domain (CacheDomain) to the TTL tier already named in
core/caching/redis_client.py, matching the exact caching rules laid out
per-endpoint in the Enterprise REST API Blueprint §13 and Database
Blueprint §8. Kept as one lookup table so a module never has to decide
"is my product cache short or very-short TTL" ad hoc -- it asks this
policy.
"""
from __future__ import annotations

from core.caching.key_builder import CacheDomain
from core.caching.redis_client import TTL_LONG, TTL_MEDIUM, TTL_SHORT, TTL_VERY_SHORT

CACHE_TTL_POLICY: dict[str, int] = {
    # Product detail/list -- REST API Blueprint §13.2: "public, short TTL"
    CacheDomain.PRODUCT: TTL_SHORT,
    # Search results/autocomplete -- REST API Blueprint §13.16: "short TTL, q-keyed"
    CacheDomain.SEARCH: TTL_SHORT,
    # Store directory -- REST API Blueprint §13.5: "public, long TTL"
    CacheDomain.STORE: TTL_LONG,
    # Wallet -- REST API Blueprint §13.8: explicitly NEVER cached in the
    # read path. This entry exists so a lookup for CacheDomain.WALLET
    # returns an explicit, self-documenting zero rather than a module
    # accidentally reusing a generic default TTL for wallet data.
    CacheDomain.WALLET: 0,
    # Analytics dashboards/reports -- REST API Blueprint §13.14: "short TTL"
    CacheDomain.ANALYTICS: TTL_SHORT,
}


def ttl_for(domain: str) -> int:
    """Returns the TTL (seconds) for a cache domain. 0 means 'never cache'."""
    if domain not in CACHE_TTL_POLICY:
        raise ValueError(f"No TTL policy defined for cache domain '{domain}'.")
    return CACHE_TTL_POLICY[domain]


__all__ = ["CACHE_TTL_POLICY", "ttl_for", "TTL_VERY_SHORT", "TTL_MEDIUM"]
