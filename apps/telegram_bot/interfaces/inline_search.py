"""
Inline mode -- `@<bot> protein` typed in ANY chat: the catalog's smart search answers with product cards
(photo, price, discount, stock) that the shopper can send to a friend. Each sent card carries "open in the bot"
(the `/start p_<id>` deep link -- straight to that product's card with Add to cart) and "view on the website".

Works without an account (it is a public catalog view). Needs inline mode switched on once in @BotFather
(/setinline) and `inline_query` among the webhook's allowed updates (telegram_set_webhook).
"""
from __future__ import annotations

import html
import logging

from django.conf import settings

from apps.telegram_bot.interfaces.i18n import t

logger = logging.getLogger("nutrizone.app")

PAGE_SIZE = 10
CACHE_SECONDS = 60
MAX_QUERY_LEN = 80


def _lang(inline_query: dict) -> str:
    """The shopper's account language when linked, else their Telegram app language."""
    from apps.telegram_bot.interfaces.callback_router import _resolve_user

    user = _resolve_user(inline_query["from"]["id"])
    if user is not None and getattr(user, "language", None) in ("uz", "ru", "en"):
        return user.language
    code = (inline_query["from"].get("language_code") or "")[:2]
    return code if code in ("uz", "ru", "en") else "uz"


def _money(amount, currency) -> str:
    from apps.telegram_bot.interfaces.callback_router import _format_price

    return _format_price(amount, currency) or ""


def _result(product: dict, lang: str, bot_username: str | None, frontend: str) -> dict:
    name = product.get("name") or ""
    price = _money(product.get("price"), product.get("currency"))
    old = _money(product.get("compare_at_price"), product.get("currency")) if product.get("discount_percent") else ""
    in_stock = (product.get("stock_quantity") or 0) > 0
    stock = t("inline_in_stock", lang) if in_stock else t("inline_out_of_stock", lang)

    description = " · ".join(x for x in (price + (f" (-{product['discount_percent']}%)" if product.get("discount_percent") else ""), stock) if x)
    lines = [f"<b>{html.escape(name)}</b>"]
    if price:
        lines.append(f"\U0001F4B0 <b>{html.escape(price)}</b>" + (f"  <s>{html.escape(old)}</s>" if old else ""))
    if product.get("rating_count"):
        lines.append(f"⭐ {product.get('rating_average')} ({product['rating_count']})")
    lines.append(("✅ " if in_stock else "⏳ ") + stock)

    buttons = []
    if bot_username:
        buttons.append([{"text": t("inline_open_in_bot", lang), "url": f"https://t.me/{bot_username}?start=p_{product['id']}"}])
    if frontend and product.get("slug"):
        buttons.append([{"text": t("btn_view_website", lang), "url": f"{frontend}/products/{product['slug']}"}])

    result = {
        "type": "article", "id": str(product["id"])[:64], "title": name[:120], "description": description[:200],
        "input_message_content": {"message_text": "\n".join(lines), "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}},
    }
    if buttons:
        result["reply_markup"] = {"inline_keyboard": buttons}
    image = product.get("primary_image_path")
    if image and image.startswith("https://"):  # Telegram fetches thumbnails itself -- only a public HTTPS URL works
        result["thumbnail_url"] = image
    return result


def build_answer(inline_query: dict) -> dict:
    """The answerInlineQuery payload: smart-search hits for the typed text (best sellers when it's empty), 10 per page."""
    from apps.products.infrastructure.selectors import DjangoProductSearchBackend

    query = " ".join((inline_query.get("query") or "").split())[:MAX_QUERY_LEN]
    lang = _lang(inline_query)
    try:
        offset = max(0, int(inline_query.get("offset") or 0))
    except ValueError:
        offset = 0
    page = offset // PAGE_SIZE + 1
    found = DjangoProductSearchBackend().search(query, {}, page, PAGE_SIZE, "relevance" if query else "-popularity", lang)
    bot_username = (getattr(settings, "TELEGRAM_BOT_USERNAME", None) or "").lstrip("@") or None
    frontend = (getattr(settings, "FRONTEND_URL", None) or "").rstrip("/")
    results = [_result(p, lang, bot_username, frontend) for p in found["results"]]
    payload = {
        "inline_query_id": inline_query["id"], "results": results, "cache_time": CACHE_SECONDS, "is_personal": False,
        "next_offset": str(offset + PAGE_SIZE) if offset + PAGE_SIZE < found["total_count"] else "",
    }
    if bot_username:
        payload["button"] = {"text": t("inline_shop_button", lang), "start_parameter": "inline"}
    return payload


def answer(inline_query: dict) -> None:
    import requests

    token = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
    if not token:
        return
    base_url = getattr(settings, "TELEGRAM_API_BASE_URL", "https://api.telegram.org")
    try:
        response = requests.post(f"{base_url}/bot{token}/answerInlineQuery", json=build_answer(inline_query), timeout=8)
        if not response.ok:
            logger.warning("answerInlineQuery failed: %s %s", response.status_code, response.text[:300])
    except Exception:  # noqa: BLE001
        logger.exception("answerInlineQuery failed")
