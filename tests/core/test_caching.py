from __future__ import annotations

import pytest

from core.caching import CacheDomain, CacheKeyBuilder, CacheManager, NeverCacheDomainError

pytestmark = pytest.mark.unit


def test_key_builder_rejects_unknown_domain():
    with pytest.raises(ValueError):
        CacheKeyBuilder(domain="not-a-real-domain")


def test_key_builder_produces_namespaced_key():
    keys = CacheKeyBuilder(domain=CacheDomain.PRODUCT)
    key = keys.build("detail", "product-1")
    assert key.startswith("nutrizone:product:v")
    assert "detail:product-1" in key


def test_key_builder_default_version_is_zero():
    """
    Default version is 0, not 1 -- corrected this phase. The prior
    assertion (default is 1) only ever passed because of a genuine
    off-by-one bug: Redis `INCR` on a nonexistent key also produces 1,
    so with a default of 1, the very first `bump_version()` call for
    any domain was a silent no-op (1 -> 1). Confirmed directly against
    real Redis before fixing `CacheKeyBuilder._version()`. See
    `test_bump_version_changes_generated_keys` below for the actual
    business-relevant contract this default exists to satisfy.
    """
    keys = CacheKeyBuilder(domain=CacheDomain.SEARCH)
    assert ":v0:" in keys.build("query")


def test_bump_version_changes_generated_keys():
    keys = CacheKeyBuilder(domain=CacheDomain.STORE)
    key_before = keys.build("directory")
    keys.bump_version()
    key_after = keys.build("directory")
    assert key_before != key_after


def test_bump_version_invalidates_only_its_own_domain():
    product_keys = CacheKeyBuilder(domain=CacheDomain.PRODUCT)
    search_keys = CacheKeyBuilder(domain=CacheDomain.SEARCH)
    product_key_before = product_keys.build("x")
    search_key_before = search_keys.build("x")
    product_keys.bump_version()
    assert product_keys.build("x") != product_key_before
    assert search_keys.build("x") == search_key_before


def test_cache_manager_set_and_get_round_trip():
    manager = CacheManager(CacheDomain.PRODUCT)
    manager.set("detail", "p1", value={"name": "Whey Protein"})
    assert manager.get("detail", "p1") == {"name": "Whey Protein"}


def test_cache_manager_get_missing_key_returns_none():
    manager = CacheManager(CacheDomain.SEARCH)
    assert manager.get("nonexistent") is None


def test_cache_manager_delete_removes_key():
    manager = CacheManager(CacheDomain.STORE)
    manager.set("x", value="y")
    manager.delete("x")
    assert manager.get("x") is None


def test_cache_manager_wallet_domain_refuses_to_cache():
    """Enforces Enterprise REST API Blueprint §13.8: wallet data is never cached."""
    manager = CacheManager(CacheDomain.WALLET)
    with pytest.raises(NeverCacheDomainError):
        manager.set("balance", "wallet-1", value=100)


def test_cache_manager_invalidate_domain_bumps_version():
    manager = CacheManager(CacheDomain.ANALYTICS)
    manager.set("report", value={"total": 1})
    manager.invalidate_domain()
    assert manager.get("report") is None


def test_cache_manager_ttl_override_is_respected():
    manager = CacheManager(CacheDomain.PRODUCT)
    manager.set("x", value="y", ttl_override=120)
    # We can't directly assert Redis TTL without reaching into the
    # client, but confirm the value round-trips correctly with an
    # override in place.
    assert manager.get("x") == "y"
