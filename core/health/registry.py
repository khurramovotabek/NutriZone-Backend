"""
Module health-check registry.

Lets a business module contribute its own advisory health checks
(e.g. Identity's repository/OTP-provider/token-issuer checks) to
`/health/ready` without `core/health/` ever importing a business app
directly -- dependency direction stays core -> (never) apps, matching
every other cross-cutting registry in `core/` (FeatureFlags, the Event
Catalogue). A module registers via this at Django app-ready time.
"""
from __future__ import annotations

from typing import Callable

HealthCheckFn = Callable[[], tuple[bool, str]]

_registered_checks: dict[str, HealthCheckFn] = {}


def register_module_check(name: str, check_fn: HealthCheckFn) -> None:
    _registered_checks[name] = check_fn


def get_registered_checks() -> dict[str, HealthCheckFn]:
    return dict(_registered_checks)
