"""
Phase 02G's OrderConfirmed -> customer notification subscriber.

## Why OrderConfirmed, evidenced not assumed

Reconnaissance (this phase's own Step 5/6) confirmed `Order.confirm()`
is reached exactly when a payment genuinely succeeds (Phase 02E's own
`UpdatePaymentStatus` triggers it on `CAPTURED`), making
`OrderConfirmed` the single clearest "the customer should be told
something just happened" business event in this repository: it is
customer-facing, happens exactly once per order (confirmed by
`Order.confirm()`'s own precondition -- `PENDING_PAYMENT` only,
transitioning away from it, so the event cannot fire twice for the
same order from the domain's own side), and both the event and its
consumer (Ordering's own outbox) already exist and are proven working
end-to-end (Phase 02E's own full-lifecycle test).

## Design, matching the proven pattern from Phases 02C/02D/02F

- Reads Ordering's own outbox table read-only, via an independent
  keyset cursor (`OrderConfirmedNotificationCursor`), mirroring --
  not reusing -- Audit's own private `SubscriberCursor`, per this
  phase's own explicit instruction not to touch Audit's certified
  infrastructure.
- `OrderConfirmedNotificationRecord.order_id` is a real, unique
  database column -- the same "let a real constraint decide the
  race" discipline already proven correct in three prior phases.
  Created before `CreateNotification` is called, inside the same
  transaction, so a losing concurrent/duplicate delivery is treated
  as "already notified", never creating a second notification.
- The notification's `recipient_id` is the order's own
  `customer_id`, re-fetched from the real `Order` aggregate (not
  trusted from the event payload, which only carries `order_id`) --
  matching every prior subscriber's own "re-fetch authoritative
  state, don't trust the event payload" discipline.
- A guest order (`customer_id is None`) is skipped, not errored --
  there is no recipient to notify, matching the identical, already-
  established pattern from Phase 02C's own reward subscriber.
"""
from __future__ import annotations

import uuid as _uuid

from django.db import IntegrityError, transaction

from apps.notifications.domain.enums import NotificationPriority, NotificationType
from apps.notifications.infrastructure import composition as notifications_composition
from apps.notifications.infrastructure import models as notifications_orm
from apps.ordering.infrastructure import composition as ordering_composition
from apps.ordering.infrastructure import models as ordering_orm

_BATCH_SIZE = 200


def sync_order_confirmed_notifications() -> dict:
    """Processes newly-confirmed orders since the last run, creating exactly one customer notification per order. Safe to run repeatedly and concurrently with itself -- the database uniqueness constraint on OrderConfirmedNotificationRecord.order_id is what actually guarantees this."""
    cursor, _created = notifications_orm.OrderConfirmedNotificationCursor.objects.get_or_create(id=1)

    qs = ordering_orm.OrderingOutboxEvent.objects.filter(event_type="OrderConfirmed")
    if cursor.last_processed_created_at is not None:
        qs = qs.filter(created_at__gte=cursor.last_processed_created_at).exclude(
            created_at=cursor.last_processed_created_at, id=cursor.last_processed_id
        )
    events = list(qs.order_by("created_at", "id")[:_BATCH_SIZE])

    notified = 0
    skipped = 0
    last_successful = None
    failed = False

    for event in events:
        try:
            order_id = event.payload["order_id"]
            outcome = _process_one_order_confirmation(order_id)
            if outcome == "notified":
                notified += 1
            else:
                skipped += 1
            last_successful = event
        except Exception:  # noqa: BLE001 - a failure notifying for one order must not corrupt the cursor or crash the whole batch; Celery's own retry picks this event back up next run
            failed = True
            break

    if last_successful is not None:
        cursor.last_processed_created_at = last_successful.created_at
        cursor.last_processed_id = last_successful.id
        cursor.save(update_fields=["last_processed_created_at", "last_processed_id", "updated_at"])

    return {"scanned": len(events), "notified": notified, "skipped": skipped, "failed": failed}


def _process_one_order_confirmation(order_id) -> str:
    """Returns 'notified', 'skipped', or 'already_notified' (the last only reachable under a genuine concurrent-delivery race)."""
    order = ordering_composition.build_order_repository().get_by_id(_uuid.UUID(str(order_id)))
    if order is None or order.customer_id is None:
        return "skipped"  # a genuinely deleted/guest order has no recipient to notify -- not an error

    with transaction.atomic():
        try:
            record = notifications_orm.OrderConfirmedNotificationRecord.objects.create(order_id=order.id, notification_id=_uuid.uuid4())
        except IntegrityError:
            # A concurrent/duplicate OrderConfirmed delivery already
            # won this order's notification -- the exactly-once
            # guarantee, enforced by the database.
            return "already_notified"

        notification = notifications_composition.build_create_notification().execute(
            recipient_id=order.customer_id, notification_type=NotificationType.TRANSACTIONAL, priority=NotificationPriority.NORMAL,
            title="Order confirmed", body=f"Your order {order.order_number.value} has been confirmed and is being prepared.",
            template_key="order_confirmed",
        )
        record.notification_id = notification.id
        record.save(update_fields=["notification_id"])
        return "notified"
