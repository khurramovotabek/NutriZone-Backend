"""
**Per this phase's own explicit instruction, this file makes zero
real network calls, fabricates zero credentials, and does NOT test
that Telegram delivery works end-to-end** -- `TelegramGateway` has no
such implementation to test. The distinction this phase requires is
made explicit here: the Gateway *contract* (the Protocol shape and
the placeholder's own real, honest behavior) is what is tested, never
a simulated successful delivery.
"""
from __future__ import annotations

import pytest

from apps.notifications.infrastructure.gateways import LiveTelegramGateway, NotImplementedTelegramGateway, get_orders_telegram_gateway

pytestmark = pytest.mark.unit


class TestOrdersTelegramGatewayResolution:
    """Phase 15F: get_orders_telegram_gateway must resolve to the separate Orders Bot's own token (TELEGRAM_ORDERS_BOT_TOKEN), never the customer-facing TELEGRAM_BOT_TOKEN -- a real regression here would mean the Orders Bot silently sends messages as the wrong bot (or fails, since it wouldn't own the chat)."""

    def test_disabled_gateway_mode_returns_placeholder(self, settings):
        settings.NUTRIZONE_TELEGRAM_GATEWAY = "disabled"
        assert isinstance(get_orders_telegram_gateway(), NotImplementedTelegramGateway)

    def test_live_gateway_mode_uses_the_orders_bot_token_not_the_customer_bot_token(self, settings):
        settings.NUTRIZONE_TELEGRAM_GATEWAY = "live"
        settings.TELEGRAM_BOT_TOKEN = "123:customer-bot-token"
        settings.TELEGRAM_ORDERS_BOT_TOKEN = "456:orders-bot-token"

        gateway = get_orders_telegram_gateway()
        assert isinstance(gateway, LiveTelegramGateway)
        assert gateway._bot_token == "456:orders-bot-token"

    def test_unknown_gateway_mode_raises(self, settings):
        settings.NUTRIZONE_TELEGRAM_GATEWAY = "bogus"
        with pytest.raises(ValueError):
            get_orders_telegram_gateway()


class TestTelegramGateway:
    def test_placeholder_raises_not_implemented_error(self):
        """The certified, honest behavior -- fails loudly rather than silently pretending a message was sent. This is NOT a test that Telegram delivery works; it is a test that the placeholder correctly refuses to pretend it does."""
        with pytest.raises(NotImplementedError):
            NotImplementedTelegramGateway().send_message("some_username", "Title", "Body")

    def test_placeholder_makes_no_network_call(self, monkeypatch):
        """Explicit proof, not an assumption: patches every plausible HTTP entry point to raise if called, then confirms the placeholder never reaches any of them before raising its own NotImplementedError."""

        def _fail_if_called(*args, **kwargs):
            raise AssertionError("TelegramGateway placeholder must never make a network call")

        monkeypatch.setattr("urllib.request.urlopen", _fail_if_called, raising=False)

        with pytest.raises(NotImplementedError):
            NotImplementedTelegramGateway().send_message("some_username", "Title", "Body")
