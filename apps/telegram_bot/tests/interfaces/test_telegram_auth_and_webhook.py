"""
Real, live-verified regression tests for this phase's Telegram
authentication work:
1. The full website "Continue with Telegram" -> bot confirm ->
   polling -> real JWT flow.
2. A real bug found and fixed: requesting a Telegram-delivered login
   code for a phone with no linked Telegram account previously
   returned 503 (implying a transient, retry-worthy failure) instead
   of 422 (a permanent, customer-facing condition retrying will never
   fix).
3. The `telegram_set_webhook` management command and its safe,
   opt-in-only auto-registration in TelegramBotConfig.ready().
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.test import Client

from apps.identity.infrastructure import models as identity_orm
from apps.products.infrastructure import models as p_models

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_rate_limit_state():
    """Real test-isolation fix: Redis-backed rate-limit state (ScopedRateLimitThrottle/RateLimiter) is not bound to Django's per-test database transaction rollback, so OTP-request-throttle counters from one test in this file could otherwise leak into and spuriously fail the next."""
    from core.caching.redis_client import get_redis_client

    get_redis_client().flushdb()  # own database only (testing.py gives each xdist worker one); flushall wiped the other workers
    yield


class TestTelegramAutomaticLoginFullFlow:
    def test_deep_link_confirm_yields_real_jwt_tokens(self, settings):
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_BOT_USERNAME = "nutrizone_test_bot"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"

        tg_user_id = uuid.uuid4().int % 900000000
        identity_orm.User.objects.create(
            id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", status="active",
            telegram_user_id=tg_user_id, full_name="Ali Karimov",
        )

        client = Client()
        create_response = client.post("/api/v1/identity/auth/telegram/session", data=json.dumps({}), content_type="application/json")
        assert create_response.status_code == 201
        session_body = json.loads(create_response.content)["data"]
        session_id = session_body["session_id"]
        raw_token = session_body["telegram_url"].split("start=")[1]

        pending_response = client.get(f"/api/v1/identity/auth/telegram/session/{session_id}")
        assert json.loads(pending_response.content)["data"]["status"] == "pending"

        webhook_auth = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": "test-webhook-secret"}
        with patch("apps.telegram_bot.interfaces.api.v1.views._reply_text"), patch("apps.telegram_bot.interfaces.callback_router._send"), patch("apps.telegram_bot.interfaces.api.v1.views._answer_callback_query"):
            start_update = {"update_id": 1, "message": {"message_id": 1, "chat": {"id": tg_user_id, "type": "private"}, "from": {"id": tg_user_id, "first_name": "Ali"}, "text": f"/start {raw_token}"}}
            client.post("/api/v1/telegram/webhook", data=json.dumps(start_update), content_type="application/json", **webhook_auth)

            confirm_update = {"update_id": 2, "callback_query": {"id": "cbq1", "from": {"id": tg_user_id}, "message": {"chat": {"id": tg_user_id}}, "data": f"authlogin:confirm:{session_id}"}}
            confirm_response = client.post("/api/v1/telegram/webhook", data=json.dumps(confirm_update), content_type="application/json", **webhook_auth)
            assert confirm_response.status_code == 200

        session = identity_orm.TelegramAuthSession.objects.get(id=session_id)
        assert session.status == "verified"

        poll_response = client.get(f"/api/v1/identity/auth/telegram/session/{session_id}")
        poll_body = json.loads(poll_response.content)["data"]
        assert "access_token" in poll_body

        session.refresh_from_db()
        assert session.status == "consumed"


class TestTelegramLoginCodeErrorHandling:
    def test_unlinked_phone_returns_422_not_503(self, settings):
        """Real bug found and fixed this phase: retrying a request for an unlinked phone number will never succeed -- 422 (permanent, customer-facing), not 503 (implies a transient failure worth retrying)."""
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"

        client = Client()
        response = client.post("/api/v1/identity/auth/request-telegram-code", data=json.dumps({"phone_number": "+998901112233"}), content_type="application/json")
        assert response.status_code == 422
        body = json.loads(response.content)
        assert body["error"]["details"]["fields"][0]["code"] == "TELEGRAM_NOT_LINKED"

    def test_linked_phone_succeeds(self, settings):
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"

        tg_user_id = uuid.uuid4().int % 900000000
        phone = f"+99890{uuid.uuid4().int % 10000000:07d}"
        identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=phone, status="active", telegram_user_id=tg_user_id, full_name="Ali Karimov")

        client = Client()
        with patch("apps.notifications.infrastructure.gateways.LiveTelegramGateway.send_message_with_keyboard", return_value=None):
            response = client.post("/api/v1/identity/auth/request-telegram-code", data=json.dumps({"phone_number": phone}), content_type="application/json")
        assert response.status_code == 202


