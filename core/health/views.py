"""
Health check endpoints.

Two distinct checks, per standard container-orchestration convention:
  - /health/live  -> "is the process up" (no dependency checks -- used
                      by the orchestrator to decide whether to restart
                      the container)
  - /health/ready -> "is the process able to serve traffic" (checks
                      PostgreSQL, Redis, Celery, disk, storage, and
                      queue depth -- used by the load balancer/
                      orchestrator to decide whether to route traffic
                      to this instance)

These are infrastructure endpoints, not part of any bounded context's
API surface, and are intentionally excluded from the REST API
Blueprint's `/api/v1/` namespace and from OpenAPI documentation.

Individual check functions live in core/health/checks.py so they can
be reused (e.g. in a startup probe management command) independent of
this HTTP view layer.
"""
from __future__ import annotations

import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from core.health.checks import (
    check_celery,
    check_database,
    check_disk,
    check_queue_depth,
    check_redis,
    check_storage,
)
from core.health.registry import get_registered_checks

logger = logging.getLogger("nutrizone.app")


@require_GET
@csrf_exempt
def liveness(request):
    return JsonResponse({"status": "alive"})


# Checks required for the process to be considered "ready" (traffic is
# routed only if ALL of these pass).
_REQUIRED_CHECKS = {
    "database": check_database,
    "redis": check_redis,
}

# Checks that are informative but don't gate readiness on their own --
# e.g. a single slow/queued Celery worker shouldn't pull an otherwise
# healthy web instance out of rotation.
_ADVISORY_CHECKS = {
    "celery": check_celery,
    "disk": check_disk,
    "storage": check_storage,
    "queue_depth": check_queue_depth,
}


@require_GET
@csrf_exempt
def readiness(request):
    checks: dict[str, str] = {}
    healthy = True

    for name, check_fn in _REQUIRED_CHECKS.items():
        ok, detail = check_fn()
        checks[name] = detail
        if not ok:
            logger.warning("Readiness check failed (required): %s -> %s", name, detail)
            healthy = False

    for name, check_fn in _ADVISORY_CHECKS.items():
        ok, detail = check_fn()
        checks[name] = detail
        if not ok:
            logger.info("Readiness check failed (advisory, non-gating): %s -> %s", name, detail)

    for name, check_fn in get_registered_checks().items():
        try:
            ok, detail = check_fn()
        except Exception as exc:  # noqa: BLE001 - a module's check must never crash the platform health endpoint
            ok, detail = False, f"check raised: {exc}"
        checks[name] = detail
        if not ok:
            logger.info("Readiness check failed (advisory, module-registered): %s -> %s", name, detail)

    status_code = 200 if healthy else 503
    return JsonResponse({"status": "ready" if healthy else "not_ready", "checks": checks}, status=status_code)
