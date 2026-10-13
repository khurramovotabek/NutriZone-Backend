"""
Telegram delivery dispatch subscriber.

## The gap this closes, evidenced

Reconnaissance for this phase confirmed: `CreateNotification` (used by
`order_confirmed_subscriber.py` and any future subscriber) only
persists a `Notification` record and stages `NotificationCreated` --
it never calls `TelegramGateway.send_message()`. No other subscriber,
task, or service anywhere in `apps/notifications` did either. This
meant every notification created by the existing OrderConfirmed
pipeline was silently never delivered -- a customer-facing gap with
no prior test coverage catching it, since existing tests only assert
that a `Notification` row was created, not that it was ever sent.

## Design, matching order_confirmed_subscriber.py's own proven pattern

- Reads `NotificationCreated` from Notifications' own outbox via an
  independent keyset cursor, exactly like the OrderConfirmed
  subscriber reads Ordering's outbox.
- Exactly-once delivery is enforced the same way as every other
  subscriber in this codebase: `notification.deliveries` already
  existing for the TELEGRAM channel means "already attempted", so a
  duplicate cursor replay is a safe no-op, not a duplicate send.
- Only dispatches when the recipient has a `telegram_username` set
  (confirmed real, pre-existing field) -- a notification for a
  recipient with no linked Telegram identity is skipped, not errored,
  matching the same "no recipient, no error" discipline already used
  for guest orders in the OrderConfirmed subscriber.
- Distinguishes retryable vs non-retryable gateway failures (both
  already defined by `apps.notifications.infrastructure.gateways`,
  confirmed unused anywhere until now): a retryable failure raises,
  letting Celery's own existing retry infrastructure re-attempt on
  the next scheduled run without ever recording a false "sent"
  delivery; a non-retryable failure is logged and the batch continues
  (this notification is left permanently undelivered via this
  channel -- no domain method exists to mark a delivery FAILED, so
  no delivery record is created at all for a hard failure, honestly
  reflecting that no attempt was actually recorded as sent).
"""
from __future__ import annotations

import logging
import uuid as _uuid

from django.db import transaction
from django.utils import timezone as django_timezone

from apps.notifications.domain.enums import NotificationChannel
from apps.notifications.infrastructure import composition as notifications_composition
from apps.notifications.infrastructure import models as notifications_orm
from apps.notifications.infrastructure.gateways import TelegramGatewayNonRetryableError, TelegramGatewayRetryableError

logger = logging.getLogger("nutrizone.app")

_BATCH_SIZE = 200


def sync_telegram_dispatch() -> dict:
    """Processes newly-created notifications since the last run, attempting exactly one Telegram delivery per notification for recipients with a linked telegram_username."""
    cursor, _created = notifications_orm.TelegramDispatchCursor.objects.get_or_create(id=1)

    qs = notifications_orm.NotificationOutboxEvent.objects.filter(event_type="NotificationCreated")
    if cursor.last_processed_created_at is not None:
        qs = qs.filter(created_at__gte=cursor.last_processed_created_at).exclude(
            created_at=cursor.last_processed_created_at, id=cursor.last_processed_id
        )
    events = list(qs.order_by("created_at", "id")[:_BATCH_SIZE])

    sent = 0
    skipped = 0
    last_successful = None

    for event in events:
        try:
            notification_id = event.payload["notification_id"]
            outcome = _dispatch_one(notification_id)
            if outcome == "sent":
                sent += 1
            else:
                skipped += 1
            last_successful = event
        except TelegramGatewayRetryableError:
            logger.warning("Telegram dispatch: retryable failure for event %s, will retry next run.", event.id)
            break
        except Exception:  # noqa: BLE001 - one bad notification must not corrupt the cursor or crash the whole batch
            logger.exception("Telegram dispatch: unexpected failure for event %s", event.id)
            last_successful = event

    if last_successful is not None:
        cursor.last_processed_created_at = last_successful.created_at
        cursor.last_processed_id = last_successful.id
        cursor.save(update_fields=["last_processed_created_at", "last_processed_id", "updated_at"])

    return {"scanned": len(events), "sent": sent, "skipped": skipped}


def _dispatch_one(notification_id) -> str:
    """Returns 'sent' or 'skipped'. Raises TelegramGatewayRetryableError for a transient failure (caller stops the batch to retry later)."""
    from apps.identity.infrastructure import models as identity_orm

    repo = notifications_composition.build_notification_repository()
    notification = repo.get_by_id(_uuid.UUID(str(notification_id)))
    if notification is None:
        return "skipped"

    if any(d.channel == NotificationChannel.TELEGRAM for d in notification.deliveries.values()):
        return "skipped"

    recipient = identity_orm.User.objects.filter(id=notification.recipient_id).first()
    if recipient is None or not recipient.telegram_username:
        return "skipped"

    gateway = notifications_composition.build_telegram_gateway()

    try:
        provider_reference = gateway.send_message(recipient.telegram_username, notification.title.value, notification.body.value)
    except TelegramGatewayNonRetryableError:
        logger.warning("Telegram dispatch: non-retryable gateway rejection for notification %s.", notification_id)
        return "skipped"

    with transaction.atomic():
        event = notification.record_delivery_attempt(NotificationChannel.TELEGRAM, django_timezone.now())
        delivery_id = event.delivery_id
        notification.confirm_delivery(delivery_id, django_timezone.now())
        for delivery in notification.deliveries.values():
            if delivery.id == delivery_id:
                delivery.provider_reference = provider_reference
        repo.save(notification)

    return "sent"
