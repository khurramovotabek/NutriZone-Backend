from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


class TestOTPHashing:
    def test_hash_otp_code_is_deterministic(self, settings):
        from apps.identity.infrastructure.security import hash_otp_code

        settings.SECRET_KEY = "test-secret"
        assert hash_otp_code("123456") == hash_otp_code("123456")

    def test_hash_otp_code_differs_for_different_codes(self, settings):
        from apps.identity.infrastructure.security import hash_otp_code

        settings.SECRET_KEY = "test-secret"
        assert hash_otp_code("123456") != hash_otp_code("654321")

    def test_hash_otp_code_never_returns_the_plaintext_code(self, settings):
        from apps.identity.infrastructure.security import hash_otp_code

        settings.SECRET_KEY = "test-secret"
        assert hash_otp_code("123456") != "123456"


class TestRefreshTokenHashing:
    def test_hash_refresh_token_is_deterministic(self):
        from apps.identity.infrastructure.security import hash_refresh_token

        assert hash_refresh_token("some-jwt-token") == hash_refresh_token("some-jwt-token")

    def test_hash_refresh_token_differs_for_different_tokens(self):
        from apps.identity.infrastructure.security import hash_refresh_token

        assert hash_refresh_token("token-a") != hash_refresh_token("token-b")

    def test_hash_refresh_token_never_returns_plaintext(self):
        from apps.identity.infrastructure.security import hash_refresh_token

        assert hash_refresh_token("raw-token-value") != "raw-token-value"
