"""
Real, product-required onboarding flow: on a not-yet-linked
Telegram user's first /start, the bot asks for their full name, then
their phone number (via a native "share contact" button), and only
then creates/links the real customer account. On any subsequent
/start from an already-linked Telegram user, none of this repeats --
the bot goes straight to the main menu.

This flow (views.py's own _handle_start / _handle_full_name_reply /
_handle_contact, backed by interfaces.onboarding_state) already
existed, fully working, before this test file was written -- it had
simply never been covered by a permanent test.
"""
from __future__ import annotations

import json
import uuid

import pytest
from django.test import Client, override_settings

from apps.identity.infrastructure import models as identity_orm
from apps.telegram_bot.interfaces import onboarding_state

pytestmark = pytest.mark.django_db

WEBHOOK_SECRET = "test-secret-onboarding"


def _post_update(client: Client, update: dict):
    with override_settings(TELEGRAM_WEBHOOK_SECRET=WEBHOOK_SECRET):
        return client.post(
            "/api/v1/telegram/webhook",
            data=json.dumps(update),
            content_type="application/json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=WEBHOOK_SECRET,
        )


class TestFirstTimeOnboardingAsksLanguageThenNameThenPhone:
    def test_first_start_puts_the_chat_into_awaiting_language(self):
        client = Client()
        chat_id = uuid.uuid4().int % 1_000_000_000
        tg_user_id = uuid.uuid4().int % 1_000_000_000

        response = _post_update(client, {"message": {"chat": {"id": chat_id}, "from": {"id": tg_user_id, "first_name": "Test"}, "text": "/start"}})
        assert response.status_code == 200

        state = onboarding_state.get_state(chat_id)
        assert state is not None
        assert state["step"] == "awaiting_language"

    def test_selecting_a_language_advances_to_awaiting_full_name(self):
        from apps.telegram_bot.interfaces.callback_router import handle_callback

        chat_id = uuid.uuid4().int % 1_000_000_000
        tg_user_id = uuid.uuid4().int % 1_000_000_000
        onboarding_state.set_awaiting_language(chat_id)

        handle_callback({"id": "c1", "from": {"id": tg_user_id}, "message": {"chat": {"id": chat_id}}, "data": "onboarding:lang:uz"})

        state = onboarding_state.get_state(chat_id)
        assert state is not None
        assert state["step"] == "awaiting_full_name"
        assert state["language"] == "uz"

    def test_typing_a_name_advances_to_awaiting_phone_and_keeps_the_name(self):
        client = Client()
        chat_id = uuid.uuid4().int % 1_000_000_000
        tg_user_id = uuid.uuid4().int % 1_000_000_000
        onboarding_state.set_awaiting_full_name(chat_id, "uz")

        response = _post_update(client, {"message": {"chat": {"id": chat_id}, "from": {"id": tg_user_id, "first_name": "Test"}, "text": "Aziz Karimov"}})
        assert response.status_code == 200

        state = onboarding_state.get_state(chat_id)
        assert state is not None
        assert state["step"] == "awaiting_phone"
        assert state["full_name"] == "Aziz Karimov"
        assert state["language"] == "uz"

    def test_too_short_a_name_is_rejected_and_stays_in_awaiting_full_name(self):
        client = Client()
        chat_id = uuid.uuid4().int % 1_000_000_000
        tg_user_id = uuid.uuid4().int % 1_000_000_000
        onboarding_state.set_awaiting_full_name(chat_id, "uz")

        _post_update(client, {"message": {"chat": {"id": chat_id}, "from": {"id": tg_user_id, "first_name": "Test"}, "text": "A"}})

        state = onboarding_state.get_state(chat_id)
        assert state is not None
        assert state["step"] == "awaiting_full_name"  # never advanced

    def test_sharing_contact_moves_to_confirmation_without_creating_the_account_yet(self):
        """Real, business-required behavior: no account is created on contact share alone -- the user must explicitly confirm via onboarding:confirm first."""
        client = Client()
        chat_id = uuid.uuid4().int % 1_000_000_000
        tg_user_id = uuid.uuid4().int % 1_000_000_000
        phone = f"+99890{uuid.uuid4().int % 10000000:07d}"
        onboarding_state.set_awaiting_phone(chat_id, "uz", "Aziz Karimov")

        response = _post_update(client, {"message": {"chat": {"id": chat_id}, "from": {"id": tg_user_id, "first_name": "Test"}, "contact": {"phone_number": phone, "user_id": tg_user_id}}})
        assert response.status_code == 200

        assert identity_orm.User.objects.filter(telegram_user_id=tg_user_id).first() is None

        state = onboarding_state.get_state(chat_id)
        assert state is not None
        assert state["step"] == "awaiting_confirmation"
        assert state["full_name"] == "Aziz Karimov"
        assert state["phone_number"] == phone

    def test_confirming_creates_the_real_customer_with_name_phone_and_language(self):
        from apps.telegram_bot.interfaces.callback_router import handle_callback

        chat_id = uuid.uuid4().int % 1_000_000_000
        tg_user_id = uuid.uuid4().int % 1_000_000_000
        phone = f"+99890{uuid.uuid4().int % 10000000:07d}"
        onboarding_state.set_awaiting_confirmation(chat_id, "ru", "Aziz Karimov", phone)

        handle_callback({"id": "c2", "from": {"id": tg_user_id}, "message": {"chat": {"id": chat_id}}, "data": "onboarding:confirm"})

        user = identity_orm.User.objects.filter(telegram_user_id=tg_user_id).first()
        assert user is not None
        assert user.full_name == "Aziz Karimov"
        assert user.phone_number == phone
        assert user.language == "ru"

        # Onboarding state is cleared once the real account exists.
        state = onboarding_state.get_state(chat_id)
        assert state is None or state.get("step") is None

    def test_cancelling_clears_state_and_creates_no_account(self):
        from apps.telegram_bot.interfaces.callback_router import handle_callback

        chat_id = uuid.uuid4().int % 1_000_000_000
        tg_user_id = uuid.uuid4().int % 1_000_000_000
        phone = f"+99890{uuid.uuid4().int % 10000000:07d}"
        onboarding_state.set_awaiting_confirmation(chat_id, "uz", "Aziz Karimov", phone)

        handle_callback({"id": "c3", "from": {"id": tg_user_id}, "message": {"chat": {"id": chat_id}}, "data": "onboarding:cancel"})

        assert identity_orm.User.objects.filter(telegram_user_id=tg_user_id).first() is None
        state = onboarding_state.get_state(chat_id)
        assert state is None or state.get("step") is None


