"""
Notifications aggregates.

**Two aggregate roots, deliberately, not one** -- `Notification` and
`NotificationPreference`. Reasoned explicitly during this phase's own
Step 1, not chosen by convenience: a `Notification` (one message to
one recipient) and a `NotificationPreference` (one per user,
configuration state) have fundamentally different cardinality,
consistency requirements, and mutation frequency -- a user has many
notifications created frequently, but exactly one preference record
that changes rarely. Linked only by `user_id: uuid.UUID`, the same
plain cross-aggregate reference convention used throughout this
build. Neither aggregate reaches into the other's state; the
Application layer will coordinate them in a future phase (e.g.
checking `NotificationPreference.is_enabled()` before calling
`Notification.record_delivery_attempt()`), matching the identical
cross-aggregate boundary already established by Chat's own
`Conversation`/`Message` split.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from apps.notifications.domain.entities import NotificationDelivery
from apps.notifications.domain.enums import DeliveryStatus, NotificationChannel, NotificationPriority, NotificationStatus, NotificationType
from apps.notifications.domain.events import (
    NotificationCancelled, NotificationChannelDisabled, NotificationChannelEnabled, NotificationCreated,
    NotificationDelivered, NotificationDeliveryFailed, NotificationDeliverySent, NotificationRead, NotificationSeen,
)
from apps.notifications.domain.exceptions import (
    DeliveryNotFound, InvalidDeliveryTransition, InvalidNotificationTransition, NotificationAlreadyCancelled,
    NotificationAlreadyDelivered,
)
from apps.notifications.domain.value_objects import NotificationBody, NotificationTitle


@dataclass(slots=True)
class Notification:
    """Aggregate root -- one message to one recipient. Owns `NotificationDelivery` entities directly (small, bounded cardinality -- see entities.py's own module docstring for the full contrast with Chat's Message)."""

    id: uuid.UUID
    recipient_id: uuid.UUID
    notification_type: NotificationType
    priority: NotificationPriority
    title: NotificationTitle
    body: NotificationBody
    template_key: str | None = None
    status: NotificationStatus = NotificationStatus.UNSEEN
    deliveries: dict[uuid.UUID, NotificationDelivery] = field(default_factory=dict)
    created_at: datetime | None = None
    seen_at: datetime | None = None
    read_at: datetime | None = None

    # --- Creation ----------------------------------------------------------

    @staticmethod
    def create(notification_id: uuid.UUID, recipient_id: uuid.UUID, notification_type: NotificationType, priority: NotificationPriority, title: NotificationTitle, body: NotificationBody, at: datetime, template_key: str | None = None) -> tuple["Notification", NotificationCreated]:
        notification = Notification(id=notification_id, recipient_id=recipient_id, notification_type=notification_type, priority=priority, title=title, body=body, template_key=template_key, created_at=at)
        event = NotificationCreated(notification_id=notification.id, recipient_id=recipient_id, notification_type=notification_type.value)
        return notification, event

    # --- Delivery ------------------------------------------------------------

    def record_delivery_attempt(self, channel: NotificationChannel, at: datetime) -> NotificationDeliverySent:
        """
        Records the FACT that a delivery attempt was made through a
        channel -- does not itself send anything (Domain never calls
        an external provider). Does not check `NotificationPreference`
        -- that cross-aggregate check belongs to the Application
        layer, which will have already loaded both aggregates before
        ever calling this method, per this module's own docstring.
        """
        delivery = NotificationDelivery(id=uuid.uuid4(), channel=channel, status=DeliveryStatus.SENT, attempted_at=at)
        self.deliveries[delivery.id] = delivery
        return NotificationDeliverySent(notification_id=self.id, delivery_id=delivery.id, channel=channel.value)

    def _get_delivery_or_raise(self, delivery_id: uuid.UUID) -> NotificationDelivery:
        delivery = self.deliveries.get(delivery_id)
        if delivery is None:
            raise DeliveryNotFound(f"No delivery '{delivery_id}' exists on this notification.")
        return delivery

    def confirm_delivery(self, delivery_id: uuid.UUID, at: datetime) -> NotificationDelivered:
        delivery = self._get_delivery_or_raise(delivery_id)
        if delivery.status != DeliveryStatus.SENT:
            raise InvalidDeliveryTransition(f"Cannot confirm a delivery in status {delivery.status.value}; only SENT deliveries can be confirmed.")
        delivery.status = DeliveryStatus.DELIVERED
        delivery.delivered_at = at
        return NotificationDelivered(notification_id=self.id, delivery_id=delivery_id)

    def mark_delivery_failed(self, delivery_id: uuid.UUID, reason: str | None, at: datetime) -> NotificationDeliveryFailed:
        delivery = self._get_delivery_or_raise(delivery_id)
        if delivery.status != DeliveryStatus.SENT:
            raise InvalidDeliveryTransition(f"Cannot fail a delivery in status {delivery.status.value}; only SENT deliveries can be marked failed.")
        delivery.status = DeliveryStatus.FAILED
        delivery.failed_at = at
        delivery.failure_reason = reason
        return NotificationDeliveryFailed(notification_id=self.id, delivery_id=delivery_id, reason=reason)

    # --- Recipient-facing lifecycle ------------------------------------------

    def mark_seen(self, at: datetime) -> NotificationSeen | None:
        """A legitimate no-op if already SEEN or READ -- matching the established 'a repeated signal is a safe no-op' precedent (e.g. Chat's own `Message.mark_delivered`)."""
        if self.status in (NotificationStatus.SEEN, NotificationStatus.READ):
            return None
        self.status = NotificationStatus.SEEN
        self.seen_at = at
        return NotificationSeen(notification_id=self.id)

    def mark_read(self, at: datetime) -> NotificationRead | None:
        """Reachable directly from UNSEEN -- opening a notification without first passing through a distinct 'seen' UI event is realistic and does not need to be forbidden."""
        if self.status == NotificationStatus.READ:
            return None
        self.status = NotificationStatus.READ
        self.read_at = at
        return NotificationRead(notification_id=self.id)

    def cancel(self) -> NotificationCancelled:
        if self.status == NotificationStatus.CANCELLED:
            raise NotificationAlreadyCancelled("This notification has already been cancelled.")
        if self.status == NotificationStatus.READ:
            raise InvalidNotificationTransition("Cannot cancel a notification that has already been read.")
        if any(d.status == DeliveryStatus.DELIVERED for d in self.deliveries.values()):
            raise NotificationAlreadyDelivered("Cannot cancel a notification that has already been delivered through at least one channel.")
        self.status = NotificationStatus.CANCELLED
        return NotificationCancelled(notification_id=self.id)


@dataclass(slots=True)
class NotificationPreference:
    """
    Aggregate root -- one per user. An opt-OUT model: every
    (channel, notification_type) combination is enabled by default;
    `disabled_combinations` records only the explicit exceptions,
    avoiding a combinatorial row-per-combination default state that
    would need to be created and kept in sync for every user.
    """

    id: uuid.UUID
    user_id: uuid.UUID
    disabled_combinations: set[tuple[NotificationChannel, NotificationType]] = field(default_factory=set)

    @staticmethod
    def create(preference_id: uuid.UUID, user_id: uuid.UUID) -> "NotificationPreference":
        """No factory event is emitted -- creating a preference record with all-default (fully enabled) settings is not itself a meaningful business fact worth a Domain Event; `NotificationChannelEnabled`/`NotificationChannelDisabled` are emitted only by actual configuration changes."""
        return NotificationPreference(id=preference_id, user_id=user_id)

    def is_enabled(self, channel: NotificationChannel, notification_type: NotificationType) -> bool:
        return (channel, notification_type) not in self.disabled_combinations

    def disable(self, channel: NotificationChannel, notification_type: NotificationType) -> NotificationChannelDisabled | None:
        """A no-op (returns None, emits nothing) if already disabled -- an idempotent configuration change, not an error."""
        key = (channel, notification_type)
        if key in self.disabled_combinations:
            return None
        self.disabled_combinations.add(key)
        return NotificationChannelDisabled(preference_id=self.id, user_id=self.user_id, channel=channel.value, notification_type=notification_type.value)

    def enable(self, channel: NotificationChannel, notification_type: NotificationType) -> NotificationChannelEnabled | None:
        key = (channel, notification_type)
        if key not in self.disabled_combinations:
            return None
        self.disabled_combinations.discard(key)
        return NotificationChannelEnabled(preference_id=self.id, user_id=self.user_id, channel=channel.value, notification_type=notification_type.value)
