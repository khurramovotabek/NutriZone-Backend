"""
Telegram bot onboarding conversational state.

A brand-new customer must be asked for their full name (as free text,
typed by them -- never silently taken from Telegram's own first_name/
last_name fields, which are frequently incomplete or informal) before
sharing their phone number. This requires remembering, between two
separate webhook deliveries, that "this chat_id is mid-onboarding,
waiting for a name" -- a real, short-lived conversational state.

Deliberately Redis-backed, not a new database model/migration: this
state is disposable (a few minutes' relevance, matching the existing
OTPCodeChallenge/TelegramAuthSession short-lived-state precedent) and
naturally expires via TTL, with zero schema footprint. Reuses this
build's own established `core.caching.redis_client` helpers rather
than introducing a second Redis access pattern.
"""
from __future__ import annotations

import json

from core.caching.redis_client import cache_key, get_redis_client

_TTL_SECONDS = 600  # 10 minutes -- long enough for a real user to type a reply, short enough that a stale, abandoned flow never lingers.


def set_awaiting_language(chat_id: int) -> None:
    client = get_redis_client()
    client.set(cache_key(chat_id, namespace="telegram_bot:onboarding"), json.dumps({"step": "awaiting_language"}), ex=_TTL_SECONDS)


def set_awaiting_full_name(chat_id: int, language: str) -> None:
    client = get_redis_client()
    client.set(cache_key(chat_id, namespace="telegram_bot:onboarding"), json.dumps({"step": "awaiting_full_name", "language": language}), ex=_TTL_SECONDS)


def set_awaiting_phone(chat_id: int, language: str, full_name: str) -> None:
    client = get_redis_client()
    client.set(cache_key(chat_id, namespace="telegram_bot:onboarding"), json.dumps({"step": "awaiting_phone", "language": language, "full_name": full_name}), ex=_TTL_SECONDS)


def set_awaiting_confirmation(chat_id: int, language: str, full_name: str, phone_number: str) -> None:
    client = get_redis_client()
    client.set(
        cache_key(chat_id, namespace="telegram_bot:onboarding"),
        json.dumps({"step": "awaiting_confirmation", "language": language, "full_name": full_name, "phone_number": phone_number}),
        ex=_TTL_SECONDS,
    )


def get_state(chat_id: int) -> dict | None:
    client = get_redis_client()
    raw = client.get(cache_key(chat_id, namespace="telegram_bot:onboarding"))
    if raw is None:
        return None
    return json.loads(raw)


def clear(chat_id: int) -> None:
    client = get_redis_client()
    client.delete(cache_key(chat_id, namespace="telegram_bot:onboarding"))