class TestTelegramWrongUserProtection:
    def test_a_different_telegram_user_cannot_confirm_someone_elses_session(self, settings):
        """Real, serious security bug found and fixed this phase: the docstring already claimed "wrong-user protection" (session.telegram_user_id must match the confirming sender), but the check was never actually implemented -- session.telegram_user_id was unconditionally overwritten by whoever pressed Confirm, with no comparison against who pressed /start. Confirmed exploitable live before the fix: a second Telegram user's callback_query silently hijacked the first user's session and would have issued them JWT tokens for the wrong account."""
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_BOT_USERNAME = "nutrizone_test_bot"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"

        user_a_tg_id = uuid.uuid4().int % 900000000
        user_b_tg_id = uuid.uuid4().int % 900000000
        identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", status="active", telegram_user_id=user_a_tg_id, full_name="User A")
        identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", status="active", telegram_user_id=user_b_tg_id, full_name="User B (attacker)")

        client = Client()
        create_response = client.post("/api/v1/identity/auth/telegram/session", data=json.dumps({}), content_type="application/json")
        session_body = json.loads(create_response.content)["data"]
        session_id = session_body["session_id"]
        raw_token = session_body["telegram_url"].split("start=")[1]
        webhook_auth = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": "test-webhook-secret"}

        with patch("apps.telegram_bot.interfaces.api.v1.views._reply_text"), patch("apps.telegram_bot.interfaces.callback_router._send"), patch("apps.telegram_bot.interfaces.api.v1.views._answer_callback_query"):
            start_update = {"update_id": 1, "message": {"message_id": 1, "chat": {"id": user_a_tg_id, "type": "private"}, "from": {"id": user_a_tg_id, "first_name": "A"}, "text": f"/start {raw_token}"}}
            client.post("/api/v1/telegram/webhook", data=json.dumps(start_update), content_type="application/json", **webhook_auth)

            session = identity_orm.TelegramAuthSession.objects.get(id=session_id)
            assert session.telegram_user_id == user_a_tg_id

            attacker_confirm = {"update_id": 2, "callback_query": {"id": "cbq1", "from": {"id": user_b_tg_id}, "message": {"chat": {"id": user_b_tg_id}}, "data": f"authlogin:confirm:{session_id}"}}
            client.post("/api/v1/telegram/webhook", data=json.dumps(attacker_confirm), content_type="application/json", **webhook_auth)

            session.refresh_from_db()
            assert session.status == "pending"
            assert session.user_id is None

            real_confirm = {"update_id": 3, "callback_query": {"id": "cbq2", "from": {"id": user_a_tg_id}, "message": {"chat": {"id": user_a_tg_id}}, "data": f"authlogin:confirm:{session_id}"}}
            client.post("/api/v1/telegram/webhook", data=json.dumps(real_confirm), content_type="application/json", **webhook_auth)
            session.refresh_from_db()
            assert session.status == "verified"


