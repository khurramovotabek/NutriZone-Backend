"""
`NotificationDelivery` has no independent public mutation methods of
its own -- its lifecycle is entirely governed by `Notification`'s own
`confirm_delivery`/`mark_delivery_failed` methods (see
test_aggregates.py for the full lifecycle coverage). This file tests
only the entity's own construction/field invariants in isolation.
**No PENDING state is tested here, because none exists** -- entities
are always constructed directly in SENT, per the certified Domain
contract.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from apps.notifications.domain.entities import NotificationDelivery
from apps.notifications.domain.enums import DeliveryStatus, NotificationChannel

pytestmark = pytest.mark.unit


class TestNotificationDelivery:
    def test_valid_construction_in_sent_status(self):
        delivery = NotificationDelivery(id=uuid.uuid4(), channel=NotificationChannel.TELEGRAM, status=DeliveryStatus.SENT, attempted_at=datetime.utcnow())
        assert delivery.status == DeliveryStatus.SENT
        assert delivery.delivered_at is None
        assert delivery.failed_at is None

    def test_provider_reference_defaults_to_none(self):
        delivery = NotificationDelivery(id=uuid.uuid4(), channel=NotificationChannel.EMAIL, status=DeliveryStatus.SENT, attempted_at=datetime.utcnow())
        assert delivery.provider_reference is None

    def test_provider_reference_is_a_plain_opaque_string(self):
        """Domain never validates or interprets this field -- it is recorded as a fact, matching entities.py's own module docstring."""
        delivery = NotificationDelivery(id=uuid.uuid4(), channel=NotificationChannel.TELEGRAM, status=DeliveryStatus.SENT, attempted_at=datetime.utcnow(), provider_reference="msg_12345")
        assert delivery.provider_reference == "msg_12345"

    def test_no_pending_status_exists(self):
        """A direct, executable proof against the certified 'no PENDING state' decision -- fails loudly if PENDING is ever added to DeliveryStatus without updating this test."""
        assert set(DeliveryStatus.values()) == {"sent", "delivered", "failed"}
