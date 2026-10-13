from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta

import pytest

from apps.identity.domain.exceptions import (
    OTPExpiredError,
    OTPInvalidError,
    OTPMaxAttemptsExceededError,
    OTPResendTooSoonError,
)
from apps.identity.domain.services import (
    OTP_EXPIRY_SECONDS,
    OTP_MAX_REQUESTS_PER_HOUR,
    OTP_MAX_VERIFY_ATTEMPTS,
    OTPChallengeState,
    OTPPolicy,
    TokenPolicy,
)
from apps.identity.domain.value_objects import OTPCode
from core.clock import Clock

pytestmark = pytest.mark.unit


def _hasher(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _challenge(code: str = "123456", attempts: int = 0, consumed: bool = False, expired: bool = False) -> OTPChallengeState:
    now = Clock.now()
    return OTPChallengeState(
        id=uuid.uuid4(),
        code_hash=_hasher(code),
        expires_at=now - timedelta(seconds=1) if expired else now + timedelta(minutes=5),
        attempt_count=attempts,
        consumed_at=now if consumed else None,
        created_at=now,
    )


class TestOTPPolicyResend:
    def test_can_resend_when_no_prior_request(self):
        OTPPolicy.can_resend(None)  # should not raise

    def test_can_resend_after_cooldown(self):
        OTPPolicy.can_resend(Clock.now() - timedelta(seconds=61))  # should not raise

    def test_cannot_resend_within_cooldown(self):
        with pytest.raises(OTPResendTooSoonError):
            OTPPolicy.can_resend(Clock.now() - timedelta(seconds=5))


class TestOTPPolicyQuota:
    def test_within_quota_does_not_raise(self):
        OTPPolicy.assert_within_hourly_quota(OTP_MAX_REQUESTS_PER_HOUR - 1)

    def test_at_quota_raises(self):
        with pytest.raises(OTPMaxAttemptsExceededError):
            OTPPolicy.assert_within_hourly_quota(OTP_MAX_REQUESTS_PER_HOUR)


class TestOTPPolicyVerify:
    def test_correct_code_verifies_successfully(self):
        challenge = _challenge(code="654321")
        OTPPolicy.verify(challenge, OTPCode("654321"), _hasher)  # should not raise

    def test_incorrect_code_raises_invalid(self):
        challenge = _challenge(code="654321")
        with pytest.raises(OTPInvalidError):
            OTPPolicy.verify(challenge, OTPCode("111111"), _hasher)

    def test_expired_challenge_raises_expired(self):
        challenge = _challenge(expired=True)
        with pytest.raises(OTPExpiredError):
            OTPPolicy.verify(challenge, OTPCode("123456"), _hasher)

    def test_already_consumed_challenge_raises_invalid(self):
        challenge = _challenge(consumed=True)
        with pytest.raises(OTPInvalidError):
            OTPPolicy.verify(challenge, OTPCode("123456"), _hasher)

    def test_max_attempts_exceeded_raises(self):
        challenge = _challenge(attempts=OTP_MAX_VERIFY_ATTEMPTS)
        with pytest.raises(OTPMaxAttemptsExceededError):
            OTPPolicy.verify(challenge, OTPCode("123456"), _hasher)

    def test_expiry_checked_before_attempt_count(self):
        """An expired-and-exhausted challenge should report expiry, the more specific/actionable error."""
        challenge = _challenge(expired=True, attempts=OTP_MAX_VERIFY_ATTEMPTS)
        with pytest.raises(OTPExpiredError):
            OTPPolicy.verify(challenge, OTPCode("123456"), _hasher)


class TestOTPPolicyExpiry:
    def test_new_expiry_is_in_the_future(self):
        assert OTPPolicy.new_expiry() > Clock.now()

    def test_otp_expiry_is_exactly_two_minutes(self):
        """
        Real, explicit product requirement: a login code -- SMS or the
        Telegram-delivered "Sayt uchun kod olish" code alike, both
        governed by this exact same policy -- must be valid for 2
        minutes, matching the reference login experience this
        authentication flow was rebuilt against ("Kod 2 daqiqada amal
        qiladi"). Regression guard against this constant silently
        drifting back to some other duration.
        """
        assert OTP_EXPIRY_SECONDS == 120
        expiry = OTPPolicy.new_expiry()
        elapsed = (expiry - Clock.now()).total_seconds()
        assert 119 <= elapsed <= 120


class TestTokenPolicy:
    def test_refresh_token_expiry_is_in_the_future(self):
        assert TokenPolicy.refresh_token_expiry() > Clock.now()

    def test_refresh_token_expiry_matches_configured_days(self):
        from datetime import timedelta as td

        fixed = Clock.now()
        with Clock.freeze(fixed):
            expiry = TokenPolicy.refresh_token_expiry()
        assert expiry == fixed + td(days=TokenPolicy.REFRESH_TOKEN_DAYS)