class TestStartLoginPayloadRouting:
    """Real, business-required behavior: "/start login" (the website's own "Open Telegram Bot" deep link) is now treated EXACTLY like a plain /start with no payload -- it must never generate or send the website OTP. The only action that ever does is the customer explicitly pressing "Sayt uchun kod olish" (menu:getcode)."""

    def test_start_login_for_an_unlinked_user_begins_language_selection_not_an_invalid_link_error(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"

        tg_user_id = uuid.uuid4().int % 900000000
        client = Client()
        webhook_auth = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": "test-webhook-secret"}

        with patch("apps.telegram_bot.interfaces.callback_router._send") as mock_send:
            update = {"update_id": 1, "message": {"message_id": 1, "chat": {"id": tg_user_id, "type": "private"}, "from": {"id": tg_user_id}, "text": "/start login"}}
            response = client.post("/api/v1/telegram/webhook", data=json.dumps(update), content_type="application/json", **webhook_auth)

        assert response.status_code == 200
        assert mock_send.called
        sent_text = mock_send.call_args[0][1]
        assert "yaroqsiz" not in sent_text.lower()  # never the stale-token error for this payload

        from apps.telegram_bot.interfaces import onboarding_state

        state = onboarding_state.get_state(tg_user_id)
        assert state is not None
        assert state["step"] == "awaiting_language"

    def test_start_login_for_a_linked_user_never_sends_a_login_code(self, settings):
        """
        Regression test for the actual reported bug: an already
        registered customer arriving via "/start login" -- the
        website's single "Continue with Telegram" button's deep link
        -- must land on the exact same main menu a bare "/start"
        would show, never an automatically-sent 6-digit code. A prior
        version of this test asserted the opposite (the bug itself,
        codified as "intended" behavior) -- login-code generation must
        be reachable ONLY via an explicit "Sayt uchun kod olish" /
        "Yangi kod olish" press (menu:getcode), never from `/start`
        under any payload.
        """
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"

        tg_user_id = uuid.uuid4().int % 900000000
        phone = f"+99890{uuid.uuid4().int % 10000000:07d}"
        identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=phone, status="active", telegram_user_id=tg_user_id, full_name="Real User", language="uz")

        client = Client()
        webhook_auth = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": "test-webhook-secret"}

        with patch("apps.telegram_bot.interfaces.callback_router.send_login_code") as mock_send_code, \
                patch("apps.telegram_bot.interfaces.callback_router.send_main_menu") as mock_send_menu:
            update = {"update_id": 1, "message": {"message_id": 1, "chat": {"id": tg_user_id, "type": "private"}, "from": {"id": tg_user_id}, "text": "/start login"}}
            response = client.post("/api/v1/telegram/webhook", data=json.dumps(update), content_type="application/json", **webhook_auth)

        assert response.status_code == 200
        assert not mock_send_code.called
        assert mock_send_menu.called

    def test_plain_start_for_a_linked_user_still_shows_the_main_menu_not_the_code(self, settings):
        """The other half of the same behavior change: a bare "/start" (no "login" payload) must still show the main menu, never jump straight to sending a code -- only the website's own explicit deep link does that."""
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"

        tg_user_id = uuid.uuid4().int % 900000000
        phone = f"+99890{uuid.uuid4().int % 10000000:07d}"
        identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=phone, status="active", telegram_user_id=tg_user_id, full_name="Real User", language="uz")

        client = Client()
        webhook_auth = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": "test-webhook-secret"}

        with patch("apps.telegram_bot.interfaces.callback_router.send_login_code") as mock_send_code, \
                patch("apps.telegram_bot.interfaces.callback_router.send_main_menu") as mock_send_menu:
            update = {"update_id": 1, "message": {"message_id": 1, "chat": {"id": tg_user_id, "type": "private"}, "from": {"id": tg_user_id}, "text": "/start"}}
            response = client.post("/api/v1/telegram/webhook", data=json.dumps(update), content_type="application/json", **webhook_auth)

        assert response.status_code == 200
        assert not mock_send_code.called
        assert mock_send_menu.called


class TestOTPResendTooSoonNeverCrashesTheWebhook:
    """Real bug fix: send_login_code only caught OTPDeliveryFailedError -- OTPResendTooSoonError (raised on a too-quick second code request) could escape uncaught and crash the webhook."""

    def test_requesting_a_code_twice_quickly_returns_200_with_a_friendly_message(self, settings):
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"
        settings.NUTRIZONE_TELEGRAM_GATEWAY = "live"

        tg_user_id = uuid.uuid4().int % 900000000
        phone = f"+99890{uuid.uuid4().int % 10000000:07d}"
        identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=phone, status="active", telegram_user_id=tg_user_id, full_name="Real User")

        client = Client()
        webhook_auth = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": "test-webhook-secret"}
        update = {"update_id": 1, "callback_query": {"id": "cbq1", "from": {"id": tg_user_id}, "message": {"chat": {"id": tg_user_id}}, "data": "menu:getcode"}}

        with patch("apps.notifications.infrastructure.gateways.LiveTelegramGateway.send_message_with_keyboard", return_value=None), \
                patch("apps.telegram_bot.interfaces.api.v1.views._answer_callback_query"):
            client.post("/api/v1/telegram/webhook", data=json.dumps(update), content_type="application/json", **webhook_auth)

            with patch("apps.telegram_bot.interfaces.callback_router._send") as mock_send_reply:
                second_response = client.post("/api/v1/telegram/webhook", data=json.dumps(update), content_type="application/json", **webhook_auth)

        assert second_response.status_code == 200  # never a 500 from an uncaught OTPResendTooSoonError
        assert mock_send_reply.called
        sent_text = mock_send_reply.call_args[0][1]
        assert any(word in sent_text.lower() for word in ("wait", "kut", "подожд"))


