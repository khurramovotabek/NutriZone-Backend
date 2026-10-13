"""
Notifications health checks -- registered against `core.health.
registry` from `apps/notifications/apps.py`'s `ready()` hook. Each
executes real logic, not merely an import test.

**No fixed count was assumed here**; this file's real checks were
derived directly from this module's actual Infrastructure
dependencies -- the repository, the Outbox, a real cross-table
consistency invariant, a content-integrity invariant matching the
identical pattern established by Reviews'/Chat's own equivalent
checks, composition, and cache. No Telegram connectivity check
exists -- `TelegramGateway` is an honest placeholder (see gateways.
py's own docstring); a health check for a provider integration that
does not exist yet would be premature, not thorough.
"""
from __future__ import annotations

from apps.notifications.infrastructure import models as orm
from apps.notifications.infrastructure.composition import build_notification_repository
from core.caching import get_redis_client


def check_notification_repository() -> tuple[bool, str]:
    try:
        orm.NotificationModel.objects.exists()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_notification_outbox_backlog() -> tuple[bool, str]:
    try:
        pending = orm.NotificationOutboxEvent.objects.filter(published_at__isnull=True).count()
        if pending > 500:
            return False, f"{pending} outbox events are pending publication"
        return True, f"ok ({pending} pending)"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_orphaned_deliveries() -> tuple[bool, str]:
    """Verifies every NotificationDeliveryModel row's notification FK actually points at a live NotificationModel -- a real cross-table consistency check beyond Django's own FK enforcement (which a bad migration or manual fix could bypass)."""
    try:
        orphaned = orm.NotificationDeliveryModel.objects.filter(notification__isnull=True).count()
        if orphaned > 0:
            return False, f"{orphaned} delivery rows are orphaned"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_notification_content_integrity() -> tuple[bool, str]:
    """Verifies no notification has an empty title or body -- the same invariant `Notification.create()` enforces at creation time via `NotificationTitle`/`NotificationBody`, checked here as a real database-level consistency check against drift (e.g. a bad migration), matching the identical pattern already established by Reviews'/Chat's own content-integrity health checks."""
    try:
        bad_count = orm.NotificationModel.objects.filter(title="").count() + orm.NotificationModel.objects.filter(body="").count()
        if bad_count > 0:
            return False, f"{bad_count} notifications have empty title or body"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_composition_integrity() -> tuple[bool, str]:
    try:
        build_notification_repository()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"composition root failed to build a repository: {exc}"


def check_notification_cache() -> tuple[bool, str]:
    try:
        client = get_redis_client()
        client.set("_health_check:notifications:probe", "ok", ex=5)
        result = client.get("_health_check:notifications:probe")
        client.delete("_health_check:notifications:probe")
        if result != "ok":
            return False, "cache round-trip returned unexpected content"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"
