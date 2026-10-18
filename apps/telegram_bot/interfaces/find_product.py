"""
"🔎 Mahsulot topib berish" in the customer bot -- the same ProductRequest the website's Profile → Mahsulot
so'rovlari creates (apps/support/infrastructure/product_requests.py), so staff answer both in one dashboard list
and the answer reaches the customer in this chat.

    menu:find / /topish   → asks for a photo, a name or a link (state "awaiting", 15 min)
    photo / text / link   → while awaiting: creates the request
    a photo sent anywhere else in the private chat → "Shall we find this product for you?" (fp:send / fp:cancel)
    fp:list               → my last requests with their status
"""
from __future__ import annotations

import json
import logging
import re

from django.conf import settings

from apps.telegram_bot.interfaces.i18n import t
from core.caching.redis_client import cache_key, get_redis_client

logger = logging.getLogger("nutrizone.telegram_bot")

_TTL = 15 * 60
_URL = re.compile(r"(https?://\S+|www\.\S+|\b[\w-]+(?:\.[\w-]+)*\.(?:uz|com|ru|net|org|shop|store)/\S*)", re.I)
STATUS_ICON = {"new": "📨", "searching": "🔎", "found": "✅", "not_found": "❌", "cancelled": "⛔"}


def _key(chat_id, name: str) -> str:
    return cache_key(chat_id, namespace=f"telegram_bot:find_product:{name}")


def is_awaiting(chat_id) -> bool:
    return bool(get_redis_client().get(_key(chat_id, "awaiting")))


def clear(chat_id) -> None:
    client = get_redis_client()
    client.delete(_key(chat_id, "awaiting"), _key(chat_id, "pending"))


def _send(chat_id, text: str, keyboard: list | None = None) -> None:
    from apps.telegram_bot.interfaces.callback_router import _send as send

    send(chat_id, text, keyboard)


def _site_url(path: str) -> str | None:
    base = (getattr(settings, "FRONTEND_URL", None) or "").rstrip("/")
    return f"{base}{path}" if base.startswith("https://") else None


def _done_keyboard(lang: str) -> list:
    rows = [[{"text": t("fp_my_requests", lang), "callback_data": "fp:list"}]]
    url = _site_url("/account/product-requests")
    if url:
        rows.append([{"text": t("fp_open_site", lang), "url": url}])
    rows.append([{"text": t("home_button", lang), "callback_data": "menu:home"}])
    return rows


def prompt(chat_id, lang: str) -> None:
    get_redis_client().set(_key(chat_id, "awaiting"), "1", ex=_TTL)
    _send(chat_id, t("fp_prompt", lang), [[{"text": t("fp_my_requests", lang), "callback_data": "fp:list"}],
                                          [{"text": t("fp_cancel_button", lang), "callback_data": "fp:cancel"}]])


def split_text(text: str, lang: str = "uz") -> tuple[str, str, str]:
    """(name, description, url) from free text: the first link is the URL, the first line (without it) the name."""
    text = (text or "").strip()
    match = _URL.search(text)
    url = match.group(0).rstrip(").,;") if match else ""
    rest = (text[: match.start()] + text[match.end():]).strip() if match else text
    lines = [line.strip() for line in rest.splitlines() if line.strip()]
    name = lines[0][:200] if lines else ""
    description = "\n".join(lines[1:])[:2000]
    if not name and url:
        host = url.split("//", 1)[-1].split("/", 1)[0].removeprefix("www.")
        name = t("fp_name_from_link", lang, host=host)
    if url and not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    return name, description, url


