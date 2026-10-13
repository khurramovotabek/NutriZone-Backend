"""
Real, live-verified regression test for the Django System Check
Framework hooks that surface Telegram misconfiguration loudly at
deploy time. Root-cause fix for a genuine silent-failure mode: with
SMS login disabled by default, a missing TELEGRAM_BOT_TOKEN/USERNAME
previously meant "Continue with Telegram" created a session
successfully (HTTP 201) but returned telegram_url=null, with zero
visible signal of why.
"""
from __future__ import annotations

import pytest
from django.test import override_settings

from apps.telegram_bot.checks import check_telegram_auth_is_configured

pytestmark = pytest.mark.django_db


class TestTelegramConfigChecks:
    def test_missing_token_and_username_raise_errors_when_sms_is_disabled(self):
        with override_settings(NUTRIZONE_SMS_LOGIN_ENABLED=False, TELEGRAM_BOT_TOKEN=None, TELEGRAM_BOT_USERNAME=None):
            errors = check_telegram_auth_is_configured(None)
        ids = [e.id for e in errors]
        assert "telegram_bot.E001" in ids
        assert "telegram_bot.E002" in ids

    def test_no_errors_when_sms_login_is_enabled_as_a_fallback(self):
        with override_settings(NUTRIZONE_SMS_LOGIN_ENABLED=True, TELEGRAM_BOT_TOKEN=None, TELEGRAM_BOT_USERNAME=None):
            errors = check_telegram_auth_is_configured(None)
        ids = [e.id for e in errors]
        assert "telegram_bot.E001" not in ids
        assert "telegram_bot.E002" not in ids

    def test_no_errors_when_fully_and_correctly_configured(self):
        with override_settings(
            NUTRIZONE_SMS_LOGIN_ENABLED=False,
            TELEGRAM_BOT_TOKEN="123:TEST",
            TELEGRAM_BOT_USERNAME="test_bot",
            TELEGRAM_WEBHOOK_SECRET="real-secret",
            FRONTEND_URL="https://nutrizone.uz",
        ):
            errors = check_telegram_auth_is_configured(None)
        assert errors == []

    def test_missing_webhook_secret_is_a_warning_regardless_of_sms_setting(self):
        with override_settings(NUTRIZONE_SMS_LOGIN_ENABLED=True, TELEGRAM_WEBHOOK_SECRET=None):
            errors = check_telegram_auth_is_configured(None)
        ids = [e.id for e in errors]
        assert "telegram_bot.W001" in ids

    def test_missing_frontend_url_is_a_warning(self):
        """Real bug fix: a missing FRONTEND_URL previously failed silently -- the bot's "Saytga avtomatik kirish" button would just show the customer a bare technical-error message with no diagnosable cause anywhere in `manage.py check` output."""
        with override_settings(NUTRIZONE_SMS_LOGIN_ENABLED=False, FRONTEND_URL=None):
            errors = check_telegram_auth_is_configured(None)
        ids = [e.id for e in errors]
        assert "telegram_bot.W002" in ids
        assert "telegram_bot.W003" not in ids

    def test_frontend_url_pointing_at_a_dev_tunnel_domain_is_a_warning(self):
        """
        Real, live-observed misconfiguration this check exists to catch:
        FRONTEND_URL left pointing at a throwaway cloudflared tunnel
        domain from local testing -- every customer who presses "Saytga
        avtomatik kirish" gets a login link that stops resolving the
        moment that tunnel is closed.
        """
        with override_settings(NUTRIZONE_SMS_LOGIN_ENABLED=False, FRONTEND_URL="https://affecting-back-classifieds-sought.trycloudflare.com"):
            errors = check_telegram_auth_is_configured(None)
        ids = [e.id for e in errors]
        assert "telegram_bot.W003" in ids
        assert "telegram_bot.W002" not in ids

    def test_missing_frontend_url_warns_even_when_sms_login_is_enabled(self):
        """The bot's "Saytga avtomatik kirish" button is shown unconditionally in the main menu (see callback_router._main_menu_keyboard) -- SMS being available as a fallback login method doesn't make that button work without FRONTEND_URL."""
        with override_settings(NUTRIZONE_SMS_LOGIN_ENABLED=True, FRONTEND_URL=None):
            errors = check_telegram_auth_is_configured(None)
        ids = [e.id for e in errors]
        assert "telegram_bot.W002" in ids

    def test_real_production_frontend_url_raises_no_warning(self):
        with override_settings(NUTRIZONE_SMS_LOGIN_ENABLED=False, FRONTEND_URL="https://nutrizone.uz", TELEGRAM_BOT_TOKEN="123:TEST", TELEGRAM_BOT_USERNAME="test_bot", TELEGRAM_WEBHOOK_SECRET="real-secret"):
            errors = check_telegram_auth_is_configured(None)
        assert errors == []


class TestOrdersBotConfigChecks:
    """Phase 15F: the separate Orders Bot's own config checks -- only fire when the Orders Channel feature is actually opted into (TELEGRAM_ORDERS_CHAT_ID set), matching sync_orders_channel()'s own inactive-when-blank gate."""

    def test_no_warnings_when_orders_channel_is_not_configured_at_all(self):
        with override_settings(TELEGRAM_ORDERS_CHAT_ID="", TELEGRAM_ORDERS_BOT_TOKEN=None, TELEGRAM_ORDERS_WEBHOOK_SECRET=None):
            errors = check_telegram_auth_is_configured(None)
        ids = [e.id for e in errors]
        assert "telegram_bot.W004" not in ids
        assert "telegram_bot.W005" not in ids

    def test_missing_orders_bot_token_warns_once_channel_is_configured(self):
        with override_settings(TELEGRAM_ORDERS_CHAT_ID="-100999888", TELEGRAM_ORDERS_BOT_TOKEN=None, TELEGRAM_ORDERS_WEBHOOK_SECRET="real-secret"):
            errors = check_telegram_auth_is_configured(None)
        ids = [e.id for e in errors]
        assert "telegram_bot.W004" in ids
        assert "telegram_bot.W005" not in ids

    def test_missing_orders_webhook_secret_warns_once_channel_is_configured(self):
        with override_settings(TELEGRAM_ORDERS_CHAT_ID="-100999888", TELEGRAM_ORDERS_BOT_TOKEN="999:TEST", TELEGRAM_ORDERS_WEBHOOK_SECRET=None):
            errors = check_telegram_auth_is_configured(None)
        ids = [e.id for e in errors]
        assert "telegram_bot.W005" in ids
        assert "telegram_bot.W004" not in ids

    def test_no_warnings_when_orders_bot_is_fully_configured(self):
        with override_settings(
            NUTRIZONE_SMS_LOGIN_ENABLED=False, FRONTEND_URL="https://nutrizone.uz",
            TELEGRAM_BOT_TOKEN="123:TEST", TELEGRAM_BOT_USERNAME="test_bot", TELEGRAM_WEBHOOK_SECRET="real-secret",
            TELEGRAM_ORDERS_CHAT_ID="-100999888", TELEGRAM_ORDERS_BOT_TOKEN="999:TEST", TELEGRAM_ORDERS_WEBHOOK_SECRET="orders-real-secret",
        ):
            errors = check_telegram_auth_is_configured(None)
        assert errors == []