class TestOTPMaxAttemptsNeverCrashesTheWebhook:
    """
    Real bug fix, the exact root cause of the "Texnik xatolik yuz
    berdi" (technical error) message customers saw immediately after
    a login code was already sent successfully via "Sayt uchun kod
    olish": send_login_code caught OTPResendTooSoonError and
    OTPDeliveryFailedError, but OTPPolicy.assert_within_hourly_quota
    raises a third, distinct exception (OTPMaxAttemptsExceededError)
    once OTP_MAX_REQUESTS_PER_HOUR requests have already gone out for
    a phone number -- that exception escaped uncaught into
    handle_callback()'s own generic `except Exception`, which logged
    it and sent the opaque, unhelpful technical_error message even
    though nothing was actually broken.
    """

    def test_exceeding_the_hourly_quota_returns_200_with_a_friendly_message_not_a_technical_error(self, settings):
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"
        settings.NUTRIZONE_TELEGRAM_GATEWAY = "live"

        from apps.identity.domain.services import OTP_MAX_REQUESTS_PER_HOUR
        from apps.identity.infrastructure import models as id_orm

        tg_user_id = uuid.uuid4().int % 900000000
        phone = f"+99890{uuid.uuid4().int % 10000000:07d}"
        identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=phone, status="active", telegram_user_id=tg_user_id, full_name="Real User")

        # Pre-seed OTP_MAX_REQUESTS_PER_HOUR already-requested challenges for
        # this phone number so the very next request trips the hourly cap
        # deterministically, without needing OTP_RESEND_COOLDOWN_SECONDS to
        # also elapse between them.
        from datetime import timedelta

        from django.utils import timezone as django_timezone

        for _ in range(OTP_MAX_REQUESTS_PER_HOUR):
            id_orm.OTPCodeChallenge.objects.create(
                phone_number=phone, code_hash=uuid.uuid4().hex, expires_at=django_timezone.now() - timedelta(seconds=1),
            )

        client = Client()
        webhook_auth = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": "test-webhook-secret"}
        update = {"update_id": 1, "callback_query": {"id": "cbq1", "from": {"id": tg_user_id}, "message": {"chat": {"id": tg_user_id}}, "data": "menu:getcode"}}

        with patch("apps.notifications.infrastructure.gateways.LiveTelegramGateway.send_message", return_value=None), \
                patch("apps.telegram_bot.interfaces.api.v1.views._answer_callback_query"), \
                patch("apps.telegram_bot.interfaces.callback_router._send") as mock_send_reply:
            response = client.post("/api/v1/telegram/webhook", data=json.dumps(update), content_type="application/json", **webhook_auth)

        assert response.status_code == 200  # never a technical_error from an uncaught OTPMaxAttemptsExceededError
        assert mock_send_reply.called
        sent_text = mock_send_reply.call_args[0][1]
        assert "texnik xatolik" not in sent_text.lower()
        assert any(word in sent_text.lower() for word in ("ko'p", "many", "много"))


