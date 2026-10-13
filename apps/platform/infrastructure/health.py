"""
Platform health checks -- registered against `core.health.registry`
from `apps/platform/apps.py`'s `ready()` hook. Each executes real
logic, not merely an import test. Matches every prior module's
identical health-check pattern (broad `except Exception` here is the
same, already-established health-check resilience pattern -- a health
check's entire purpose is reporting a dependency as unhealthy, never
crashing the health endpoint itself).
"""
from __future__ import annotations

from apps.platform.infrastructure import models as orm
from apps.platform.infrastructure.composition import build_feature_flag_repository
from core.flags.providers import RedisFlagProvider


def check_feature_flag_repository() -> tuple[bool, str]:
    try:
        orm.FeatureFlagModel.objects.exists()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_flag_redis_publisher() -> tuple[bool, str]:
    try:
        RedisFlagProvider().get_definition("__health_check__")
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_composition_integrity() -> tuple[bool, str]:
    try:
        build_feature_flag_repository()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"
