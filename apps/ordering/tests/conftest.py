from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _fake_redis(monkeypatch):
    """Isolates every Ordering test from needing a live Redis instance -- matches every prior module's identical test fixture."""
    import fakeredis

    from core.caching import redis_client as redis_client_module

    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_client_module, "_client", fake)
    monkeypatch.setattr(redis_client_module, "get_redis_client", lambda: fake)
    yield fake
    fake.flushall()
