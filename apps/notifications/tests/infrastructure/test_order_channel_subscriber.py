"""
Phase 15 continuation: Orders Channel notification subscriber tests.

Real database throughout, real Order aggregate creation via the same
factories already used by test_order_confirmed_notification_integration.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime as _dt
from decimal import Decimal

import pytest

from apps.notifications.infrastructure import composition as notifications_composition
from apps.notifications.infrastructure import models as notifications_orm
from apps.notifications.infrastructure.gateways import TelegramGatewayNonRetryableError, TelegramGatewayRetryableError
from apps.notifications.infrastructure.order_channel_subscriber import sync_order_channel_notifications
from apps.ordering.domain.aggregates import Order
from apps.ordering.domain.enums import OrderChannel
from apps.ordering.domain.value_objects import OrderNumber
from apps.ordering.infrastructure import composition as ordering_composition
from apps.ordering.tests.factories import _next_order_number, make_address, make_line_item
from common.utils.money import Money


class _FakeGateway:
    def __init__(self, outcome="success"):
        self.outcome = outcome
        self.calls = []

    def send_message(self, telegram_username, title, body):
        self.calls.append((telegram_username, title, body))
        if self.outcome == "retryable":
            raise TelegramGatewayRetryableError("Simulated transient failure.")
        if self.outcome == "non_retryable":
            raise TelegramGatewayNonRetryableError("Simulated permanent rejection.")
        return "fake-message-id"


def _persist_new_order(unit_price=Decimal("850000.00"), quantity=1, currency="UZS"):
    from apps.ordering.domain.events import OrderCreated
    from apps.ordering.infrastructure import models as ordering_orm
    from core.outbox import stage_event

    line = make_line_item(unit_price=Money(amount=unit_price, currency=currency), quantity=quantity)
    order = Order(
        id=uuid.uuid4(), order_number=OrderNumber(_next_order_number()), customer_id=uuid.uuid4(), cart_id=uuid.uuid4(),
        shipping_address=make_address(), billing_address=make_address(), currency=currency, channel=OrderChannel.WEB,
        lines={line.id: line}, placed_at=_dt.utcnow(),
    )
    saved = ordering_composition.build_order_repository().save(order)

    # repository.save() alone never stages an event -- only the real
    # CreateOrderFromCart application service does that, separately,
    # as part of a full cart checkout. Staging it explicitly here,
    # matching OrderCreated's own real to_payload() shape exactly.
    event = OrderCreated(order_id=saved.id, order_number=saved.order_number.value, cart_id=saved.cart_id, customer_id=saved.customer_id)
    stage_event(ordering_orm.OrderingOutboxEvent, "OrderCreated", event.to_payload())

    return saved


@pytest.mark.django_db
class TestOrderChannelConfiguration:
    def test_unconfigured_chat_id_skips_without_error(self, monkeypatch, settings):
        settings.TELEGRAM_ORDERS_CHAT_ID = ""
        _persist_new_order()
        fake_gateway = _FakeGateway("success")
        monkeypatch.setattr(notifications_composition, "build_telegram_gateway", lambda: fake_gateway)

        result = sync_order_channel_notifications()
        assert result["sent"] == 0
        assert result["reason"] == "TELEGRAM_ORDERS_CHAT_ID not configured"
        assert fake_gateway.calls == []


@pytest.mark.django_db
class TestOrderChannelBasic:
    def test_new_order_sends_real_formatted_message(self, monkeypatch, settings):
        settings.TELEGRAM_ORDERS_CHAT_ID = "-1001234567890"
        order = _persist_new_order(unit_price=Decimal("850000.00"), quantity=2)
        fake_gateway = _FakeGateway("success")
        monkeypatch.setattr(notifications_composition, "build_telegram_gateway", lambda: fake_gateway)

        result = sync_order_channel_notifications()
        assert result["sent"] == 1
        assert len(fake_gateway.calls) == 1

        chat_id, _title, message = fake_gateway.calls[0]
        assert chat_id == "-1001234567890"
        assert order.order_number.value in message
        assert "1 700 000" in message
        assert "UZS" in message

        assert notifications_orm.OrderChannelNotificationRecord.objects.filter(order_id=order.id).exists()

    def test_order_with_shipping_address_does_not_crash(self, monkeypatch, settings):
        settings.TELEGRAM_ORDERS_CHAT_ID = "-1001234567890"
        order = _persist_new_order()
        fake_gateway = _FakeGateway("success")
        monkeypatch.setattr(notifications_composition, "build_telegram_gateway", lambda: fake_gateway)

        result = sync_order_channel_notifications()
        assert result["sent"] == 1


@pytest.mark.django_db
class TestOrderChannelIdempotency:
    def test_same_order_never_sent_twice(self, monkeypatch, settings):
        settings.TELEGRAM_ORDERS_CHAT_ID = "-1001234567890"
        _persist_new_order()
        fake_gateway = _FakeGateway("success")
        monkeypatch.setattr(notifications_composition, "build_telegram_gateway", lambda: fake_gateway)

        result1 = sync_order_channel_notifications()
        assert result1["sent"] == 1

        cursor = notifications_orm.TelegramDispatchCursor.objects.get(id=2)
        cursor.last_processed_created_at = None
        cursor.last_processed_id = None
        cursor.save()

        result2 = sync_order_channel_notifications()
        assert result2["sent"] == 0
        assert len(fake_gateway.calls) == 1


@pytest.mark.django_db
class TestOrderChannelFailureHandling:
    def test_retryable_failure_does_not_create_a_false_sent_record(self, monkeypatch, settings):
        settings.TELEGRAM_ORDERS_CHAT_ID = "-1001234567890"
        _persist_new_order()
        fake_gateway = _FakeGateway("retryable")
        monkeypatch.setattr(notifications_composition, "build_telegram_gateway", lambda: fake_gateway)

        result = sync_order_channel_notifications()
        assert result["sent"] == 0

        monkeypatch.setattr(notifications_composition, "build_telegram_gateway", lambda: _FakeGateway("success"))
        result2 = sync_order_channel_notifications()
        assert result2["sent"] == 1

    def test_non_retryable_failure_is_skipped_and_batch_continues(self, monkeypatch, settings):
        settings.TELEGRAM_ORDERS_CHAT_ID = "-1001234567890"
        _persist_new_order()
        _persist_new_order()

        fake_gateway = _FakeGateway("non_retryable")
        monkeypatch.setattr(notifications_composition, "build_telegram_gateway", lambda: fake_gateway)

        result = sync_order_channel_notifications()
        assert result["sent"] == 0
        assert result["skipped"] == 2
        assert len(fake_gateway.calls) == 2
