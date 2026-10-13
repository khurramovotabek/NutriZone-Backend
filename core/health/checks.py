"""
Individual health checks.

Each function returns `(is_healthy: bool, detail: str)` and never
raises -- a check that fails is reported as unhealthy, not as a 500
from the health endpoint itself, since the health endpoint's own
availability is what the orchestrator is relying on.

`core/health/views.py` composes these into the `/health/ready`
response; each is also independently importable for use in a
management command / startup probe.
"""
from __future__ import annotations

import logging
import shutil

logger = logging.getLogger("nutrizone.app")

HealthCheckResult = tuple[bool, str]


def check_database() -> HealthCheckResult:
    from django.db import connections

    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        # Phase 15: /health/ready is reachable from the public internet
        # (confirmed via docker/nginx/nginx.conf -- it has no dedicated
        # location block and falls through to the catch-all proxy).
        # Full exception logged server-side only; the public-facing
        # detail stays generic to avoid leaking internal connection
        # details to an unauthenticated caller.
        logger.warning("Database health check failed: %s", exc)
        return False, "unavailable"


def check_redis() -> HealthCheckResult:
    try:
        from core.caching.redis_client import get_redis_client

        get_redis_client().ping()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis health check failed: %s", exc)
        return False, "unavailable"


def check_celery() -> HealthCheckResult:
    """
    Verifies at least one Celery worker is reachable via a broker-level
    ping (does not enqueue/execute a real task). A foundation-phase
    deployment with no workers running yet will correctly report this
    as unhealthy -- that's accurate, not a bug in the check.
    """
    try:
        from config.celery import app as celery_app

        replies = celery_app.control.ping(timeout=1.0)
        if replies:
            return True, f"ok ({len(replies)} worker(s) responded)"
        return False, "no workers responded"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_disk(path: str = "/", min_free_percent: float = 10.0) -> HealthCheckResult:
    try:
        total, _used, free = shutil.disk_usage(path)
        free_percent = (free / total) * 100 if total else 0.0
        if free_percent < min_free_percent:
            return False, f"low disk space: {free_percent:.1f}% free (minimum {min_free_percent}%)"
        return True, f"ok ({free_percent:.1f}% free)"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_storage() -> HealthCheckResult:
    """Verifies the configured MediaStorageBackend is reachable (a write+read+delete round-trip of a tiny probe object)."""
    try:
        from core.storage import get_storage_backend

        backend = get_storage_backend()
        probe_path = "_health_check/probe.txt"
        backend.save(probe_path, b"ok")
        content = backend.read(probe_path)
        backend.delete(probe_path)
        if content != b"ok":
            return False, "storage round-trip returned unexpected content"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_queue_depth(queue_names: tuple[str, ...] = ("transactional", "default", "bulk"), max_depth: int = 10_000) -> HealthCheckResult:
    """
    Reports whether any monitored Celery queue has grown suspiciously
    large -- a signal that workers have stalled even if the broker
    itself (Redis) is reachable. Uses Redis LLEN directly on the
    Celery-managed list keys rather than the Celery inspect API, since
    LLEN is cheap and doesn't require a worker round-trip.
    """
    try:
        from core.caching.redis_client import get_redis_client

        client = get_redis_client()
        depths = {name: client.llen(name) for name in queue_names}
        overloaded = {name: depth for name, depth in depths.items() if depth > max_depth}
        if overloaded:
            return False, f"queue(s) over threshold ({max_depth}): {overloaded}"
        return True, f"ok ({depths})"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"
