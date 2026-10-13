from __future__ import annotations

import pytest

from core.health.checks import check_disk, check_queue_depth, check_redis, check_storage

pytestmark = pytest.mark.unit


def test_check_redis_reports_healthy_when_reachable():
    ok, detail = check_redis()
    assert ok is True
    assert detail == "ok"


def test_check_redis_reports_unhealthy_when_ping_raises(monkeypatch):
    import core.health.checks as checks_module

    class _BrokenClient:
        def ping(self):
            raise ConnectionError("refused")

    monkeypatch.setattr(
        "core.caching.redis_client.get_redis_client", lambda: _BrokenClient()
    )
    ok, detail = check_redis()
    assert ok is False
    assert "unavailable" in detail


def test_check_disk_reports_healthy_with_reasonable_threshold():
    ok, detail = check_disk(path="/", min_free_percent=0.0)
    assert ok is True
    assert "free" in detail


def test_check_disk_reports_unhealthy_when_threshold_impossible():
    ok, detail = check_disk(path="/", min_free_percent=100.1)
    assert ok is False
    assert "low disk space" in detail


def test_check_storage_round_trips_a_probe_file(tmp_path, monkeypatch, settings):
    from core.storage import LocalDiskBackend

    monkeypatch.setattr(
        "core.storage.get_storage_backend", lambda: LocalDiskBackend(root=tmp_path)
    )
    ok, detail = check_storage()
    assert ok is True
    assert detail == "ok"


def test_check_storage_reports_failure_when_backend_raises(monkeypatch):
    class _BrokenBackend:
        def save(self, *a, **k):
            raise OSError("disk full")

    monkeypatch.setattr("core.storage.get_storage_backend", lambda: _BrokenBackend())
    ok, detail = check_storage()
    assert ok is False
    assert "unavailable" in detail


def test_check_queue_depth_healthy_when_under_threshold():
    ok, detail = check_queue_depth(queue_names=("transactional",), max_depth=1000)
    assert ok is True


def test_check_queue_depth_unhealthy_when_over_threshold(_fake_redis):
    _fake_redis.rpush("transactional", *["x"] * 50)
    ok, detail = check_queue_depth(queue_names=("transactional",), max_depth=10)
    assert ok is False
    assert "over threshold" in detail