class TestReturningUserSkipsOnboarding:
    def test_start_from_an_already_linked_telegram_user_never_asks_for_name_or_phone(self):
        client = Client()
        chat_id = uuid.uuid4().int % 1_000_000_000
        tg_user_id = uuid.uuid4().int % 1_000_000_000
        phone = f"+99890{uuid.uuid4().int % 10000000:07d}"
        identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=phone, full_name="Mavjud Foydalanuvchi", status="active", telegram_user_id=tg_user_id)

        response = _post_update(client, {"message": {"chat": {"id": chat_id}, "from": {"id": tg_user_id, "first_name": "Test"}, "text": "/start"}})
        assert response.status_code == 200

        # The onboarding state machine was never entered at all.
        state = onboarding_state.get_state(chat_id)
        assert state is None or state.get("step") is None

    def test_plain_start_never_generates_or_sends_an_otp_code(self, settings):
        """Real, explicitly-required behavior: /start -- with or without the website's own "login" deep-link payload -- from an already-linked user must ONLY show the main menu. It must never call RequestOTP or send_login_code, no matter how send_main_menu's own implementation evolves. See also test_telegram_auth_and_webhook.py::test_start_login_for_a_linked_user_never_sends_a_login_code."""
        from unittest.mock import patch

        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"

        chat_id = uuid.uuid4().int % 1_000_000_000
        tg_user_id = uuid.uuid4().int % 1_000_000_000
        phone = f"+99890{uuid.uuid4().int % 10000000:07d}"
        identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=phone, full_name="Mavjud Foydalanuvchi", status="active", telegram_user_id=tg_user_id, language="uz")

        client = Client()
        with patch("apps.identity.application.services.auth.RequestOTP.execute") as mock_otp, \
                patch("apps.telegram_bot.interfaces.callback_router.send_login_code") as mock_send_code:
            response = _post_update(client, {"message": {"chat": {"id": chat_id}, "from": {"id": tg_user_id}, "text": "/start"}})

        assert response.status_code == 200
        assert not mock_otp.called
        assert not mock_send_code.called


class TestPartiallyRegisteredUserResumesOnboarding:
    """
    Defensive gate: a `telegram_user_id`-linked account missing its
    `full_name` is not "registered" and must never see the main menu
    (or, worse, a login code) as if it were. LinkTelegramCustomer never
    produces this state itself (full_name/phone_number are always set
    together), so this covers pre-existing/externally-edited data.
    """

    def test_start_from_a_linked_user_with_no_full_name_resumes_at_the_name_step(self, settings):
        from unittest.mock import patch

        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"

        chat_id = uuid.uuid4().int % 1_000_000_000
        tg_user_id = uuid.uuid4().int % 1_000_000_000
        phone = f"+99890{uuid.uuid4().int % 10000000:07d}"
        identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=phone, full_name="", status="active", telegram_user_id=tg_user_id, language="uz")

        client = Client()
        with patch("apps.telegram_bot.interfaces.callback_router.send_login_code") as mock_send_code, \
                patch("apps.telegram_bot.interfaces.callback_router.send_main_menu") as mock_send_menu:
            response = _post_update(client, {"message": {"chat": {"id": chat_id}, "from": {"id": tg_user_id}, "text": "/start"}})

        assert response.status_code == 200
        assert not mock_send_code.called
        assert not mock_send_menu.called

        state = onboarding_state.get_state(chat_id)
        assert state is not None
        assert state["step"] == "awaiting_full_name"
