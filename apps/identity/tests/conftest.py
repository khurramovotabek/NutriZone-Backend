from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _fake_redis(monkeypatch):
    """Isolates every identity test from needing a live Redis instance -- see tests/core/conftest.py for the identical rationale."""
    import fakeredis

    from core.caching import redis_client as redis_client_module

    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_client_module, "_client", fake)
    monkeypatch.setattr(redis_client_module, "get_redis_client", lambda: fake)
    yield fake
    fake.flushall()
