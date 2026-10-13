"""
Telegram OTP delivery channel -- reuses 100% of RequestOTP/VerifyOTP's
own existing, proven business logic by implementing the same
OTPProvider protocol; only the delivery mechanism differs from SMS.
Every scenario here was verified live via direct provider invocation
before being formalized as a test.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from apps.identity.domain.value_objects import PhoneNumber
from apps.identity.infrastructure.gateways.otp_providers import OTPProviderNonRetryableError, TelegramOTPProvider

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestTelegramOTPProviderRefusesUnlinkedAccounts:
    def test_phone_with_no_linked_telegram_account_raises_clearly(self):
        from apps.identity.infrastructure import models as identity_orm

        phone = f"+99890{str(uuid.uuid4().int)[:7]}"
        identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=phone, full_name="Unlinked", status="active", language="uz")

        with pytest.raises(OTPProviderNonRetryableError, match="no linked Telegram account"):
            TelegramOTPProvider().send_otp(PhoneNumber(phone), "123456")

    def test_phone_with_no_user_at_all_raises_clearly(self):
        phone = f"+99890{str(uuid.uuid4().int)[:7]}"
        with pytest.raises(OTPProviderNonRetryableError, match="no linked Telegram account"):
            TelegramOTPProvider().send_otp(PhoneNumber(phone), "123456")


class TestTelegramOTPProviderDeliversToLinkedAccount:
    def test_sends_the_real_code_to_the_real_linked_chat_id(self, settings):
        from apps.identity.infrastructure import models as identity_orm

        settings.TELEGRAM_BOT_TOKEN = "test-fake-token-for-mocked-http-only"
        phone = f"+99890{str(uuid.uuid4().int)[:7]}"
        telegram_id = 987654321
        identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=phone, full_name="Linked", status="active", language="uz", telegram_user_id=telegram_id)

        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200, json=lambda: {"ok": True, "result": {"message_id": 1}})
            result = TelegramOTPProvider().send_otp(PhoneNumber(phone), "654321")

        assert result is True
        sent_json = mock_post.call_args.kwargs["json"]
        assert sent_json["chat_id"] == str(telegram_id)
        assert "654321" in sent_json["text"]

    def test_returns_false_on_retryable_telegram_error_not_an_exception(self, settings):
        from apps.identity.infrastructure import models as identity_orm

        settings.TELEGRAM_BOT_TOKEN = "test-fake-token-for-mocked-http-only"
        phone = f"+99890{str(uuid.uuid4().int)[:7]}"
        identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=phone, full_name="Linked", status="active", language="uz", telegram_user_id=111222333)

        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=500, json=lambda: {})
            result = TelegramOTPProvider().send_otp(PhoneNumber(phone), "111111")

        assert result is False