class TestTelegramOnboardingAsksForFullName:
    def test_full_onboarding_flow_uses_typed_name_not_telegram_profile(self, settings):
        """Real gap closed this phase: the bot previously took full_name silently from Telegram's own first_name/last_name (often incomplete/informal) instead of asking the user to type it, as explicitly required."""
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"
        settings.NUTRIZONE_TELEGRAM_GATEWAY = "live"

        tg_user_id = uuid.uuid4().int % 900000000
        client = Client()
        webhook_auth = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": "test-webhook-secret"}

        with patch("apps.telegram_bot.interfaces.callback_router._send") as mock_send, \
                patch("apps.notifications.infrastructure.gateways.LiveTelegramGateway.send_contact_request", return_value="1") as mock_contact:
            start_update = {"update_id": 1, "message": {"message_id": 1, "chat": {"id": tg_user_id, "type": "private"}, "from": {"id": tg_user_id, "first_name": "TelegramProfileFirstName"}, "text": "/start"}}
            client.post("/api/v1/telegram/webhook", data=json.dumps(start_update), content_type="application/json", **webhook_auth)
            assert mock_send.called  # language selection shown

            lang_update = {"update_id": 2, "callback_query": {"id": "cbq1", "from": {"id": tg_user_id}, "message": {"chat": {"id": tg_user_id}}, "data": "onboarding:lang:uz"}}
            with patch("apps.telegram_bot.interfaces.api.v1.views._answer_callback_query"):
                client.post("/api/v1/telegram/webhook", data=json.dumps(lang_update), content_type="application/json", **webhook_auth)

            name_update = {"update_id": 3, "message": {"message_id": 3, "chat": {"id": tg_user_id, "type": "private"}, "from": {"id": tg_user_id}, "text": "Sardor Aliyev"}}
            client.post("/api/v1/telegram/webhook", data=json.dumps(name_update), content_type="application/json", **webhook_auth)
            assert mock_contact.called
            assert "Sardor Aliyev" in mock_contact.call_args[0][1]

            contact_update = {
                "update_id": 4,
                "message": {"message_id": 4, "chat": {"id": tg_user_id, "type": "private"}, "from": {"id": tg_user_id, "first_name": "TelegramProfileFirstName"},
                            "contact": {"phone_number": f"99890{uuid.uuid4().int % 10000000:07d}", "user_id": tg_user_id}},
            }
            client.post("/api/v1/telegram/webhook", data=json.dumps(contact_update), content_type="application/json", **webhook_auth)

            # Real, business-required behavior: the account is not created on contact share alone -- must explicitly confirm.
            confirm_update = {"update_id": 5, "callback_query": {"id": "cbq2", "from": {"id": tg_user_id}, "message": {"chat": {"id": tg_user_id}}, "data": "onboarding:confirm"}}
            with patch("apps.telegram_bot.interfaces.api.v1.views._answer_callback_query"):
                client.post("/api/v1/telegram/webhook", data=json.dumps(confirm_update), content_type="application/json", **webhook_auth)

        user = identity_orm.User.objects.filter(telegram_user_id=tg_user_id).first()
        assert user is not None
        assert user.full_name == "Sardor Aliyev"
        assert user.full_name != "TelegramProfileFirstName"

    def test_too_short_name_is_rejected_and_reasked(self, settings):
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"

        tg_user_id = uuid.uuid4().int % 900000000
        client = Client()
        webhook_auth = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": "test-webhook-secret"}

        with patch("apps.telegram_bot.interfaces.callback_router._send") as mock_send, \
                patch("apps.telegram_bot.interfaces.api.v1.views._reply_text") as mock_reply, \
                patch("apps.notifications.infrastructure.gateways.LiveTelegramGateway.send_contact_request") as mock_contact:
            start_update = {"update_id": 1, "message": {"message_id": 1, "chat": {"id": tg_user_id, "type": "private"}, "from": {"id": tg_user_id}, "text": "/start"}}
            client.post("/api/v1/telegram/webhook", data=json.dumps(start_update), content_type="application/json", **webhook_auth)

            lang_update = {"update_id": 2, "callback_query": {"id": "cbq1", "from": {"id": tg_user_id}, "message": {"chat": {"id": tg_user_id}}, "data": "onboarding:lang:uz"}}
            with patch("apps.telegram_bot.interfaces.api.v1.views._answer_callback_query"):
                client.post("/api/v1/telegram/webhook", data=json.dumps(lang_update), content_type="application/json", **webhook_auth)

            short_name_update = {"update_id": 3, "message": {"message_id": 3, "chat": {"id": tg_user_id, "type": "private"}, "from": {"id": tg_user_id}, "text": "A"}}
            client.post("/api/v1/telegram/webhook", data=json.dumps(short_name_update), content_type="application/json", **webhook_auth)

        assert not mock_contact.called
        assert mock_send.called  # language selection shown
        assert mock_reply.called  # too-short rejection shown, never silently proceeds


