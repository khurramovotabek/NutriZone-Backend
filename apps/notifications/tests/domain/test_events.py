from __future__ import annotations

import ast
import dataclasses
import uuid

import pytest

import apps.notifications.domain.events as events_module
import apps.notifications.domain.exceptions as exceptions_module
from apps.notifications.domain.events import (
    NotificationCancelled, NotificationChannelDisabled, NotificationChannelEnabled, NotificationCreated,
    NotificationDelivered, NotificationDeliveryFailed, NotificationDeliverySent, NotificationRead, NotificationSeen,
)

pytestmark = pytest.mark.unit


def test_notification_created_payload():
    notification_id, recipient_id = uuid.uuid4(), uuid.uuid4()
    payload = NotificationCreated(notification_id=notification_id, recipient_id=recipient_id, notification_type="transactional").to_payload()
    assert payload["notification_id"] == str(notification_id)
    assert payload["notification_type"] == "transactional"


def test_notification_delivery_sent_payload():
    payload = NotificationDeliverySent(notification_id=uuid.uuid4(), delivery_id=uuid.uuid4(), channel="telegram").to_payload()
    assert payload["channel"] == "telegram"


def test_notification_delivered_payload():
    notification_id, delivery_id = uuid.uuid4(), uuid.uuid4()
    assert NotificationDelivered(notification_id=notification_id, delivery_id=delivery_id).to_payload() == {"notification_id": str(notification_id), "delivery_id": str(delivery_id)}


def test_notification_delivery_failed_payload():
    payload = NotificationDeliveryFailed(notification_id=uuid.uuid4(), delivery_id=uuid.uuid4(), reason="invalid number").to_payload()
    assert payload["reason"] == "invalid number"


def test_notification_seen_payload():
    notification_id = uuid.uuid4()
    assert NotificationSeen(notification_id=notification_id).to_payload() == {"notification_id": str(notification_id)}


def test_notification_read_payload():
    notification_id = uuid.uuid4()
    assert NotificationRead(notification_id=notification_id).to_payload() == {"notification_id": str(notification_id)}


def test_notification_cancelled_payload():
    notification_id = uuid.uuid4()
    assert NotificationCancelled(notification_id=notification_id).to_payload() == {"notification_id": str(notification_id)}


def test_notification_channel_enabled_payload():
    payload = NotificationChannelEnabled(preference_id=uuid.uuid4(), user_id=uuid.uuid4(), channel="email", notification_type="promotional").to_payload()
    assert payload["channel"] == "email"
    assert payload["notification_type"] == "promotional"


def test_notification_channel_disabled_payload():
    payload = NotificationChannelDisabled(preference_id=uuid.uuid4(), user_id=uuid.uuid4(), channel="sms", notification_type="transactional").to_payload()
    assert payload["channel"] == "sms"


def test_every_event_is_a_frozen_dataclass():
    event_classes = [obj for name, obj in vars(events_module).items() if isinstance(obj, type) and dataclasses.is_dataclass(obj)]
    for cls in event_classes:
        assert cls.__dataclass_params__.frozen is True, f"{cls.__name__} is not frozen"


def test_events_are_immutable():
    event = NotificationRead(notification_id=uuid.uuid4())
    with pytest.raises(Exception):
        event.notification_id = uuid.uuid4()  # type: ignore[misc]


def test_programmatically_verify_exactly_9_events():
    tree = ast.parse(open(events_module.__file__).read())
    class_names = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
    assert len(class_names) == 9, f"Expected exactly 9 Notifications domain events, found {len(class_names)}: {class_names}"


def test_zero_collisions_between_events_and_exceptions():
    event_names = set(n.name for n in ast.parse(open(events_module.__file__).read()).body if isinstance(n, ast.ClassDef))
    exception_names = set(n.name for n in ast.parse(open(exceptions_module.__file__).read()).body if isinstance(n, ast.ClassDef))
    collisions = event_names & exception_names
    assert not collisions, f"Naming collisions found between events and exceptions: {collisions}"
