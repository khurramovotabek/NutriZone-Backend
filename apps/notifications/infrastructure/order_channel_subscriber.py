"""
OrderCreated -> staff Orders Channel notification subscriber.

## Why OrderCreated, and why a channel (not a per-recipient Notification)

`OrderCreated` is the correct trigger for a staff-facing "a new order
needs fulfilling" alert -- it fires exactly once per order (Order
aggregate creation, confirmed by direct inspection of
`CreateOrderFromCart`), and staff need to know about an order the
moment it exists, not only once payment is later confirmed.

This is deliberately NOT built as a `Notification` aggregate the way
the customer-facing OrderConfirmed pipeline is: the Orders Channel is
one fixed staff destination (`settings.TELEGRAM_ORDERS_CHAT_ID`), not
a per-recipient User, so there's no `recipient_id` to attach a
`Notification` to. `OrderChannelNotificationRecord` provides the same
"exactly once" database guarantee directly.

## Race handling, matching telegram_dispatch_subscriber.py's own discipline

A real bug was found and fixed during this phase's own test-writing:
an earlier version created the "already sent" claim record before
calling the gateway, so a retryable (transient) failure permanently
consumed the claim -- the order could never actually be sent on a
later retry, since the second attempt would hit the database's own
unique constraint and report "already sent" despite never having
succeeded. Fixed to check "already sent" first (read-only), send, and
only record the claim after a real, successful send -- exactly
matching `telegram_dispatch_subscriber.py`'s own established pattern.
This leaves a small, accepted race window (two concurrent workers
could both pass the check and both send), identical to the same
trade-off already present in that subscriber.

## Configuration-gated, never silently sending to a wrong destination

If `TELEGRAM_ORDERS_CHAT_ID` is unset (the default), this subscriber
scans and skips every event without ever calling the gateway --
matching the same "blank config means the feature is inactive, not
mis-targeted" discipline as every other Telegram setting in this
project.
"""
from __future__ import annotations

import uuid as _uuid

from django.conf import settings
from django.db import IntegrityError

from apps.notifications.infrastructure import composition as notifications_composition
from apps.notifications.infrastructure import models as notifications_orm
from apps.notifications.infrastructure.gateways import TelegramGatewayNonRetryableError, TelegramGatewayRetryableError
from apps.notifications.infrastructure.order_channel_message import build_new_order_channel_message
from apps.ordering.infrastructure import composition as ordering_composition
from apps.ordering.infrastructure import models as ordering_orm

_BATCH_SIZE = 200


def sync_order_channel_notifications() -> dict:
    """Processes newly-created orders since the last run, sending exactly one Orders Channel message per order -- a no-op scan if TELEGRAM_ORDERS_CHAT_ID is unconfigured."""
    cursor, _created = notifications_orm.TelegramDispatchCursor.objects.get_or_create(id=2)  # id=2: a distinct singleton row from the customer-dispatch cursor (id=1)

    qs = ordering_orm.OrderingOutboxEvent.objects.filter(event_type="OrderCreated")
    if cursor.last_processed_created_at is not None:
        qs = qs.filter(created_at__gte=cursor.last_processed_created_at).exclude(
            created_at=cursor.last_processed_created_at, id=cursor.last_processed_id
        )
    events = list(qs.order_by("created_at", "id")[:_BATCH_SIZE])

    if not settings.TELEGRAM_ORDERS_CHAT_ID:
        if events:
            last = events[-1]
            cursor.last_processed_created_at = last.created_at
            cursor.last_processed_id = last.id
            cursor.save(update_fields=["last_processed_created_at", "last_processed_id", "updated_at"])
        return {"scanned": len(events), "sent": 0, "skipped": len(events), "reason": "TELEGRAM_ORDERS_CHAT_ID not configured"}

    sent = 0
    skipped = 0
    last_successful = None

    for event in events:
        try:
            order_id = event.payload["order_id"]
            outcome = _send_one(order_id)
            if outcome == "sent":
                sent += 1
            else:
                skipped += 1
            last_successful = event
        except TelegramGatewayRetryableError:
            break
        except Exception:  # noqa: BLE001 - one bad order must not corrupt the cursor or crash the whole batch
            last_successful = event

    if last_successful is not None:
        cursor.last_processed_created_at = last_successful.created_at
        cursor.last_processed_id = last_successful.id
        cursor.save(update_fields=["last_processed_created_at", "last_processed_id", "updated_at"])

    return {"scanned": len(events), "sent": sent, "skipped": skipped}


def _send_one(order_id) -> str:
    """Returns 'sent' or 'skipped'. Raises TelegramGatewayRetryableError for a transient failure (caller stops the batch to retry later)."""
    if notifications_orm.OrderChannelNotificationRecord.objects.filter(order_id=order_id).exists():
        return "skipped"  # already sent -- checked before any network call, so a retryable failure below never falsely "uses up" this order's one attempt

    order = ordering_composition.build_order_repository().get_by_id(_uuid.UUID(str(order_id)))
    if order is None:
        return "skipped"

    message = build_new_order_channel_message(order)
    gateway = notifications_composition.build_telegram_gateway()
    try:
        gateway.send_message(settings.TELEGRAM_ORDERS_CHAT_ID, "", message)
    except TelegramGatewayNonRetryableError:
        return "skipped"

    # The claim record is only created after a real, successful send --
    # matching telegram_dispatch_subscriber.py's own discipline. This
    # leaves a small window where two concurrent workers could both
    # pass the check above and both send (an accepted trade-off,
    # identical to the customer dispatch subscriber's own), but a
    # transient failure can never permanently block a real delivery,
    # which the earlier claim-first design incorrectly allowed
    # (confirmed by a real failing test before this fix).
    try:
        notifications_orm.OrderChannelNotificationRecord.objects.create(order_id=order.id)
    except IntegrityError:
        pass  # a concurrent worker already recorded it -- the message was still sent exactly once by this worker, which is the outcome that matters

    return "sent"