class TestTelegramMainMenuButtons:
    """Real, live-verified regression test for Phase 5: the bot's own main menu expanded from 3 buttons to the full 10 requested (auto-login, get-code, products, categories, brands, stores, cart, orders, social links, chat) plus language."""

    def test_products_button_shows_the_submenu_not_a_flat_product_list(self, settings):
        """Real, product-required upgrade (premium mini-store phase): "📦 Mahsulotlar" used to dump the newest products directly. Now shows the Best Sellers/New/All entry-point sub-menu -- no product data at all in this first screen."""
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"

        tg_user_id = uuid.uuid4().int % 900000000
        identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", status="active", telegram_user_id=tg_user_id, full_name="Test", language="uz")

        client = Client()
        webhook_auth = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": "test-webhook-secret"}
        with patch("apps.telegram_bot.interfaces.callback_router._send") as mock_send, patch("apps.telegram_bot.interfaces.api.v1.views._answer_callback_query"):
            update = {"update_id": 1, "callback_query": {"id": "cbq1", "from": {"id": tg_user_id}, "message": {"chat": {"id": tg_user_id}}, "data": "menu:products"}}
            response = client.post("/api/v1/telegram/webhook", data=json.dumps(update), content_type="application/json", **webhook_auth)
            assert response.status_code == 200
            keyboard = mock_send.call_args[0][2]
            callback_data_values = [button["callback_data"] for row in keyboard for button in row]
            assert "pm:best" in callback_data_values
            assert "pm:new" in callback_data_values
            assert "pm:all" in callback_data_values

    def test_all_products_entry_shows_the_real_product_as_a_single_card(self, settings):
        """"pm:all" is the real replacement for the old flat list -- one real product, one message, real name/price-pending (no PriceListEntry exists in this test), never a fabricated value."""
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"

        tg_user_id = uuid.uuid4().int % 900000000
        identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", status="active", telegram_user_id=tg_user_id, full_name="Test", language="uz")

        product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="uz", name="Menu Test Product", slug=f"mtp-{uuid.uuid4().hex[:6]}")
        p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku="MTP-1", status="active", is_default=True)

        client = Client()
        webhook_auth = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": "test-webhook-secret"}
        with patch("apps.telegram_bot.interfaces.callback_router._send") as mock_send, patch("apps.telegram_bot.interfaces.api.v1.views._answer_callback_query"):
            update = {"update_id": 1, "callback_query": {"id": "cbq1", "from": {"id": tg_user_id}, "message": {"chat": {"id": tg_user_id}}, "data": "pm:all"}}
            response = client.post("/api/v1/telegram/webhook", data=json.dumps(update), content_type="application/json", **webhook_auth)
            assert response.status_code == 200
            assert "Menu Test Product" in str(mock_send.call_args)

    def test_brands_button_filters_out_untranslated_blank_names(self, settings):
        """Real bug found and fixed this phase: BrandSelector.list_active() returns an empty name for a brand with no translation in the active locale -- rendering that as a blank, useless bot menu button. Now filtered out entirely."""
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"

        tg_user_id = uuid.uuid4().int % 900000000
        identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", status="active", telegram_user_id=tg_user_id, full_name="Test", language="uz")

        named_brand = p_models.Brand.objects.create(id=uuid.uuid4())
        p_models.BrandTranslation.objects.create(id=uuid.uuid4(), brand=named_brand, locale_code="en", name="Named Brand", slug=f"nb-{uuid.uuid4().hex[:6]}")
        p_models.Brand.objects.create(id=uuid.uuid4())  # no translation at all -- would previously render as a blank button

        client = Client()
        webhook_auth = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": "test-webhook-secret"}
        with patch("apps.telegram_bot.interfaces.callback_router._send") as mock_send, patch("apps.telegram_bot.interfaces.api.v1.views._answer_callback_query"):
            update = {"update_id": 1, "callback_query": {"id": "cbq1", "from": {"id": tg_user_id}, "message": {"chat": {"id": tg_user_id}}, "data": "menu:brands"}}
            client.post("/api/v1/telegram/webhook", data=json.dumps(update), content_type="application/json", **webhook_auth)
            keyboard = mock_send.call_args[0][2]
            button_texts = [row[0]["text"] for row in keyboard]
            assert "Named Brand" in button_texts
            assert "" not in button_texts

    def test_autologin_button_creates_verified_session_with_real_frontend_link(self, settings):
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"
        settings.FRONTEND_URL = "https://nutrizone.uz"

        tg_user_id = uuid.uuid4().int % 900000000
        identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", status="active", telegram_user_id=tg_user_id, full_name="Test", language="uz")

        client = Client()
        webhook_auth = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": "test-webhook-secret"}
        with patch("apps.telegram_bot.interfaces.callback_router._send") as mock_send, patch("apps.telegram_bot.interfaces.api.v1.views._answer_callback_query"):
            update = {"update_id": 1, "callback_query": {"id": "cbq1", "from": {"id": tg_user_id}, "message": {"chat": {"id": tg_user_id}}, "data": "menu:autologin"}}
            client.post("/api/v1/telegram/webhook", data=json.dumps(update), content_type="application/json", **webhook_auth)
            assert "nutrizone.uz/auto-login" in str(mock_send.call_args)

        session = identity_orm.TelegramAuthSession.objects.filter(telegram_user_id=tg_user_id).first()
        assert session is not None
        assert session.status == "verified"

    def test_getcode_button_triggers_real_otp_delivery(self, settings):
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"

        tg_user_id = uuid.uuid4().int % 900000000
        identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", status="active", telegram_user_id=tg_user_id, full_name="Test", language="uz")

        client = Client()
        webhook_auth = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": "test-webhook-secret"}
        with patch("apps.telegram_bot.interfaces.callback_router._send"), patch("apps.telegram_bot.interfaces.api.v1.views._answer_callback_query"), \
                patch("apps.notifications.infrastructure.gateways.LiveTelegramGateway.send_message_with_keyboard", return_value="1") as mock_otp:
            update = {"update_id": 1, "callback_query": {"id": "cbq1", "from": {"id": tg_user_id}, "message": {"chat": {"id": tg_user_id}}, "data": "menu:getcode"}}
            response = client.post("/api/v1/telegram/webhook", data=json.dumps(update), content_type="application/json", **webhook_auth)
            assert response.status_code == 200
            assert mock_otp.called


