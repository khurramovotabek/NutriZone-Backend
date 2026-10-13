"""
Verifies the Identity module's rate-limit throttle configuration
(mission §11) matches Architecture Review §14's documented numbers,
and that the underlying RateLimiter mechanics actually deny requests
once exhausted -- the "OTP brute force" and "Rate limiting" security
tests this phase's mission requires.
"""
from __future__ import annotations

import pytest

from apps.identity.interfaces.api.v1.views import (
    AdminOperationThrottle,
    LoginThrottle,
    OTPRequestThrottle,
    OTPVerifyThrottle,
    ProfileUpdateThrottle,
    RefreshThrottle,
)

pytestmark = pytest.mark.unit


class TestThrottleConfiguration:
    def test_otp_request_throttle_matches_architecture_review_limit(self):
        """Architecture Review §14: '3 per hour per phone number.'"""
        assert OTPRequestThrottle.limit == 3
        assert OTPRequestThrottle.window_seconds == 3600
        assert OTPRequestThrottle.identifier_source == "field:phone_number"

    def test_every_throttle_has_a_positive_limit_and_scope(self):
        for throttle_cls in (OTPRequestThrottle, OTPVerifyThrottle, LoginThrottle, RefreshThrottle, ProfileUpdateThrottle, AdminOperationThrottle):
            assert throttle_cls.limit > 0
            assert throttle_cls.scope

    def test_throttle_scopes_are_unique(self):
        throttles = (OTPRequestThrottle, OTPVerifyThrottle, LoginThrottle, RefreshThrottle, ProfileUpdateThrottle, AdminOperationThrottle)
        scopes = [t.scope for t in throttles]
        assert len(scopes) == len(set(scopes))


class TestOTPRequestThrottleBehavior:
    def test_denies_after_limit_exhausted_for_same_phone(self):
        throttle = OTPRequestThrottle()
        results = [throttle._limiter.check(f"field:phone_number:+998901111111") for _ in range(4)]
        allowed = [r.allowed for r in results]
        assert allowed == [True, True, True, False]

    def test_different_phone_numbers_have_independent_quotas(self):
        throttle = OTPRequestThrottle()
        for _ in range(3):
            throttle._limiter.check("field:phone_number:+998902222222")
        # A different phone number is unaffected.
        assert throttle._limiter.check("field:phone_number:+998903333333").allowed is True
