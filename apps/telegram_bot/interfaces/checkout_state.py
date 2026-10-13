"""
Telegram bot checkout conversational state.

Before this phase, `confirm_cash_order()`'s own `location_text`
parameter was fed a fabricated placeholder (f"Telegram chat
{chat_id}") -- never the customer's real delivery location, per
explicit product decision. This module remembers, between the
"checkout:start" callback and the customer's next message, that
"this chat_id is waiting for a real location share" so the plain
`message["location"]` payload Telegram sends when the user taps the
native "Share Location" button can be routed to the right place.

Deliberately Redis-backed (same established pattern as
onboarding_state.py/chat_state.py), not a new database model: this is
disposable routing state, not the durable record -- the real, durable
outcome is the geo.Address row itself, created once the location
arrives.
"""
from __future__ import annotations

from core.caching.redis_client import cache_key, get_redis_client

_TTL_SECONDS = 600  # 10 minutes -- same rationale as onboarding_state's identical constant: long enough for a real user to tap "share location", short enough that an abandoned checkout never lingers.


def set_awaiting_location(chat_id: int) -> None:
    client = get_redis_client()
    client.set(cache_key(chat_id, namespace="telegram_bot:checkout"), "awaiting_location", ex=_TTL_SECONDS)


def is_awaiting_location(chat_id: int) -> bool:
    client = get_redis_client()
    raw = client.get(cache_key(chat_id, namespace="telegram_bot:checkout"))
    if raw is None:
        return False
    return (raw if isinstance(raw, str) else raw.decode()) == "awaiting_location"


def clear(chat_id: int) -> None:
    client = get_redis_client()
    client.delete(cache_key(chat_id, namespace="telegram_bot:checkout"))