class TestTelegramSetWebhookCommand:
    def _mock_get_webhook_info(self, current_url: str = "", allowed_updates=None):
        """A getWebhookInfo response reporting some OTHER (or no) currently-registered URL, so the command's own already-registered short-circuit doesn't apply and it proceeds to call setWebhook, per the scenario each test below is actually testing."""
        from apps.telegram_bot.management.commands.telegram_set_webhook import ALLOWED_UPDATES

        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True, "result": {"url": current_url, "allowed_updates": ALLOWED_UPDATES if allowed_updates is None else allowed_updates}}
        return mock_response

    def test_successful_registration_calls_real_telegram_api_shape(self, settings):
        settings.TELEGRAM_API_BASE_URL = "https://api.telegram.org"  # the real shape (testing.py points the suite at a dead local port)
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-secret"
        settings.PUBLIC_BASE_URL = "https://api.nutrizone.uz"

        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True, "result": True, "description": "Webhook was set"}
        with patch("requests.get", return_value=self._mock_get_webhook_info()), patch("requests.post", return_value=mock_response) as mock_post:
            call_command("telegram_set_webhook")
            call_args = mock_post.call_args
            assert "api.telegram.org/bot123456:TEST-TOKEN/setWebhook" in call_args[0][0]
            assert call_args[1]["json"]["url"] == "https://api.nutrizone.uz/api/v1/telegram/webhook"
            assert call_args[1]["json"]["secret_token"] == "test-secret"

    def test_already_registered_webhook_skips_the_real_api_call(self, settings):
        """
        Real, closed production bug: this command previously called
        setWebhook unconditionally on every invocation -- with several
        gunicorn workers (or a `runserver` dev-server reload) each
        starting AppConfig.ready()'s auto-registration thread, several
        redundant setWebhook calls landed on Telegram within the same
        couple of seconds, and Telegram's own API throttled them with
        the exact production error "Too Many Requests: retry after N".
        When the webhook is already correctly registered (the
        overwhelming majority of real restarts), setWebhook must never
        be called at all.
        """
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-secret"
        settings.PUBLIC_BASE_URL = "https://api.nutrizone.uz"

        with patch("requests.get", return_value=self._mock_get_webhook_info("https://api.nutrizone.uz/api/v1/telegram/webhook")), patch("requests.post") as mock_post:
            call_command("telegram_set_webhook")
            mock_post.assert_not_called()

    def test_same_url_without_inline_queries_is_re_registered(self, settings):
        """A webhook registered before inline mode (no "inline_query" in allowed_updates) must be updated, not skipped."""
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-secret"
        settings.PUBLIC_BASE_URL = "https://api.nutrizone.uz"

        ok = MagicMock()
        ok.json.return_value = {"ok": True}
        with patch("requests.get", return_value=self._mock_get_webhook_info("https://api.nutrizone.uz/api/v1/telegram/webhook", ["message", "callback_query"])), \
                patch("requests.post", return_value=ok) as mock_post:
            call_command("telegram_set_webhook")
        assert "inline_query" in mock_post.call_args[1]["json"]["allowed_updates"]

    def test_telegram_api_rejection_raises_command_error(self, settings):
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-secret"
        settings.PUBLIC_BASE_URL = "https://api.nutrizone.uz"

        from django.core.management.base import CommandError

        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": False, "description": "Unauthorized"}
        with patch("requests.get", return_value=self._mock_get_webhook_info()), patch("requests.post", return_value=mock_response), pytest.raises(CommandError, match="Unauthorized"):
            call_command("telegram_set_webhook")

    def test_missing_bot_token_raises_command_error(self, settings):
        settings.TELEGRAM_BOT_TOKEN = None

        from django.core.management.base import CommandError

        with pytest.raises(CommandError, match="TELEGRAM_BOT_TOKEN"):
            call_command("telegram_set_webhook")

    def test_getwebhookinfo_failure_does_not_block_registration(self, settings):
        """A transient getWebhookInfo failure (network hiccup, Telegram outage) must never prevent the real registration from proceeding -- unknown current state falls back to registering."""
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-secret"
        settings.PUBLIC_BASE_URL = "https://api.nutrizone.uz"

        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True, "result": True, "description": "Webhook was set"}
        with patch("requests.get", side_effect=ConnectionError("network down")), patch("requests.post", return_value=mock_response) as mock_post:
            call_command("telegram_set_webhook")
            mock_post.assert_called_once()

    def test_concurrent_registration_is_serialized_by_a_short_lock(self, settings):
        """The second real fix layer: even a genuinely new/changed URL must not let multiple concurrent processes all call setWebhook together -- only the lock winner does."""
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-secret"
        settings.PUBLIC_BASE_URL = "https://api.nutrizone.uz"

        from core.caching.redis_client import cache_key, get_redis_client

        lock_key = cache_key("https://api.nutrizone.uz/api/v1/telegram/webhook", namespace="telegram_bot:webhook_registration_lock")
        client = get_redis_client()
        client.delete(lock_key)
        try:
            client.set(lock_key, "1", nx=True, ex=30)  # simulates a concurrent process that already won the race
            with patch("requests.get", return_value=self._mock_get_webhook_info()), patch("requests.post") as mock_post:
                call_command("telegram_set_webhook")
                mock_post.assert_not_called()
        finally:
            client.delete(lock_key)


