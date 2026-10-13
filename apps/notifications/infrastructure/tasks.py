"""
Notifications Celery tasks -- orchestration only, never business logic.

**Phase 15 update to a previously-disclosed limitation**: the note
below ("no task here mutates a Notification... Zero Application
Services exist for Notifications to call") was accurate when written,
but is no longer -- `sync_telegram_dispatch` now calls the
`Notification` aggregate's own existing `record_delivery_attempt`/
`confirm_delivery` domain methods (not a new Application Service,
reusing what already existed but was never invoked by anything).
`flag_undelivered_notifications` below remains genuinely real and
useful without a mutating service: it only reads and reports.
"""
from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.utils import timezone as django_timezone

from apps.notifications.infrastructure import models as orm
from apps.notifications.infrastructure.event_handlers import handle_notification_event, invalidate_notification_cache_group
from core.metrics import default_collector
from core.outbox import OutboxRelay

DEFAULT_UNDELIVERED_THRESHOLD = timedelta(hours=1)


@shared_task(queue="transactional", name="notifications.sync_order_confirmed_notifications")
def sync_order_confirmed_notifications() -> dict:
    """Phase 02G's OrderConfirmed -> customer notification sync -- see order_confirmed_subscriber.py's own module docstring for the full design. Matches every prior phase's own subscriber-task pattern (Phase 02C/02D/02F)."""
    from apps.notifications.infrastructure.order_confirmed_subscriber import sync_order_confirmed_notifications as _sync
    return _sync()


@shared_task(queue="transactional", name="notifications.sync_telegram_dispatch", autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def sync_telegram_dispatch() -> dict:
    """Phase 15: dispatches newly-created notifications to their recipient's linked Telegram identity -- see telegram_dispatch_subscriber.py's own module docstring for the full design and the real gap it closes. autoretry_for handles a retryable gateway failure by re-running this whole task (the cursor position is only advanced past a successfully-processed or non-retryable event, so a retry safely resumes from where the retryable failure occurred)."""
    from apps.notifications.infrastructure.telegram_dispatch_subscriber import sync_telegram_dispatch as _sync
    return _sync()


@shared_task(queue="transactional", name="telegram_bot.sync_orders_channel", autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def sync_orders_channel() -> dict:
    """Phase 15E: posts newly-created orders to the manager-facing Telegram Orders Channel -- see orders_channel_subscriber.py's own module docstring for the full design."""
    from apps.telegram_bot.infrastructure.orders_channel_subscriber import sync_orders_channel as _sync
    return _sync()


@shared_task(queue="transactional", name="telegram_bot.sync_pos_sales_channel", autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def sync_pos_sales_channel() -> dict:
    """Posts completed/refunded POS Terminal sales to the same Telegram Orders Channel -- see pos_sales_channel_subscriber.py."""
    from apps.telegram_bot.infrastructure.pos_sales_channel_subscriber import sync_pos_sales_channel as _sync
    return _sync()


@shared_task(queue="transactional", name="telegram_bot.sync_after_sales_channel", autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def sync_after_sales_channel() -> dict:
    """Announces customer return / cancellation requests and self-cancellations in the Orders Channel -- see after_sales_channel_subscriber.py."""
    from apps.telegram_bot.infrastructure.after_sales_channel_subscriber import sync_after_sales_channel as _sync
    return _sync()


def sync_order_channel_notifications() -> dict:
    """
    DEPRECATED -- no longer registered as a Celery task.

    This was a second, independent subscriber to the same
    OrderCreated event that telegram_bot.sync_orders_channel already
    handles -- a real duplication risk (if both were ever scheduled,
    every order would post twice to the same staff channel). Kept as
    a plain function (not deleted) only so its own existing test
    suite still documents its historical behavior; it is not called
    from anywhere in production code. telegram_bot.sync_orders_channel
    is the single, current Orders Channel path -- it additionally
    includes the real customer name/phone, delivery address, GPS
    location, product name, and product image this function never had.
    """
    from apps.notifications.infrastructure.order_channel_subscriber import sync_order_channel_notifications as _sync
    return _sync()


@shared_task(queue="scheduled", name="notifications.flag_undelivered_notifications")
def flag_undelivered_notifications() -> int:
    """Read-only visibility sweep -- reports (via metric) how many notifications have no delivery attempt recorded at all, longer than the threshold after creation. Never mutates a Notification; a future Application Service could act on this count once one exists."""
    cutoff = django_timezone.now() - DEFAULT_UNDELIVERED_THRESHOLD
    count = orm.NotificationModel.objects.filter(created_at__lte=cutoff, deliveries__isnull=True).count()
    default_collector.counter("notifications_undelivered_count", count)
    return count


@shared_task(queue="scheduled", name="notifications.rebuild_statistics")
def rebuild_notification_statistics() -> str:
    invalidate_notification_cache_group("notification_statistics")
    return "ok"


@shared_task(queue="transactional", name="notifications.relay_outbox_events")
def relay_outbox_events() -> dict:
    """Celery Beat-scheduled Outbox relay for the `notifications` schema -- matches every prior module's identical relay task."""

    def _publish(event) -> bool:
        try:
            handle_notification_event(event.event_type, event.payload)
            return True
        except Exception:  # noqa: BLE001
            return False

    relay = OutboxRelay(orm.NotificationOutboxEvent, max_attempts=5, batch_size=100)
    return relay.relay_pending(publish_fn=_publish)


@shared_task(queue="transactional", name="notifications.deliver_telegram_notification", autoretry_for=(ConnectionError, TimeoutError), retry_backoff=True, max_retries=3)
def deliver_telegram_notification(notification_id: str) -> bool:
    """Sends one inbox notification to the customer's Telegram (see notify.send_telegram)."""
    from apps.notifications.infrastructure.notify import send_telegram

    return send_telegram(notification_id)


@shared_task(queue="bulk", name="notifications.run_broadcast", soft_time_limit=3600)
def run_notification_broadcast(broadcast_id: str) -> dict:
    """Dashboard → Bildirishnoma yuborish: fans one broadcast out to its whole audience."""
    from apps.notifications.infrastructure.notify import run_broadcast

    return run_broadcast(broadcast_id)
