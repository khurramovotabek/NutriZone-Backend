"""
Chat presence (online/offline) -- Redis-backed, no new DB model.

A user's real online status *is* "does this user currently hold at
least one open, authenticated WebSocket connection" -- not a fabricated
notion of a "presence record" persisted in Postgres. Reference-counted
(not a plain boolean) so a user with two open tabs/devices doesn't
flip to "offline" the moment they close one of them. The TTL is a
safety net only, for a connection that drops without a clean
`disconnect()` (a killed process, a network drop Channels never
learns about) -- a live connection keeps itself "online" by simply
staying open; there is no separate heartbeat to maintain because
`ChatConsumer` already holds the socket open for as long as it's
genuinely connected.

Uses `core.caching.redis_client`, the same Redis instance and
`cache_key()` convention every other module's ephemeral state already
uses (rate limiting, Telegram onboarding state) -- no second Redis
access pattern introduced.
"""
from __future__ import annotations

import uuid

from core.caching.redis_client import cache_key, get_redis_client

_PRESENCE_TTL_SECONDS = 90  # comfortably longer than any real connection's own keep-alive interval


def _key(user_id: uuid.UUID) -> str:
    return cache_key(user_id, namespace="chat:presence")


def mark_connected(user_id: uuid.UUID) -> None:
    client = get_redis_client()
    key = _key(user_id)
    client.incr(key)
    client.expire(key, _PRESENCE_TTL_SECONDS)


def touch(user_id: uuid.UUID) -> None:
    """Heartbeat: keeps a still-open connection's presence alive past the TTL (the client pings every ~25s). Re-creates the key if it expired meanwhile."""
    client = get_redis_client()
    key = _key(user_id)
    if not client.expire(key, _PRESENCE_TTL_SECONDS):
        client.set(key, 1, ex=_PRESENCE_TTL_SECONDS)


def mark_disconnected(user_id: uuid.UUID) -> None:
    client = get_redis_client()
    key = _key(user_id)
    remaining = client.decr(key)
    if remaining <= 0:
        client.delete(key)


def is_online(user_id: uuid.UUID) -> bool:
    client = get_redis_client()
    value = client.get(_key(user_id))
    return value is not None and int(value) > 0


def is_online_bulk(user_ids: list[uuid.UUID]) -> dict[uuid.UUID, bool]:
    """Batched form for a conversation list -- one Redis round trip instead of N, matching the "no N+1" convention already followed elsewhere in this codebase."""
    if not user_ids:
        return {}
    client = get_redis_client()
    keys = [_key(uid) for uid in user_ids]
    values = client.mget(keys)
    return {uid: (val is not None and int(val) > 0) for uid, val in zip(user_ids, values, strict=True)}
