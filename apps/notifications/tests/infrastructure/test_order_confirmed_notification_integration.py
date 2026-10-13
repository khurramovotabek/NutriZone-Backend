"""
Phase 02G's OrderConfirmed -> customer notification test matrix.
Real PostgreSQL throughout; drives the real ConfirmOrder Application
Service (not a hand-built event payload) so the outbox event this
suite's own subscriber consumes is exactly what production code
actually stages.
"""
from __future__ import annotations

import threading
import uuid
from decimal import Decimal

import pytest
from django.db import connection

from apps.notifications.infrastructure import models as notifications_orm
from apps.notifications.infrastructure.order_confirmed_subscriber import sync_order_confirmed_notifications
from apps.ordering.infrastructure import composition as ordering_composition
from apps.ordering.tests.factories import make_line_item
from common.utils.money import Money


def _persist_confirmed_order(customer_id, unit_price=Decimal("500.00"), quantity=1, currency="UZS"):
    from datetime import datetime as _dt
    from apps.ordering.domain.aggregates import Order
    from apps.ordering.domain.enums import OrderChannel, OrderStatus
    from apps.ordering.domain.value_objects import OrderNumber
    from apps.ordering.tests.factories import _next_order_number, make_address

    line = make_line_item(unit_price=Money(amount=unit_price, currency=currency), quantity=quantity)
    order = Order(
        id=uuid.uuid4(), order_number=OrderNumber(_next_order_number()), customer_id=customer_id, cart_id=uuid.uuid4(),
        shipping_address=make_address(), billing_address=make_address(), currency=currency, channel=OrderChannel.WEB,
        status=OrderStatus.PENDING_PAYMENT, lines={line.id: line}, placed_at=_dt.utcnow(),
    )
    saved = ordering_composition.build_order_repository().save(order)
    ordering_composition.build_confirm_order(None).execute(saved.id)
    return saved


@pytest.mark.django_db
class TestBasicTrigger:
    def test_order_confirmed_creates_notification_for_customer(self):
        customer_id = uuid.uuid4()
        order = _persist_confirmed_order(customer_id)
        result = sync_order_confirmed_notifications()
        assert result["notified"] == 1
        assert result["failed"] is False

        record = notifications_orm.OrderConfirmedNotificationRecord.objects.get(order_id=order.id)
        notification = notifications_orm.NotificationModel.objects.get(id=record.notification_id)
        assert notification.recipient_id == customer_id
        assert notification.notification_type == "transactional"

    def test_guest_order_no_customer_id_is_skipped_not_crashed(self):
        order = _persist_confirmed_order(None)
        result = sync_order_confirmed_notifications()
        assert result["notified"] == 0
        assert result["skipped"] == 1
        assert result["failed"] is False
        assert notifications_orm.OrderConfirmedNotificationRecord.objects.filter(order_id=order.id).exists() is False


@pytest.mark.django_db
class TestIdempotency:
    def test_duplicate_event_processing_does_not_create_two_notifications(self):
        customer_id = uuid.uuid4()
        order = _persist_confirmed_order(customer_id)
        sync_order_confirmed_notifications()
        notifications_orm.OrderConfirmedNotificationCursor.objects.filter(id=1).update(last_processed_created_at=None, last_processed_id=None)
        sync_order_confirmed_notifications()

        assert notifications_orm.OrderConfirmedNotificationRecord.objects.filter(order_id=order.id).count() == 1
        recipient_notifications = notifications_orm.NotificationModel.objects.filter(recipient_id=customer_id)
        assert recipient_notifications.count() == 1


@pytest.mark.django_db(transaction=True)
class TestConcurrency:
    def test_concurrent_duplicate_processing_produces_exactly_one_notification_record(self):
        order_id = uuid.uuid4()
        winners, errors = [], []

        def worker():
            from django.db import IntegrityError as _IE
            try:
                notifications_orm.OrderConfirmedNotificationRecord.objects.create(order_id=order_id, notification_id=uuid.uuid4())
                winners.append(1)
            except _IE:
                errors.append(1)
            finally:
                connection.close()

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(winners) == 1
        assert len(errors) == 4
        assert notifications_orm.OrderConfirmedNotificationRecord.objects.filter(order_id=order_id).count() == 1


@pytest.mark.django_db
class TestSecurity:
    def test_recipient_is_never_taken_from_arbitrary_input(self):
        import inspect
        from apps.notifications.infrastructure.order_confirmed_subscriber import _process_one_order_confirmation
        sig = inspect.signature(_process_one_order_confirmation)
        assert list(sig.parameters) == ["order_id"]

    def test_no_notification_without_a_real_confirmed_order(self):
        result = sync_order_confirmed_notifications()
        assert result["notified"] == 0
        assert notifications_orm.OrderConfirmedNotificationRecord.objects.count() == 0


@pytest.mark.django_db
class TestAuditOutboxIntegration:
    def test_notification_created_event_staged_to_outbox(self):
        customer_id = uuid.uuid4()
        _persist_confirmed_order(customer_id)
        sync_order_confirmed_notifications()
        assert notifications_orm.NotificationOutboxEvent.objects.filter(event_type="NotificationCreated").exists()


@pytest.mark.django_db
class TestEndToEnd:
    def test_full_flow_order_creation_to_confirmed_to_notified(self):
        customer_id = uuid.uuid4()
        order = _persist_confirmed_order(customer_id, unit_price=Decimal("750.00"), quantity=2)
        result = sync_order_confirmed_notifications()
        assert result["notified"] == 1

        record = notifications_orm.OrderConfirmedNotificationRecord.objects.get(order_id=order.id)
        notification = notifications_orm.NotificationModel.objects.get(id=record.notification_id)
        assert order.order_number.value in notification.body
        assert notification.status == "unseen"
