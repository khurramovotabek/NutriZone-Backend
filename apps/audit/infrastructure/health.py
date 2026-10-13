"""Audit health checks -- matches every prior module's identical pattern (broad `except Exception` here is the same, already-established health-check resilience convention)."""
from __future__ import annotations

from apps.audit.infrastructure import models as orm


def check_activity_timeline_table() -> tuple[bool, str]:
    try:
        orm.ActivityTimelineEntry.objects.exists()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_subscriber_cursor_table() -> tuple[bool, str]:
    try:
        orm.SubscriberCursor.objects.exists()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"
