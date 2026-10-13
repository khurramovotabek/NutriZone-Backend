"""
Phase 04: LiveTelegramGateway tests. Every test mocks the HTTP
boundary (`requests.post`) -- no real network call is ever made, per
this phase's own explicit instruction.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from apps.notifications.infrastructure.gateways import (
    LiveTelegramGateway, TelegramGatewayConfigurationError, TelegramGatewayNonRetryableError, TelegramGatewayRetryableError,
)


def _gateway(**overrides) -> LiveTelegramGateway:
    defaults = dict(bot_token="123456:fake-bot-token", base_url="https://api.telegram.org", timeout_seconds=5.0)
    defaults.update(overrides)
    return LiveTelegramGateway(**defaults)


class TestLiveTelegramGatewayConfiguration:
    def test_missing_token_raises_configuration_error(self):
        gateway = _gateway(bot_token=None)
        with pytest.raises(TelegramGatewayConfigurationError):
            gateway.send_message("12345", "Title", "Body")


class TestLiveTelegramGatewaySuccess:
    @patch("apps.notifications.infrastructure.gateways.requests.post")
    def test_successful_send_returns_message_id(self, mock_post):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"ok": True, "result": {"message_id": 42}}
        mock_post.return_value = response

        gateway = _gateway()
        result = gateway.send_message("12345", "Title", "Body")
        assert result == "42"

    @patch("apps.notifications.infrastructure.gateways.requests.post")
    def test_bot_token_never_logged(self, mock_post, caplog):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"ok": True, "result": {"message_id": 42}}
        mock_post.return_value = response

        gateway = _gateway(bot_token="123456:super-secret-bot-token")
        with caplog.at_level("DEBUG"):
            gateway.send_message("12345", "Title", "Body")

        assert "super-secret-bot-token" not in caplog.text

    @patch("apps.notifications.infrastructure.gateways.requests.post")
    def test_edit_message_text_calls_the_real_edit_endpoint(self, mock_post):
        """Real, closed regression: edit_message_text previously had no `def` line at all in LiveTelegramGateway -- it was unreachable dead code fused onto send_location_request, so calling it raised AttributeError."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"ok": True}
        mock_post.return_value = response

        gateway = _gateway()
        gateway.edit_message_text("12345", "999", "Updated text", inline_keyboard=[[{"text": "OK", "callback_data": "x"}]])

        called_url = mock_post.call_args[0][0]
        assert called_url.endswith("/editMessageText")
        payload = mock_post.call_args[1]["json"]
        assert payload["message_id"] == "999"
        assert payload["reply_markup"] == {"inline_keyboard": [[{"text": "OK", "callback_data": "x"}]]}

    @patch("apps.notifications.infrastructure.gateways.requests.post")
    def test_send_photo_calls_the_real_send_photo_endpoint(self, mock_post):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"ok": True, "result": {"message_id": 7}}
        mock_post.return_value = response

        gateway = _gateway()
        result = gateway.send_photo("12345", "https://cdn.example.com/product.jpg", "A caption", inline_keyboard=[[{"text": "Confirm", "callback_data": "y"}]])

        assert result == "7"
        called_url = mock_post.call_args[0][0]
        assert called_url.endswith("/sendPhoto")
        payload = mock_post.call_args[1]["json"]
        assert payload["photo"] == "https://cdn.example.com/product.jpg"
        assert payload["caption"] == "A caption"

    @patch("apps.notifications.infrastructure.gateways.requests.post")
    def test_edit_message_media_calls_the_real_edit_endpoint(self, mock_post):
        """Real, product-required addition (premium mini-store phase): the Telegram product browsing card pages through products by editing one photo message's image/caption in place, never sending a new one per product."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"ok": True}
        mock_post.return_value = response

        gateway = _gateway()
        gateway.edit_message_media("12345", "999", "https://cdn.example.com/product2.jpg", "New caption", inline_keyboard=[[{"text": "Next", "callback_data": "pc:next"}]])

        called_url = mock_post.call_args[0][0]
        assert called_url.endswith("/editMessageMedia")
        payload = mock_post.call_args[1]["json"]
        assert payload["chat_id"] == "12345"
        assert payload["message_id"] == "999"
        assert payload["media"] == {"type": "photo", "media": "https://cdn.example.com/product2.jpg", "caption": "New caption", "parse_mode": "HTML"}
        assert payload["reply_markup"] == {"inline_keyboard": [[{"text": "Next", "callback_data": "pc:next"}]]}

    @patch("apps.notifications.infrastructure.gateways.requests.post")
    def test_edit_message_media_raises_non_retryable_when_telegram_reports_failure(self, mock_post):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"ok": False, "description": "message to edit not found"}
        mock_post.return_value = response

        gateway = _gateway()
        with pytest.raises(TelegramGatewayNonRetryableError):
            gateway.edit_message_media("12345", "stale-id", "https://cdn.example.com/product.jpg", "Caption")

    def test_edit_message_media_missing_token_raises_configuration_error(self):
        gateway = _gateway(bot_token=None)
        with pytest.raises(TelegramGatewayConfigurationError):
            gateway.edit_message_media("12345", "999", "https://cdn.example.com/product.jpg", "Caption")


class TestLiveTelegramGatewayRetryableFailures:
    @patch("apps.notifications.infrastructure.gateways.requests.post")
    def test_timeout_raises_retryable(self, mock_post):
        mock_post.side_effect = requests.exceptions.Timeout()
        gateway = _gateway()
        with pytest.raises(TelegramGatewayRetryableError):
            gateway.send_message("12345", "Title", "Body")

    @patch("apps.notifications.infrastructure.gateways.requests.post")
    def test_connection_error_raises_retryable(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError()
        gateway = _gateway()
        with pytest.raises(TelegramGatewayRetryableError):
            gateway.send_message("12345", "Title", "Body")

    @patch("apps.notifications.infrastructure.gateways.requests.post")
    def test_server_error_raises_retryable(self, mock_post):
        response = MagicMock()
        response.status_code = 502
        mock_post.return_value = response
        gateway = _gateway()
        with pytest.raises(TelegramGatewayRetryableError):
            gateway.send_message("12345", "Title", "Body")


class TestLiveTelegramGatewayNonRetryableFailures:
    @patch("apps.notifications.infrastructure.gateways.requests.post")
    def test_unauthorized_raises_non_retryable(self, mock_post):
        response = MagicMock()
        response.status_code = 401
        mock_post.return_value = response
        gateway = _gateway()
        with pytest.raises(TelegramGatewayNonRetryableError):
            gateway.send_message("12345", "Title", "Body")

    @patch("apps.notifications.infrastructure.gateways.requests.post")
    def test_bad_request_raises_non_retryable(self, mock_post):
        response = MagicMock()
        response.status_code = 400
        mock_post.return_value = response
        gateway = _gateway()
        with pytest.raises(TelegramGatewayNonRetryableError):
            gateway.send_message("12345", "Title", "Body")

    @patch("apps.notifications.infrastructure.gateways.requests.post")
    def test_ok_false_raises_non_retryable(self, mock_post):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"ok": False, "description": "chat not found"}
        mock_post.return_value = response
        gateway = _gateway()
        with pytest.raises(TelegramGatewayNonRetryableError):
            gateway.send_message("12345", "Title", "Body")

    @patch("apps.notifications.infrastructure.gateways.requests.post")
    def test_malformed_json_raises_non_retryable(self, mock_post):
        response = MagicMock()
        response.status_code = 200
        response.json.side_effect = ValueError("not json")
        mock_post.return_value = response
        gateway = _gateway()
        with pytest.raises(TelegramGatewayNonRetryableError):
            gateway.send_message("12345", "Title", "Body")
