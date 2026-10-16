"""
Repository-wide pytest hooks (applies to apps/* and tests/*).

Rate limits live in Redis (core.ratelimit sliding windows + DRF throttles in the Django cache), which
outlives a test's database transaction. Without a reset, requests made by earlier tests count against
later ones in the same minute/hour and those fail at random (seen: 401/429/500 depending on order).
The permission-check cache (identity:permissions) is per user id and survives the same way, and so does the bot
conversation state. Each xdist worker owns a Redis database (config/settings/testing.py), flushed before every test.
"""
from __future__ import annotations

import pytest

_PATTERNS = ("nutrizone:ratelimit:*", "*throttle_*", "nutrizone:identity:permissions:*", "nutrizone:telegram_bot:*")


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    """
    Redis and in-process caches outlive a test's rolled-back transaction: rate limits, permission caches, the bots'
    per-chat state (many tests share fake Telegram ids), and -- the nasty one -- the smart-search index / catalog
    caches built from rows an earlier test created and rolled back (later tests then saw products that no longer
    exist: DoesNotExist, empty results, lost bot state). Each xdist worker owns a Redis database (testing.py), so the
    whole database is flushed before every test, together with smart_search's per-process memo of that index.
    A shared low-numbered database (dev / prod) is never flushed -- only the known leaking keys are dropped there.
    """
    try:
        from core.caching.redis_client import get_redis_client

        client = get_redis_client()
        for pattern in _PATTERNS:
            keys = list(client.scan_iter(match=pattern, count=500))
            if keys:
                client.delete(*keys)
    except Exception:  # noqa: BLE001 - no Redis in this environment: nothing to reset
        pass
    try:
        from apps.products.infrastructure import smart_search

        smart_search._LOCAL.clear()
        smart_search._PREPARED.clear()
    except Exception:  # noqa: BLE001
        pass
    yield


@pytest.fixture(autouse=True)
def _fresh_content_type_cache():
    """
    Most apps keep their models in infrastructure/models.py (no top-level models module), so post_migrate never creates
    their content types; the first ContentType.get_for_model() inside a test creates one -- and the manager caches its id
    for the whole process. The test's transaction rolls the row back, the cached id stays, and the next admin log entry
    hits a ForeignKeyViolation. Clearing the cache around every test keeps ids honest.
    """
    from django.contrib.contenttypes.models import ContentType

    ContentType.objects.clear_cache()
    yield
    ContentType.objects.clear_cache()
