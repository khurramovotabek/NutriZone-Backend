"""
Telegram bot "active support chat" conversational state.

Once a customer taps the "Chat" menu button, every subsequent plain-
text message they send should be routed as a real chat message into
their real apps.chat Conversation -- not silently dropped (the
previously disclosed gap this module closes) and not misrouted into
some other flow (onboarding name/phone capture, Telegram-code login).

Deliberately Redis-backed (same established pattern as
onboarding_state.py), not a new database model: which chat_id is
"currently in chat mode, pointed at which conversation_id" is
disposable routing state, not domain data -- the real, durable record
is the Conversation/Message aggregates themselves. A longer TTL than
onboarding's 10 minutes is used here because a real support
conversation can legitimately have gaps of many minutes between
replies; every real send refreshes the TTL so an active chat never
expires mid-use.
"""
from __future__ import annotations

import uuid

from core.caching.redis_client import cache_key, get_redis_client

_TTL_SECONDS = 3600  # 1 hour, refreshed on every real send -- long enough to survive a real conversational gap, short enough that a long-abandoned chat eventually stops being treated as "active".


def set_active_conversation(chat_id: int, conversation_id: uuid.UUID) -> None:
    client = get_redis_client()
    client.set(cache_key(chat_id, namespace="telegram_bot:active_chat"), str(conversation_id), ex=_TTL_SECONDS)


def get_active_conversation(chat_id: int) -> uuid.UUID | None:
    client = get_redis_client()
    raw = client.get(cache_key(chat_id, namespace="telegram_bot:active_chat"))
    if raw is None:
        return None
    return uuid.UUID(raw if isinstance(raw, str) else raw.decode())


def refresh(chat_id: int, conversation_id: uuid.UUID) -> None:
    """Re-sets the same value to push the TTL back out -- called after every real message send, so an actively-used chat never expires mid-conversation."""
    set_active_conversation(chat_id, conversation_id)


def clear(chat_id: int) -> None:
    client = get_redis_client()
    client.delete(cache_key(chat_id, namespace="telegram_bot:active_chat"))
