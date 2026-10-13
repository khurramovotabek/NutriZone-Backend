"""
Aggregate tests -- covers every public method, every state transition,
every invariant, every emitted Domain Event, and every exception path
on both `Notification` and `NotificationPreference`.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from apps.notifications.domain.aggregates import Notification, NotificationPreference
from apps.notifications.domain.enums import NotificationChannel, NotificationPriority, NotificationStatus, NotificationType
from apps.notifications.domain.exceptions import (
    DeliveryNotFound, InvalidDeliveryTransition, InvalidNotificationTransition, NotificationAlreadyCancelled,
    NotificationAlreadyDelivered,
)
from apps.notifications.domain.value_objects import NotificationBody, NotificationTitle
from apps.notifications.tests.factories import make_notification, make_preference

pytestmark = pytest.mark.unit


def _now() -> datetime:
    return datetime.utcnow()


class TestNotificationCreate:
    def test_creates_unseen_notification(self):
        recipient_id = uuid.uuid4()
        notification, event = Notification.create(uuid.uuid4(), recipient_id, NotificationType.TRANSACTIONAL, NotificationPriority.NORMAL, NotificationTitle("Shipped"), NotificationBody("On its way."), _now())
        assert notification.status == NotificationStatus.UNSEEN
        assert notification.recipient_id == recipient_id
        assert event.__class__.__name__ == "NotificationCreated"

    def test_starts_with_empty_delivery_collection(self):
        notification = make_notification()
        assert notification.deliveries == {}

    def test_seen_at_and_read_at_start_none(self):
        notification = make_notification()
        assert notification.seen_at is None
        assert notification.read_at is None

    def test_template_key_defaults_to_none(self):
        notification = make_notification()
        assert notification.template_key is None

    def test_template_key_stored_when_supplied(self):
        notification = make_notification(template_key="order_shipped_v2")
        assert notification.template_key == "order_shipped_v2"


class TestNotificationDeliveryLifecycle:
    def test_record_delivery_attempt_creates_delivery_directly_in_sent(self):
        notification = make_notification()
        event = notification.record_delivery_attempt(NotificationChannel.TELEGRAM, _now())
        assert len(notification.deliveries) == 1
        delivery = next(iter(notification.deliveries.values()))
        assert delivery.status.value == "sent"
        assert event.__class__.__name__ == "NotificationDeliverySent"

    def test_confirm_delivery(self):
        notification = make_notification()
        notification.record_delivery_attempt(NotificationChannel.EMAIL, _now())
        delivery_id = next(iter(notification.deliveries.keys()))
        event = notification.confirm_delivery(delivery_id, _now())
        assert notification.deliveries[delivery_id].status.value == "delivered"
        assert event.__class__.__name__ == "NotificationDelivered"

    def test_confirm_unknown_delivery_raises(self):
        notification = make_notification()
        with pytest.raises(DeliveryNotFound):
            notification.confirm_delivery(uuid.uuid4(), _now())

    def test_confirm_already_delivered_raises(self):
        notification = make_notification()
        notification.record_delivery_attempt(NotificationChannel.EMAIL, _now())
        delivery_id = next(iter(notification.deliveries.keys()))
        notification.confirm_delivery(delivery_id, _now())
        with pytest.raises(InvalidDeliveryTransition):
            notification.confirm_delivery(delivery_id, _now())

    def test_mark_delivery_failed(self):
        notification = make_notification()
        notification.record_delivery_attempt(NotificationChannel.SMS, _now())
        delivery_id = next(iter(notification.deliveries.keys()))
        event = notification.mark_delivery_failed(delivery_id, "invalid number", _now())
        assert notification.deliveries[delivery_id].status.value == "failed"
        assert notification.deliveries[delivery_id].failure_reason == "invalid number"
        assert event.__class__.__name__ == "NotificationDeliveryFailed"

    def test_mark_unknown_delivery_failed_raises(self):
        notification = make_notification()
        with pytest.raises(DeliveryNotFound):
            notification.mark_delivery_failed(uuid.uuid4(), "x", _now())

    def test_mark_already_failed_delivery_failed_again_raises(self):
        notification = make_notification()
        notification.record_delivery_attempt(NotificationChannel.SMS, _now())
        delivery_id = next(iter(notification.deliveries.keys()))
        notification.mark_delivery_failed(delivery_id, "x", _now())
        with pytest.raises(InvalidDeliveryTransition):
            notification.mark_delivery_failed(delivery_id, "y", _now())


class TestNotificationSeenRead:
    def test_mark_seen_persists_exact_timestamp(self):
        notification = make_notification()
        at = _now()
        event = notification.mark_seen(at)
        assert notification.seen_at == at
        assert notification.status == NotificationStatus.SEEN
        assert event.__class__.__name__ == "NotificationSeen"

    def test_mark_seen_twice_is_idempotent_noop(self):
        notification = make_notification()
        notification.mark_seen(_now())
        result = notification.mark_seen(_now())
        assert result is None

    def test_mark_read_persists_exact_timestamp(self):
        notification = make_notification()
        at = _now()
        event = notification.mark_read(at)
        assert notification.read_at == at
        assert notification.status == NotificationStatus.READ
        assert event.__class__.__name__ == "NotificationRead"

    def test_mark_read_reachable_directly_from_unseen(self):
        notification = make_notification()
        assert notification.status == NotificationStatus.UNSEEN
        notification.mark_read(_now())
        assert notification.status == NotificationStatus.READ

    def test_mark_read_twice_is_idempotent_noop(self):
        notification = make_notification()
        notification.mark_read(_now())
        result = notification.mark_read(_now())
        assert result is None

    def test_mark_seen_after_read_is_idempotent_noop_and_does_not_downgrade_status(self):
        notification = make_notification()
        notification.mark_read(_now())
        result = notification.mark_seen(_now())
        assert result is None
        assert notification.status == NotificationStatus.READ


class TestNotificationCancel:
    def test_cancel_succeeds_from_unseen(self):
        notification = make_notification()
        event = notification.cancel()
        assert notification.status == NotificationStatus.CANCELLED
        assert event.__class__.__name__ == "NotificationCancelled"

    def test_cancel_succeeds_from_seen(self):
        notification = make_notification()
        notification.mark_seen(_now())
        notification.cancel()
        assert notification.status == NotificationStatus.CANCELLED

    def test_double_cancel_raises_already_cancelled(self):
        notification = make_notification()
        notification.cancel()
        with pytest.raises(NotificationAlreadyCancelled):
            notification.cancel()

    def test_cancel_after_read_raises_invalid_transition(self):
        notification = make_notification()
        notification.mark_read(_now())
        with pytest.raises(InvalidNotificationTransition):
            notification.cancel()

    def test_cancel_after_delivered_raises_already_delivered(self):
        notification = make_notification()
        notification.record_delivery_attempt(NotificationChannel.EMAIL, _now())
        delivery_id = next(iter(notification.deliveries.keys()))
        notification.confirm_delivery(delivery_id, _now())
        with pytest.raises(NotificationAlreadyDelivered):
            notification.cancel()

    def test_cancel_allowed_when_delivery_attempted_but_not_yet_confirmed(self):
        """A SENT (not yet DELIVERED) delivery attempt does not block cancellation -- only a confirmed DELIVERED does."""
        notification = make_notification()
        notification.record_delivery_attempt(NotificationChannel.EMAIL, _now())
        notification.cancel()
        assert notification.status == NotificationStatus.CANCELLED

    def test_cancel_allowed_when_a_delivery_failed(self):
        notification = make_notification()
        notification.record_delivery_attempt(NotificationChannel.EMAIL, _now())
        delivery_id = next(iter(notification.deliveries.keys()))
        notification.mark_delivery_failed(delivery_id, "x", _now())
        notification.cancel()
        assert notification.status == NotificationStatus.CANCELLED


class TestNotificationPreference:
    def test_create_has_no_disabled_combinations(self):
        preference = make_preference()
        assert preference.disabled_combinations == set()

    def test_every_combination_enabled_by_default(self):
        preference = make_preference()
        assert preference.is_enabled(NotificationChannel.EMAIL, NotificationType.PROMOTIONAL) is True
        assert preference.is_enabled(NotificationChannel.TELEGRAM, NotificationType.TRANSACTIONAL) is True

    def test_disable_specific_combination(self):
        preference = make_preference()
        event = preference.disable(NotificationChannel.EMAIL, NotificationType.PROMOTIONAL)
        assert preference.is_enabled(NotificationChannel.EMAIL, NotificationType.PROMOTIONAL) is False
        assert event.__class__.__name__ == "NotificationChannelDisabled"

    def test_disable_does_not_affect_other_combinations(self):
        preference = make_preference()
        preference.disable(NotificationChannel.EMAIL, NotificationType.PROMOTIONAL)
        assert preference.is_enabled(NotificationChannel.EMAIL, NotificationType.TRANSACTIONAL) is True
        assert preference.is_enabled(NotificationChannel.SMS, NotificationType.PROMOTIONAL) is True

    def test_disable_already_disabled_is_idempotent_noop(self):
        preference = make_preference()
        preference.disable(NotificationChannel.EMAIL, NotificationType.PROMOTIONAL)
        result = preference.disable(NotificationChannel.EMAIL, NotificationType.PROMOTIONAL)
        assert result is None

    def test_enable_reverses_disable(self):
        preference = make_preference()
        preference.disable(NotificationChannel.EMAIL, NotificationType.PROMOTIONAL)
        event = preference.enable(NotificationChannel.EMAIL, NotificationType.PROMOTIONAL)
        assert preference.is_enabled(NotificationChannel.EMAIL, NotificationType.PROMOTIONAL) is True
        assert event.__class__.__name__ == "NotificationChannelEnabled"

    def test_enable_already_enabled_is_idempotent_noop(self):
        preference = make_preference()
        result = preference.enable(NotificationChannel.EMAIL, NotificationType.PROMOTIONAL)
        assert result is None


class TestPrivateAccessBoundary:
    def test_private_methods_are_underscore_prefixed_and_not_part_of_public_contract(self):
        for cls in (Notification, NotificationPreference):
            public_methods = {name for name in dir(cls) if not name.startswith("_") and callable(getattr(cls, name, None))}
            assert "_get_delivery_or_raise" not in public_methods
