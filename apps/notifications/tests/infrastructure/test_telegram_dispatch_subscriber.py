"""
Phase 15's Telegram dispatch subscriber test matrix.

Uses real Notification creation via CreateNotification (not a
hand-built database row) so the outbox event this subscriber consumes
is exactly what production code actually stages -- matching the same
discipline already established in test_order_confirmed_notification_integration.py.
"""
from __future__ import annotations

import uuid

import pytest

from apps.notifications.domain.enums import NotificationPriority, NotificationType
from apps.notifications.infrastructure import composition as notifications_composition
from apps.notifications.infrastructure import models as notifications_orm
from apps.notifications.infrastructure.gateways import TelegramGatewayNonRetryableError, TelegramGatewayRetryableError
from apps.notifications.infrastructure.telegram_dispatch_subscriber import sync_telegram_dispatch


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
        return "fake-message-id-123"


def _create_real_user(telegram_username=None):
    from apps.identity.infrastructure import models as identity_orm

    return identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=f"+99895{uuid.uuid4().int % 10_000_000:07d}", full_name="Telegram Test User", status="active", telegram_username=telegram_username)


def _create_real_notification(recipient_id):
    return notifications_composition.build_create_notification().execute(
        recipient_id=recipient_id, notification_type=NotificationType.TRANSACTIONAL, priority=NotificationPriority.NORMAL,
        title="Test Notification", body="This is a real test notification body.", template_key="test",
    )


@pytest.mark.django_db
class TestTelegramDispatchBasic:
    def test_dispatches_to_recipient_with_linked_telegram(self, monkeypatch):
        user = _create_real_user(telegram_username="@real_test_user")
        notification = _create_real_notification(user.id)

        fake_gateway = _FakeGateway("success")
        monkeypatch.setattr(notifications_composition, "build_telegram_gateway", lambda: fake_gateway)

        result = sync_telegram_dispatch()
        assert result["sent"] == 1
        assert fake_gateway.calls == [("@real_test_user", "Test Notification", "This is a real test notification body.")]

        row = notifications_orm.NotificationModel.objects.get(id=notification.id)
        deliveries = notifications_orm.NotificationDeliveryModel.objects.filter(notification=row)
        assert deliveries.count() == 1
        assert deliveries.first().status == "delivered"
        assert deliveries.first().provider_reference == "fake-message-id-123"

    def test_recipient_without_telegram_is_skipped_not_errored(self, monkeypatch):
        user = _create_real_user(telegram_username=None)
        _create_real_notification(user.id)

        fake_gateway = _FakeGateway("success")
        monkeypatch.setattr(notifications_composition, "build_telegram_gateway", lambda: fake_gateway)

        result = sync_telegram_dispatch()
        assert result["sent"] == 0
        assert result["skipped"] == 1
        assert fake_gateway.calls == []


@pytest.mark.django_db
class TestTelegramDispatchIdempotency:
    def test_same_notification_never_dispatched_twice(self, monkeypatch):
        user = _create_real_user(telegram_username="@idempotency_test")
        _create_real_notification(user.id)

        fake_gateway = _FakeGateway("success")
        monkeypatch.setattr(notifications_composition, "build_telegram_gateway", lambda: fake_gateway)

        result1 = sync_telegram_dispatch()
        assert result1["sent"] == 1

        cursor = notifications_orm.TelegramDispatchCursor.objects.get(id=1)
        cursor.last_processed_created_at = None
        cursor.last_processed_id = None
        cursor.save()

        result2 = sync_telegram_dispatch()
        assert result2["sent"] == 0
        assert result2["skipped"] == 1
        assert len(fake_gateway.calls) == 1


@pytest.mark.django_db
class TestTelegramDispatchFailureHandling:
    def test_non_retryable_failure_is_skipped_and_batch_continues(self, monkeypatch):
        user_a = _create_real_user(telegram_username="@will_fail")
        user_b = _create_real_user(telegram_username="@will_succeed")
        _create_real_notification(user_a.id)
        _create_real_notification(user_b.id)

        class _MixedGateway:
            def send_message(self, telegram_username, title, body):
                if telegram_username == "@will_fail":
                    raise TelegramGatewayNonRetryableError("rejected")
                return "ok-id"

        monkeypatch.setattr(notifications_composition, "build_telegram_gateway", lambda: _MixedGateway())

        result = sync_telegram_dispatch()
        assert result["sent"] == 1
        assert result["skipped"] == 1

    def test_retryable_failure_stops_batch_without_advancing_cursor_past_it(self, monkeypatch):
        user = _create_real_user(telegram_username="@transient_failure")
        _create_real_notification(user.id)

        fake_gateway = _FakeGateway("retryable")
        monkeypatch.setattr(notifications_composition, "build_telegram_gateway", lambda: fake_gateway)

        result = sync_telegram_dispatch()
        assert result["sent"] == 0
        assert notifications_orm.NotificationDeliveryModel.objects.count() == 0

        monkeypatch.setattr(notifications_composition, "build_telegram_gateway", lambda: _FakeGateway("success"))
        result2 = sync_telegram_dispatch()
        assert result2["sent"] == 1


@pytest.mark.django_db
class TestTelegramDispatchSecretSafety:
    def test_gateway_never_receives_bot_token_directly(self):
        import inspect

        from apps.notifications.infrastructure import telegram_dispatch_subscriber

        source = inspect.getsource(telegram_dispatch_subscriber)
        assert "TELEGRAM_BOT_TOKEN" not in source
        assert "bot_token" not in source.lower()
