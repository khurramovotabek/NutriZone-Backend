"""
Rate limit foundation.

A Redis-backed sliding-window limiter, scoped by an arbitrary
`(scope, identifier)` pair -- callers compose the scope key themselves
(e.g. `scope="otp_request"`, `identifier=phone_number` for the "3/hour
per phone number" rule from Enterprise REST API Blueprint §13.1, or
`scope="anon_global"`, `identifier=ip_address` for the coarse per-IP
tier from REST API Blueprint §18). This module supplies the mechanism
only -- no endpoint-specific limit numbers are hardcoded here; those
are declared per module per REST API Blueprint §13/§18 when that
module is implemented.

Algorithm: sliding-window log via a Redis sorted set (ZADD score=
timestamp, ZREMRANGEBYSCORE to expire old entries, ZCARD to count) --
smoother than a fixed-window counter (no "burst at window boundary"
artifact) while remaining O(log n) per call and needing no separate
scheduled cleanup job (expired entries are trimmed lazily on each
check call, and the whole key carries a TTL as a backstop).
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from core.caching.redis_client import cache_key, get_redis_client

_SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window_seconds = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

redis.call("ZREMRANGEBYSCORE", key, 0, now - window_seconds)
local current = redis.call("ZCARD", key)

if current < limit then
    redis.call("ZADD", key, now, member)
    redis.call("EXPIRE", key, window_seconds)
    return {1, current + 1}
else
    return {0, current}
end
"""


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    current_count: int
    limit: int
    window_seconds: int

    @property
    def retry_after_seconds(self) -> int:
        """Conservative estimate: the full window, since the sliding-window log doesn't cheaply expose 'when does the oldest entry expire'."""
        return 0 if self.allowed else self.window_seconds


class RateLimiter:
    """
    Usage:
        limiter = RateLimiter(scope="otp_request", limit=3, window_seconds=3600)
        result = limiter.check(identifier=phone_number)
        if not result.allowed:
            raise RateLimitExceeded(...)
    """

    def __init__(self, scope: str, limit: int, window_seconds: int, burst_allowance: int = 0) -> None:
        """
        `burst_allowance` widens the effective limit for short spikes
        (the mission's "Burst" requirement) without changing the
        steady-state window rate -- e.g. limit=100/min with
        burst_allowance=20 permits up to 120 requests in any given
        window, still bounded and still evaluated against the same
        sliding window (not a second, separate counter).
        """
        self.scope = scope
        self.limit = limit + burst_allowance
        self.window_seconds = window_seconds
        self._client = get_redis_client()

    def _key(self, identifier: str) -> str:
        return cache_key(identifier, namespace=f"ratelimit:{self.scope}")

    def check(self, identifier: str) -> RateLimitResult:
        """Atomically checks and records one request. Safe under concurrent access (single Lua script execution)."""
        key = self._key(identifier)
        now = time.time()
        member = f"{now}:{uuid.uuid4().hex[:8]}"  # unique member even for same-millisecond requests
        allowed_flag, count = self._client.eval(
            _SLIDING_WINDOW_SCRIPT, 1, key, now, self.window_seconds, self.limit, member
        )
        return RateLimitResult(
            allowed=bool(allowed_flag), current_count=int(count), limit=self.limit, window_seconds=self.window_seconds
        )

    def reset(self, identifier: str) -> None:
        self._client.delete(self._key(identifier))


# Pre-scoped constructors matching the mission's explicit dimensions --
# generic mechanism, no hardcoded numbers (each caller supplies its own
# limit/window per REST API Blueprint §18's per-endpoint table).
def per_ip_limiter(endpoint_name: str, limit: int, window_seconds: int) -> RateLimiter:
    return RateLimiter(scope=f"ip:{endpoint_name}", limit=limit, window_seconds=window_seconds)


def per_user_limiter(endpoint_name: str, limit: int, window_seconds: int) -> RateLimiter:
    return RateLimiter(scope=f"user:{endpoint_name}", limit=limit, window_seconds=window_seconds)


def per_endpoint_global_limiter(endpoint_name: str, limit: int, window_seconds: int) -> RateLimiter:
    return RateLimiter(scope=f"global:{endpoint_name}", limit=limit, window_seconds=window_seconds)
