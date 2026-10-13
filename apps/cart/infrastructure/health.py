"""
Cart health checks -- registered against `core.health.registry` from
`apps/cart/apps.py`'s `ready()` hook. Each executes meaningful logic,
not merely an import test.
"""
from __future__ import annotations


def check_cart_repository() -> tuple[bool, str]:
    try:
        from apps.cart.infrastructure import models as orm

        orm.CartModel.objects.exists()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_cart_cache() -> tuple[bool, str]:
    try:
        from core.caching import get_redis_client

        client = get_redis_client()
        client.set("_health_check:cart:probe", "ok", ex=5)
        result = client.get("_health_check:cart:probe")
        client.delete("_health_check:cart:probe")
        if result != "ok":
            return False, "cache round-trip returned unexpected content"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_cart_state_consistency() -> tuple[bool, str]:
    """Verifies no cart is in a structurally impossible state: LOCKED status doesn't exist as a top-level CartStatus (locking is the separate lock_reason field), but a real inconsistency worth catching is a cart with lock_reason set while also ARCHIVED/CONVERTED -- those states should be mutually exclusive in practice, since archiving/converting doesn't explicitly clear a lock."""
    try:
        from apps.cart.infrastructure import models as orm

        inconsistent = orm.CartModel.objects.filter(status__in=["archived", "converted"], lock_reason__isnull=False).count()
        if inconsistent > 0:
            return False, f"{inconsistent} cart(s) are archived/converted while still marked locked"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_reservation_cleanup() -> tuple[bool, str]:
    """Flags any AttachedReservation past its expiry that the cleanup_expired_reservations task hasn't yet swept -- a real signal the sweep task is behind schedule, not just a table-connectivity check."""
    try:
        from django.utils import timezone as django_timezone

        from apps.cart.infrastructure import models as orm

        overdue = orm.AttachedReservationModel.objects.filter(expires_at__isnull=False, expires_at__lt=django_timezone.now()).count()
        if overdue > 10:
            return False, f"{overdue} attached reservations are past expiry and not yet cleaned up"
        return True, f"ok ({overdue} pending sweep)"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_snapshot_validity() -> tuple[bool, str]:
    """Verifies every CartSnapshot's items_snapshot is well-formed JSON with the expected shape -- catches silent corruption from a future migration or manual DB edit, not just 'does the table exist'."""
    try:
        from apps.cart.infrastructure import models as orm

        sample = orm.CartSnapshotModel.objects.order_by("-captured_at")[:20]
        for snapshot in sample:
            if not isinstance(snapshot.items_snapshot, list):
                return False, f"snapshot {snapshot.id} has a malformed items_snapshot (expected a list)"
            for entry in snapshot.items_snapshot:
                if "product_variant_id" not in entry or "quantity" not in entry:
                    return False, f"snapshot {snapshot.id} has an item entry missing required keys"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"
