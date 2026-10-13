from __future__ import annotations

import pytest

from core.ratelimit import RateLimiter, per_endpoint_global_limiter, per_ip_limiter, per_user_limiter

pytestmark = pytest.mark.unit


def test_requests_within_limit_are_allowed():
    limiter = RateLimiter(scope="test-otp", limit=3, window_seconds=60)
    for _ in range(3):
        result = limiter.check("phone-1")
        assert result.allowed is True


def test_requests_beyond_limit_are_denied():
    limiter = RateLimiter(scope="test-otp-2", limit=2, window_seconds=60)
    limiter.check("phone-2")
    limiter.check("phone-2")
    result = limiter.check("phone-2")
    assert result.allowed is False
    assert result.current_count == 2


def test_different_identifiers_have_independent_limits():
    limiter = RateLimiter(scope="test-otp-3", limit=1, window_seconds=60)
    assert limiter.check("phone-a").allowed is True
    assert limiter.check("phone-b").allowed is True
    assert limiter.check("phone-a").allowed is False


def test_burst_allowance_widens_effective_limit():
    limiter = RateLimiter(scope="test-burst", limit=2, window_seconds=60, burst_allowance=2)
    results = [limiter.check("id-1").allowed for _ in range(4)]
    assert results == [True, True, True, True]
    assert limiter.check("id-1").allowed is False


def test_reset_clears_the_window():
    limiter = RateLimiter(scope="test-reset", limit=1, window_seconds=60)
    limiter.check("id-2")
    assert limiter.check("id-2").allowed is False
    limiter.reset("id-2")
    assert limiter.check("id-2").allowed is True


def test_retry_after_is_zero_when_allowed():
    limiter = RateLimiter(scope="test-retry", limit=5, window_seconds=60)
    result = limiter.check("id-3")
    assert result.retry_after_seconds == 0


def test_retry_after_is_window_seconds_when_denied():
    limiter = RateLimiter(scope="test-retry-2", limit=1, window_seconds=30)
    limiter.check("id-4")
    result = limiter.check("id-4")
    assert result.retry_after_seconds == 30


def test_per_ip_limiter_scopes_key_by_endpoint():
    limiter_a = per_ip_limiter("otp_request", limit=1, window_seconds=60)
    limiter_b = per_ip_limiter("coupon_validate", limit=1, window_seconds=60)
    assert limiter_a.check("1.2.3.4").allowed is True
    assert limiter_b.check("1.2.3.4").allowed is True  # independent scope, not shared with limiter_a


def test_per_user_and_global_limiter_constructors_produce_distinct_scopes():
    user_limiter = per_user_limiter("orders", limit=20, window_seconds=3600)
    global_limiter = per_endpoint_global_limiter("orders", limit=1000, window_seconds=60)
    assert user_limiter.scope != global_limiter.scope