def _create(user, chat_id, lang: str, *, text: str = "", file_id: str | None = None) -> None:
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.support.infrastructure import product_requests as svc
    from apps.telegram_bot.infrastructure import tg_files

    name, description, url = split_text(text, lang)
    image = None
    if file_id:
        try:
            f = tg_files.download(file_id)
            image = SimpleUploadedFile(f.filename, f.content, content_type=f.mime_type)
        except tg_files.TelegramFileError:
            logger.warning("find product: photo download failed for chat %s", chat_id)
            _send(chat_id, t("fp_photo_failed", lang), [[{"text": t("fp_cancel_button", lang), "callback_data": "fp:cancel"}]])
            return
        if not name:
            name = t("fp_name_from_photo", lang)
    try:
        row = svc.create(user.id, product_name=name, description=description, url=url, image=image)
    except svc.ProductRequestError as exc:
        key = {"NAME_REQUIRED": "fp_need_more", "TOO_MANY_OPEN": "fp_too_many"}.get(exc.code, "fp_failed")
        _send(chat_id, t(key, lang), [[{"text": t("fp_my_requests", lang), "callback_data": "fp:list"}], [{"text": t("home_button", lang), "callback_data": "menu:home"}]])
        if exc.code != "NAME_REQUIRED":
            clear(chat_id)
        return
    clear(chat_id)
    _send(chat_id, t("fp_created", lang, number=row.number, name=_esc(row.product_name)), _done_keyboard(lang))


def _esc(text: str) -> str:
    import html

    return html.escape(text or "")


def handle_message(user, message: dict, lang: str) -> bool:
    """A photo / text in the private chat. True when this module took it (awaiting a request, or a stray photo)."""
    from apps.telegram_bot.infrastructure.tg_files import best_photo

    chat_id = message["chat"]["id"]
    photo = best_photo(message)
    text = message.get("caption") or message.get("text") or ""
    if is_awaiting(chat_id):
        if not photo and not text.strip():
            return False
        _create(user, chat_id, lang, text=text, file_id=photo["file_id"] if photo else None)
        return True
    if photo:
        get_redis_client().set(_key(chat_id, "pending"), json.dumps({"file_id": photo["file_id"], "caption": text[:1000]}), ex=_TTL)
        _send(chat_id, t("fp_offer_photo", lang), [[{"text": t("fp_send_button", lang), "callback_data": "fp:send"}],
                                                   [{"text": t("fp_cancel_button", lang), "callback_data": "fp:cancel"}]])
        return True
    return False


def show_list(user, chat_id, lang: str) -> None:
    from apps.support.infrastructure.models import ProductRequest
    from apps.telegram_bot.interfaces.callback_router import money_text

    rows = list(ProductRequest.objects.filter(customer_id=user.id).order_by("-created_at")[:6])
    if not rows:
        _send(chat_id, t("fp_list_empty", lang), [[{"text": t("menu_find", lang), "callback_data": "menu:find"}], [{"text": t("home_button", lang), "callback_data": "menu:home"}]])
        return
    lines = [t("fp_list_title", lang)]
    for r in rows:
        line = f"{STATUS_ICON.get(r.status, '•')} <b>{_esc(r.product_name)}</b> · {r.number}\n    {t('fp_status_' + r.status, lang)}"
        if r.staff_reply:
            reply = r.staff_reply if len(r.staff_reply) <= 160 else r.staff_reply[:157] + "…"
            line += f"\n    💬 <i>{_esc(reply)}</i>"
        if r.offered_price:
            line += "\n    💰 ≈ " + money_text(r.offered_price, lang)
        lines.append(line)
    keyboard = [[{"text": t("menu_find", lang), "callback_data": "menu:find"}]]
    url = _site_url("/account/product-requests")
    if url:
        keyboard.append([{"text": t("fp_open_site", lang), "url": url}])
    keyboard.append([{"text": t("home_button", lang), "callback_data": "menu:home"}])
    _send(chat_id, "\n\n".join(lines), keyboard)


def handle_callback(user, chat_id, action: str, lang: str) -> None:
    if action == "send":
        raw = get_redis_client().get(_key(chat_id, "pending"))
        if not raw:
            prompt(chat_id, lang)
            return
        pending = json.loads(raw if isinstance(raw, str) else raw.decode())
        _create(user, chat_id, lang, text=pending.get("caption") or "", file_id=pending.get("file_id"))
    elif action == "list":
        show_list(user, chat_id, lang)
    else:  # cancel
        clear(chat_id)
        _send(chat_id, t("fp_cancelled", lang), [[{"text": t("home_button", lang), "callback_data": "menu:home"}]])
