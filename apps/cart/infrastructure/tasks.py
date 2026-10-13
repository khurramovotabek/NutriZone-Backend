"""
Cart Celery tasks -- orchestration only. Every task loads data, calls
a real Application Service for the actual decision, and persists/
reports the result -- never business logic itself.
"""
from __future__ import annotations

from celery import shared_task
from django.utils import timezone as django_timezone

from apps.cart.infrastructure import models as orm
from apps.cart.infrastructure.event_handlers import handle_cart_event
from core.outbox import OutboxRelay


@shared_task(queue="scheduled", name="cart.expire_carts")
def expire_carts() -> int:
    """Sweeps every ACTIVE/SAVED cart past its expires_at and calls the real `ExpireCart` Application Service for each -- the task orchestrates the sweep, the service (via composition.py) makes the actual domain decision."""
    from apps.cart.infrastructure.composition import build_expire_cart
    from apps.cart.infrastructure.repositories import DjangoCartRepository

    now = django_timezone.now()
    repo = DjangoCartRepository()
    expiring = repo.list_expiring_before(now)
    count = 0
    for cart in expiring:
        try:
            build_expire_cart().execute(cart.id)
            count += 1
        except Exception:  # noqa: BLE001 - one failure must not abort the sweep for the rest
            continue
    return count


@shared_task(queue="scheduled", name="cart.cleanup_abandoned_carts")
def cleanup_abandoned_carts(inactive_for_days: int = 3) -> int:
    """Archives carts that have seen no activity in N days -- calls the real `ArchiveCart` Application Service per cart, never sets `status` directly."""
    import uuid

    from apps.cart.infrastructure.composition import build_archive_cart
    from apps.cart.infrastructure.selectors import AbandonedCartSelector

    abandoned = AbandonedCartSelector().list_abandoned(inactive_for_days=inactive_for_days)
    count = 0
    for entry in abandoned:
        try:
            build_archive_cart().execute(uuid.UUID(entry["id"]))
            count += 1
        except Exception:  # noqa: BLE001
            continue
    return count


@shared_task(queue="scheduled", name="cart.cleanup_expired_reservations")
def cleanup_expired_reservations() -> int:
    """
    Detaches reservation references whose `expires_at` has passed --
    Cart does not own reservation lifecycle (Inventory does), so this
    only clears Cart's own stale reference via the real
    `DetachReservation` Application Service; it never talks to
    Inventory directly.
    """
    from apps.cart.infrastructure.composition import build_detach_reservation

    now = django_timezone.now()
    stale = orm.AttachedReservationModel.objects.filter(expires_at__isnull=False, expires_at__lte=now).select_related("item")
    count = 0
    for reservation_row in stale:
        try:
            build_detach_reservation().execute(reservation_row.item.cart_id, reservation_row.item_id)
            count += 1
        except Exception:  # noqa: BLE001
            continue
    return count


@shared_task(queue="scheduled", name="cart.rebuild_statistics")
def rebuild_statistics() -> str:
    from apps.cart.infrastructure.event_handlers import invalidate_cart_cache_group

    invalidate_cart_cache_group("cart_list")
    return "ok"


@shared_task(queue="transactional", name="cart.relay_outbox_events")
def relay_outbox_events() -> dict:
    """Celery Beat-scheduled Outbox relay for the `cart` schema -- matches every prior module's identical relay task."""

    def _publish(event) -> bool:
        try:
            handle_cart_event(event.event_type, event.payload)
            return True
        except Exception:  # noqa: BLE001
            return False

    relay = OutboxRelay(orm.CartOutboxEvent, max_attempts=5, batch_size=100)
    return relay.relay_pending(publish_fn=_publish)


GUEST_CART_TTL_DAYS = 30


def stale_guest_carts(older_than_days: int = GUEST_CART_TTL_DAYS):
    """
    Guest carts (no customer) with no product left in them and no activity for N days. Signed-in customers' carts
    are never touched (one cart per customer is reused), nor any cart an order was placed from.
    """
    from datetime import timedelta

    from django.db.models import Exists, OuterRef

    from apps.ordering.infrastructure.models import OrderModel

    cutoff = django_timezone.now() - timedelta(days=older_than_days)
    has_items = Exists(orm.CartItemModel.objects.filter(cart=OuterRef("pk"), status="active"))
    ordered = Exists(OrderModel.objects.filter(cart_id=OuterRef("pk")))
    return orm.CartModel.objects.filter(customer_id__isnull=True, updated_at__lt=cutoff).exclude(has_items).exclude(ordered)


@shared_task(queue="default", name="cart.purge_empty_guest_carts")  # "scheduled" has no worker; default does
def purge_empty_guest_carts(older_than_days: int = GUEST_CART_TTL_DAYS, batch_size: int = 1000) -> int:
    """
    Weekly housekeeping: deletes empty guest carts idle for `older_than_days` (with their removed items, history
    and snapshots). A visitor coming back after that simply gets a new cart. Runs in batches.
    """
    import logging

    deleted = 0
    while True:
        ids = list(stale_guest_carts(older_than_days).values_list("id", flat=True)[:batch_size])
        if not ids:
            break
        orm.CartModel.objects.filter(id__in=ids).delete()
        deleted += len(ids)
    logging.getLogger("nutrizone.app").info("cart.purge_empty_guest_carts: %s deleted", deleted)
    return deleted
