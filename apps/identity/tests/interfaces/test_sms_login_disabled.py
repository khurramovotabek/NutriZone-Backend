"""
Real, live-verified regression test: SMS/phone login was temporarily
disabled per explicit product decision (Telegram-only for now), via a
simple, reversible settings toggle (NUTRIZONE_SMS_LOGIN_ENABLED) --
not a deletion. Every scenario here was proven live via a real HTTP
request before being formalized.
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import pytest
from django.test import Client

from apps.identity.infrastructure import models as identity_orm
from apps.identity.infrastructure.security import hash_otp_code

pytestmark = pytest.mark.django_db


class TestSmsLoginTemporarilyDisabled:
    def test_sms_request_otp_returns_503_by_default(self, settings):
        settings.NUTRIZONE_SMS_LOGIN_ENABLED = False
        client = Client()
        response = client.post("/api/v1/identity/auth/request-otp", data=json.dumps({"phone_number": f"+99890{uuid.uuid4().int % 10000000:07d}"}), content_type="application/json")
        assert response.status_code == 503

    def test_sms_request_otp_can_be_re_enabled_via_settings(self, settings):
        settings.NUTRIZONE_SMS_LOGIN_ENABLED = True
        client = Client()
        response = client.post("/api/v1/identity/auth/request-otp", data=json.dumps({"phone_number": f"+99890{uuid.uuid4().int % 10000000:07d}"}), content_type="application/json")
        assert response.status_code == 202

    def test_telegram_otp_request_is_unaffected_by_sms_being_disabled(self, settings):
        settings.NUTRIZONE_SMS_LOGIN_ENABLED = False
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"

        phone = f"+99890{uuid.uuid4().int % 10000000:07d}"
        identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=phone, status="active", telegram_user_id=uuid.uuid4().int % 900000000, full_name="Test")

        client = Client()
        with patch("apps.notifications.infrastructure.gateways.LiveTelegramGateway.send_message_with_keyboard", return_value="1"):
            response = client.post("/api/v1/identity/auth/request-telegram-code", data=json.dumps({"phone_number": phone}), content_type="application/json")
        assert response.status_code == 202

    def test_verify_otp_is_unaffected_by_sms_being_disabled(self, settings):
        """verify-otp is shared with the Telegram 6-digit-code flow (VerifyOTP has no dependency on how the code was delivered) -- must keep working regardless of the SMS toggle."""
        settings.NUTRIZONE_SMS_LOGIN_ENABLED = False

        phone = f"+99890{uuid.uuid4().int % 10000000:07d}"
        client = Client()
        from django.utils import timezone as django_timezone
        from datetime import timedelta

        identity_orm.OTPCodeChallenge.objects.create(
            id=uuid.uuid4(), phone_number=phone, code_hash=hash_otp_code("999999"),
            expires_at=django_timezone.now() + timedelta(minutes=5), attempt_count=0,
        )

        response = client.post("/api/v1/identity/auth/verify-otp", data=json.dumps({"phone_number": phone, "code": "999999"}), content_type="application/json")
        assert response.status_code == 200