class TestTelegramWebhookAutoRegistrationSafety:
    def test_does_not_start_a_thread_for_a_non_server_command(self, settings):
        """Real safety guarantee: `ready()` fires on every management command (migrate/test/shell/...), not just the real server process -- this must never fire a real network call during those."""
        import sys
        import threading

        from django.apps import apps

        settings.TELEGRAM_AUTO_SET_WEBHOOK = True
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.PUBLIC_BASE_URL = "https://api.nutrizone.uz"

        config = apps.get_app_config("telegram_bot")
        original_argv = sys.argv
        try:
            sys.argv = ["manage.py", "test"]
            before = threading.active_count()
            config._maybe_auto_register_webhook()
            assert threading.active_count() == before
        finally:
            sys.argv = original_argv

    def test_does_nothing_when_not_opted_in(self, settings):
        import threading

        from django.apps import apps

        settings.TELEGRAM_AUTO_SET_WEBHOOK = False
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.PUBLIC_BASE_URL = "https://api.nutrizone.uz"

        config = apps.get_app_config("telegram_bot")
        before = threading.active_count()
        config._maybe_auto_register_webhook()
        assert threading.active_count() == before

    def test_the_channels_service_uvicorn_does_not_also_register_the_webhook(self, settings):
        """Real bug fix: "uvicorn" was previously in the real-server-command allowlist, so BOTH web (runserver/gunicorn) and channels (uvicorn, per docker-compose.yml's own `command: ["uvicorn", ...]`) would independently call setWebhook on startup -- Telegram rejects the second, redundant call with "Too Many Requests". Only "web" registers the webhook now; uvicorn/daphne/uwsgi are excluded."""
        import sys
        import threading

        from django.apps import apps

        settings.TELEGRAM_AUTO_SET_WEBHOOK = True
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.PUBLIC_BASE_URL = "https://api.nutrizone.uz"

        config = apps.get_app_config("telegram_bot")
        original_argv = sys.argv
        try:
            # Mirrors docker-compose.yml's real channels command: ["uvicorn", "config.asgi:application", ...]
            sys.argv = ["/usr/local/bin/uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8001"]
            before = threading.active_count()
            config._maybe_auto_register_webhook()
            assert threading.active_count() == before  # no registration thread started
        finally:
            sys.argv = original_argv


class TestAllMainMenuButtonsAreFunctional:
    """Real, product-required completeness check: every one of the 10 main-menu buttons must return 200 and never crash the webhook, for a real linked user, in a single pass through the actual callback router (no per-button mocking of internal logic -- only the outbound Telegram send calls are mocked)."""

    def test_every_main_menu_button_returns_200_without_crashing(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"

        chat_id = uuid.uuid4().int % 900000000
        tg_user_id = uuid.uuid4().int % 900000000
        phone = f"+99890{uuid.uuid4().int % 10000000:07d}"
        identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=phone, full_name="Menu Coverage User", status="active", telegram_user_id=tg_user_id, language="uz")

        client = Client()
        webhook_auth = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": "test-webhook-secret"}
        buttons = ["autologin", "getcode", "products", "catalog", "brands", "cart", "orders", "social", "chat", "lang"]

        with patch("apps.notifications.infrastructure.gateways.LiveTelegramGateway.send_message_with_keyboard"), \
                patch("apps.notifications.infrastructure.gateways.LiveTelegramGateway.send_message"), \
                patch("apps.telegram_bot.interfaces.api.v1.views._answer_callback_query"):
            for idx, action in enumerate(buttons):
                update = {"update_id": idx, "callback_query": {"id": f"mcov{idx}", "from": {"id": tg_user_id}, "message": {"chat": {"id": chat_id}}, "data": f"menu:{action}"}}
                response = client.post("/api/v1/telegram/webhook", data=json.dumps(update), content_type="application/json", **webhook_auth)
                assert response.status_code == 200, f"menu:{action} did not return 200"
