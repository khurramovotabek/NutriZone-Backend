from __future__ import annotations

import fakeredis
import pytest

from core.caching import redis_client as redis_client_module


@pytest.fixture(autouse=True)
def _fake_redis(monkeypatch):
    """Isolates every POS test from needing a live Redis instance -- matches every prior module's identical test fixture."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_client_module, "_client", fake)
    monkeypatch.setattr(redis_client_module, "get_redis_client", lambda: fake)
    yield fake
    fake.flushall()
