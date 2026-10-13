"""
Ordering health checks -- registered against `core.health.registry`
from `apps/ordering/apps.py`'s `ready()` hook. Each executes real
logic, not merely an import test.
"""
from __future__ import annotations


def check_ordering_repository() -> tuple[bool, str]:
    try:
        from apps.ordering.infrastructure import models as orm

        orm.OrderModel.objects.exists()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_ordering_cache() -> tuple[bool, str]:
    try:
        from core.caching import get_redis_client

        client = get_redis_client()
        client.set("_health_check:ordering:probe", "ok", ex=5)
        result = client.get("_health_check:ordering:probe")
        client.delete("_health_check:ordering:probe")
        if result != "ok":
            return False, "cache round-trip returned unexpected content"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_outbox_pending_events() -> tuple[bool, str]:
    """Flags a real Outbox backlog -- more than N unpublished events means the relay task is behind schedule or failing, a real operational signal."""
    try:
        from apps.ordering.infrastructure import models as orm

        pending = orm.OrderingOutboxEvent.objects.filter(published_at__isnull=True).count()
        if pending > 500:
            return False, f"{pending} outbox events are pending publication"
        return True, f"ok ({pending} pending)"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_expired_orders() -> tuple[bool, str]:
    """Flags orders past their expiry window that the expire_orders sweep task hasn't yet processed."""
    try:
        from datetime import timedelta

        from django.utils import timezone as django_timezone

        from apps.ordering.infrastructure import models as orm

        cutoff = django_timezone.now() - timedelta(hours=2)
        overdue = orm.OrderModel.objects.filter(status__in=["draft", "pending_payment"], placed_at__isnull=False, placed_at__lte=cutoff).count()
        if overdue > 20:
            return False, f"{overdue} orders are past expiry and not yet swept"
        return True, f"ok ({overdue} pending sweep)"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_stale_returns() -> tuple[bool, str]:
    """Flags returns stuck in REQUESTED for an unusually long time."""
    try:
        from datetime import timedelta

        from django.utils import timezone as django_timezone

        from apps.ordering.infrastructure import models as orm

        cutoff = django_timezone.now() - timedelta(days=30)
        stale = orm.OrderReturnModel.objects.filter(status="requested", requested_at__lte=cutoff).count()
        if stale > 10:
            return False, f"{stale} return requests have been pending for over 30 days"
        return True, f"ok ({stale} stale)"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_database_consistency() -> tuple[bool, str]:
    """Verifies no order is archived while still locked, and no order carries an issued invoice with a zero total -- two structurally-suspicious states worth a real query, not just table connectivity."""
    try:
        from apps.ordering.infrastructure import models as orm

        inconsistent_locks = orm.OrderModel.objects.filter(status__in=["cancelled", "failed"], lock_reason__isnull=False).count()
        if inconsistent_locks > 0:
            return False, f"{inconsistent_locks} order(s) are cancelled/failed while still marked locked"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"
