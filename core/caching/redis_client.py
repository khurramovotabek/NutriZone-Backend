"""
Redis client wrapper and cache-key conventions.

Backs the read-model caches named throughout the Enterprise Database
Blueprint (§8 there) and REST API Blueprint (§13): EffectivePriceBoard,
AvailabilityBoard, feature-flag evaluation, unread-message counters.
This module provides the *mechanism* only -- no business cache
population logic lives here (that belongs to each module's
`application/` layer).
"""
from __future__ import annotations

from typing import Any

import redis
from django.conf import settings

_client: redis.Redis | None = None


def get_redis_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _client


def cache_key(*parts: Any, namespace: str) -> str:
    """
    Uniform cache-key builder: `nutrizone:<namespace>:<part>:<part>...`

    e.g. cache_key(variant_id, tier, namespace="pricing:effective")
      -> "nutrizone:pricing:effective:<variant_id>:<tier>"
    """
    joined = ":".join(str(p) for p in parts)
    return f"nutrizone:{namespace}:{joined}"


# Default TTLs (seconds), by cache category -- referenced by module
# implementations rather than each module inventing its own numbers.
TTL_VERY_SHORT = 15        # e.g. EffectivePriceBoard, AvailabilityBoard
TTL_SHORT = 60              # e.g. product detail, order detail
TTL_MEDIUM = 300            # e.g. trending searches, popular products
TTL_LONG = 3600             # e.g. category tree, geo reference data
TTL_FEATURE_FLAGS = 30      # fast kill-switch propagation (REST API Blueprint §13.18)
