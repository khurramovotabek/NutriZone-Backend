from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _fake_redis(monkeypatch):
    """
    Every core/* component that talks to Redis does so exclusively
    through `core.caching.redis_client.get_redis_client()` -- patching
    that one function is enough to isolate the entire test suite from
    needing a live Redis instance, matching Django Implementation
    Blueprint §11's "application/ports mocked, never a real dependency"
    rule for unit tests.
    """
    import fakeredis

    from core.caching import redis_client as redis_client_module

    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_client_module, "_client", fake)
    monkeypatch.setattr(redis_client_module, "get_redis_client", lambda: fake)
    yield fake
    fake.flushall()
