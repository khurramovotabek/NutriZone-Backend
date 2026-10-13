"""
Phase 04: EskizOTPProvider tests. Every test mocks the HTTP boundary
(`requests.post`) -- no real network call is ever made, per this
phase's own explicit instruction.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from apps.identity.domain.value_objects import PhoneNumber
from apps.identity.infrastructure.gateways.otp_providers import (
    EskizOTPProvider, OTPProviderConfigurationError, OTPProviderNonRetryableError,
)


def _provider(**overrides) -> EskizOTPProvider:
    defaults = dict(email="test@example.com", password="secret", sender_name="4546", base_url="https://notify.eskiz.uz/api", timeout_seconds=5.0)
    defaults.update(overrides)
    return EskizOTPProvider(**defaults)


def _auth_response(token="fake-token-123"):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"data": {"token": token}}
    return resp


class TestEskizOTPProviderConfiguration:
    def test_missing_credentials_raises_configuration_error(self):
        provider = _provider(email=None, password=None)
        with pytest.raises(OTPProviderConfigurationError):
            provider.send_otp(PhoneNumber("+998901234567"), "123456")


class TestEskizOTPProviderSuccess:
    @patch("apps.identity.infrastructure.gateways.otp_providers.requests.post")
    def test_successful_send_returns_true(self, mock_post):
        send_response = MagicMock()
        send_response.status_code = 200
        send_response.json.return_value = {"status": "waiting"}
        mock_post.side_effect = [_auth_response(), send_response]

        provider = _provider()
        result = provider.send_otp(PhoneNumber("+998901234567"), "123456")
        assert result is True

    @patch("apps.identity.infrastructure.gateways.otp_providers.requests.post")
    def test_bearer_token_never_logged(self, mock_post, caplog):
        send_response = MagicMock()
        send_response.status_code = 200
        send_response.json.return_value = {"status": "waiting"}
        mock_post.side_effect = [_auth_response(token="super-secret-token-xyz"), send_response]

        provider = _provider(password="super-secret-password")
        with caplog.at_level("DEBUG"):
            provider.send_otp(PhoneNumber("+998901234567"), "123456")

        assert "super-secret-token-xyz" not in caplog.text
        assert "super-secret-password" not in caplog.text


class TestEskizOTPProviderRetryableFailures:
    """Transient failures return False -- safe for the caller's existing retry infrastructure, never raise."""

    @patch("apps.identity.infrastructure.gateways.otp_providers.requests.post")
    def test_authentication_timeout_returns_false(self, mock_post):
        mock_post.side_effect = requests.exceptions.Timeout()
        provider = _provider()
        assert provider.send_otp(PhoneNumber("+998901234567"), "123456") is False

    @patch("apps.identity.infrastructure.gateways.otp_providers.requests.post")
    def test_authentication_connection_error_returns_false(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError()
        provider = _provider()
        assert provider.send_otp(PhoneNumber("+998901234567"), "123456") is False

    @patch("apps.identity.infrastructure.gateways.otp_providers.requests.post")
    def test_send_timeout_returns_false(self, mock_post):
        mock_post.side_effect = [_auth_response(), requests.exceptions.Timeout()]
        provider = _provider()
        assert provider.send_otp(PhoneNumber("+998901234567"), "123456") is False

    @patch("apps.identity.infrastructure.gateways.otp_providers.requests.post")
    def test_send_server_error_returns_false(self, mock_post):
        send_response = MagicMock()
        send_response.status_code = 503
        mock_post.side_effect = [_auth_response(), send_response]
        provider = _provider()
        assert provider.send_otp(PhoneNumber("+998901234567"), "123456") is False


class TestEskizOTPProviderNonRetryableFailures:
    """Permanent failures raise OTPProviderNonRetryableError -- retrying would not help."""

    @patch("apps.identity.infrastructure.gateways.otp_providers.requests.post")
    def test_send_invalid_request_raises_non_retryable(self, mock_post):
        send_response = MagicMock()
        send_response.status_code = 400
        mock_post.side_effect = [_auth_response(), send_response]
        provider = _provider()
        with pytest.raises(OTPProviderNonRetryableError):
            provider.send_otp(PhoneNumber("+998901234567"), "123456")

    @patch("apps.identity.infrastructure.gateways.otp_providers.requests.post")
    def test_send_malformed_json_response_raises_non_retryable(self, mock_post):
        send_response = MagicMock()
        send_response.status_code = 200
        send_response.json.side_effect = ValueError("not json")
        mock_post.side_effect = [_auth_response(), send_response]
        provider = _provider()
        with pytest.raises(OTPProviderNonRetryableError):
            provider.send_otp(PhoneNumber("+998901234567"), "123456")

    @patch("apps.identity.infrastructure.gateways.otp_providers.requests.post")
    def test_provider_body_error_raises_non_retryable(self, mock_post):
        send_response = MagicMock()
        send_response.status_code = 200
        send_response.json.return_value = {"status": "error", "message": "Invalid phone number"}
        mock_post.side_effect = [_auth_response(), send_response]
        provider = _provider()
        with pytest.raises(OTPProviderNonRetryableError):
            provider.send_otp(PhoneNumber("+998901234567"), "123456")
