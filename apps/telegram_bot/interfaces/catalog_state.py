"""
Telegram bot product-browsing state.

Holds only *navigation* context (which listing a chat is currently
paging through, and which page) -- never the product data itself.
Every render re-fetches the current page fresh from the same real
selectors the website uses (`TelegramCatalogService`), so a paginated
browse session can never show stale price/stock, matching this
project's own "server remains financial/inventory authority" rule.

Deliberately Redis-backed, matching `onboarding_state.py`'s own
established short-lived-conversational-state pattern -- no new
database model/migration, natural TTL, one shared access pattern
(`core.caching.redis_client`).
"""
from __future__ import annotations

import json

from core.caching.redis_client import cache_key, get_redis_client

_TTL_SECONDS = 1800  # 30 minutes -- long enough for a real browsing session, short enough that an abandoned one never lingers indefinitely.

_VALID_SOURCES = {"best", "new", "all", "brand", "category", "search", "product"}


def set_browsing(chat_id: int, source: str, *, brand_id: str | None = None, category_id: str | None = None, page: int = 1, back_to: str = "menu:products", has_photo: bool = False, query: str | None = None, product_id: str | None = None) -> None:
    if source not in _VALID_SOURCES:
        raise ValueError(f"Unknown browsing source '{source}'.")
    client = get_redis_client()
    client.set(
        cache_key(chat_id, namespace="telegram_bot:catalog"),
        json.dumps({"source": source, "brand_id": brand_id, "category_id": category_id, "page": page, "back_to": back_to, "has_photo": has_photo, "query": query, "product_id": product_id}),
        ex=_TTL_SECONDS,
    )


def get_browsing(chat_id: int) -> dict | None:
    client = get_redis_client()
    raw = client.get(cache_key(chat_id, namespace="telegram_bot:catalog"))
    return json.loads(raw) if raw is not None else None


def set_page(chat_id: int, page: int) -> dict | None:
    """Updates only the page of an existing browsing session, keeping its source/filters -- returns the updated state, or None if the session already expired (the caller must handle that by re-showing the products menu, never by guessing a source)."""
    return merge(chat_id, page=page)


def merge(chat_id: int, **fields) -> dict | None:
    """Updates the given fields of an existing browsing session, keeping the rest -- returns the updated state, or None if the session already expired."""
    state = get_browsing(chat_id)
    if state is None:
        return None
    state.update(fields)
    client = get_redis_client()
    client.set(cache_key(chat_id, namespace="telegram_bot:catalog"), json.dumps(state), ex=_TTL_SECONDS)
    return state


def clear(chat_id: int) -> None:
    client = get_redis_client()
    client.delete(cache_key(chat_id, namespace="telegram_bot:catalog"))
