"""
The Orders channel: where the Orders bot posts online orders, kassa sales, after-sales requests, shift reports and
staff alerts. This module is the ONLY place that decides which chat that is:

  chat_id()        the dashboard / auto-detected channel (OrdersChannelSettings), else env TELEGRAM_ORDERS_CHAT_ID
  handle_update()  Orders-bot webhook updates about chats:
                     - my_chat_member: the bot was added/promoted/removed → remembered (the dashboard pick list); if
                       no channel is connected yet, the bot can post there AND the person who added it is NutriZone
                       staff (an active TelegramStaffMember) → connected
                     - channel_post: the channel is remembered (posts in a channel are anonymous, so they never
                       connect anything -- otherwise anyone could add the bot to their own channel and receive orders)
                     - "/ulash" in a group from a group admin who is NutriZone staff → connect it
                     - a group that became a supergroup keeps working (migrate_to_chat_id)
  connect_ref()    dashboard: "@username", "-100…" or a t.me link → verified (bot must be an admin that may post)
  send_test(), disconnect(), status()

Connecting a NEW chat fast-forwards the channel cursors, so the history of past orders is never dumped into it --
everything from that moment on is posted.
"""
from __future__ import annotations

import html
import logging
import re

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError
from django.utils import timezone

from apps.telegram_bot.infrastructure import rich as R

logger = logging.getLogger("nutrizone.telegram_bot")

CACHE_KEY = "telegram:orders-chat-id:v1"
CONNECT_COMMANDS = {"/ulash", "/connect", "/podklyuchit"}
POSTING = {"creator", "administrator"}


def _token() -> str:
    return getattr(settings, "TELEGRAM_ORDERS_BOT_TOKEN", None) or ""


def _env_chat() -> str:
    return str(getattr(settings, "TELEGRAM_ORDERS_CHAT_ID", "") or "").strip()


def _settings():
    from apps.telegram_bot.infrastructure.models import OrdersChannelSettings

    obj, _ = OrdersChannelSettings.objects.get_or_create(pk=1)
    return obj


def _stored_chat() -> str:
    try:
        value = cache.get(CACHE_KEY)
    except Exception:  # noqa: BLE001 - no cache: read the DB every time
        value = None
    if value is None:
        from apps.telegram_bot.infrastructure.models import OrdersChannelSettings

        try:
            value = OrdersChannelSettings.objects.filter(pk=1).values_list("chat_id", flat=True).first() or ""
        except DatabaseError:
            return ""
        try:
            cache.set(CACHE_KEY, value, 300)
        except Exception:  # noqa: BLE001
            pass
    return value


def _forget() -> None:
    try:
        cache.delete(CACHE_KEY)
    except Exception:  # noqa: BLE001
        pass


def chat_id() -> str:
    """The Orders channel chat id ("" = not connected → every poster stays silent)."""
    return _stored_chat() or _env_chat()


# ------------------------------------------------------------------------------------------------ connecting


def _remember(chat: dict, status: str, can_post: bool) -> None:
    from apps.telegram_bot.infrastructure.models import TelegramBotChat

    if not chat.get("id"):
        return
    TelegramBotChat.objects.update_or_create(
        bot="orders", chat_id=int(chat["id"]),
        defaults={"title": (chat.get("title") or "")[:255], "chat_type": chat.get("type") or "", "username": chat.get("username") or "",
                  "status": status, "can_post": can_post},
    )


def _can_post(chat_type: str, member: dict) -> bool:
    status = member.get("status")
    if status == "creator":
        return True
    if status == "administrator":
        return chat_type != "channel" or bool(member.get("can_post_messages"))
    return status == "member" and chat_type in ("group", "supergroup")


def _fast_forward_cursors() -> None:
    """New chat: start from "now" for every channel poster -- no replay of old orders/sales into it."""
    from apps.ordering.infrastructure import models as ordering_orm
    from apps.pos.infrastructure import models as pos_orm
    from apps.telegram_bot.infrastructure.after_sales_channel_subscriber import AFTER_SALES_CURSOR_ID, EVENT_TYPES
    from apps.telegram_bot.infrastructure.models import TelegramOrdersChannelCursor
    from apps.telegram_bot.infrastructure.pos_sales_channel_subscriber import _EVENT_KINDS, POS_CURSOR_ID

    sources = {
        1: ordering_orm.OrderingOutboxEvent.objects.filter(event_type="OrderCreated"),
        POS_CURSOR_ID: pos_orm.PosOutboxEvent.objects.filter(event_type__in=list(_EVENT_KINDS)),
        AFTER_SALES_CURSOR_ID: ordering_orm.OrderingOutboxEvent.objects.filter(event_type__in=EVENT_TYPES),
    }
    for cursor_id, qs in sources.items():
        latest = qs.order_by("-created_at", "-id").first()
        if latest is None:
            continue
        TelegramOrdersChannelCursor.objects.update_or_create(
            id=cursor_id, defaults={"last_processed_created_at": latest.created_at, "last_processed_id": latest.id})


def connect(chat: dict, by: str, *, welcome: bool = True) -> tuple[bool, str]:
    """Make `chat` (a Telegram Chat object) the Orders channel."""
    new_id = str(chat.get("id") or "").strip()
    if not new_id:
        return False, "Chat ID topilmadi."
    obj = _settings()
    previous = obj.chat_id or _env_chat()
    obj.chat_id = new_id
    obj.title = (chat.get("title") or chat.get("username") or "")[:255]
    obj.chat_type = chat.get("type") or ""
    obj.username = chat.get("username") or ""
    obj.connected_at = timezone.now()
    obj.connected_by = (by or "")[:150]
    obj.last_error = ""
    obj.save()
    _forget()
    if previous != new_id:
        try:
            _fast_forward_cursors()
        except Exception:  # noqa: BLE001 - a cursor problem must not undo the connection
            logger.exception("Orders channel: cursor fast-forward failed.")
    logger.info("Orders channel connected: %s (%s) by %s", new_id, obj.title, by)
    if welcome:
        _send(new_id, _welcome_text(obj.title))
    return True, f"«{obj.title or new_id}» buyurtmalar kanali sifatida ulandi."


def disconnect(by: str) -> tuple[bool, str]:
    obj = _settings()
    obj.chat_id = obj.title = obj.chat_type = obj.username = obj.last_error = ""
    obj.connected_at = None
    obj.connected_by = (by or "")[:150]
    obj.save()
    _forget()
    if _env_chat():
        return True, "Kanal uzildi. Diqqat: serverdagi TELEGRAM_ORDERS_CHAT_ID hali ham amal qiladi."
    return True, "Kanal uzildi — buyurtmalar endi kanalga yuborilmaydi."


def _normalize_ref(ref: str) -> str:
    ref = (ref or "").strip()
    m = re.match(r"^(?:https?://)?(?:t\.me|telegram\.me)/(?:s/)?([A-Za-z0-9_]{4,})/?$", ref)
    if m:
        return "@" + m.group(1)
    if re.fullmatch(r"-?\d{5,20}", ref):
        return ref
    if re.fullmatch(r"@?[A-Za-z][A-Za-z0-9_]{3,}", ref):
        return "@" + ref.lstrip("@")
    return ""


def connect_ref(ref: str, by: str) -> tuple[bool, str]:
    """Dashboard: connect by @username / numeric id / t.me link -- checked live with getChat + getChatMember."""
    if not _token():
        return False, "Orders bot tokeni (TELEGRAM_ORDERS_BOT_TOKEN) sozlanmagan."
    target = _normalize_ref(ref)
    if not target:
        return False, "Kanalni @username, t.me havola yoki -100… ID ko'rinishida kiriting."
    try:
        chat = R._api(_token(), "getChat", json_body={"chat_id": target})
        me = R._api(_token(), "getMe", json_body={})
        member = R._api(_token(), "getChatMember", json_body={"chat_id": chat["id"], "user_id": me["id"]})
    except R.RichSendError as exc:
        return False, f"Telegram kanalni topmadi yoki bot unga qo'shilmagan ({exc}). Botni kanalga admin qilib qo'shing."
    can_post = _can_post(chat.get("type", ""), member)
    _remember(chat, member.get("status", ""), can_post)
    if not can_post:
        return False, "Bot kanalda admin emas yoki «Xabar yuborish» ruxsati yo'q. Ruxsatni yoqib, qayta urinib ko'ring."
    return connect(chat, by)


# ------------------------------------------------------------------------------------------------ webhook updates


def _is_command(text: str) -> bool:
    word = (text or "").strip().split(maxsplit=1)[0].lower() if (text or "").strip() else ""
    return word.split("@", 1)[0] in CONNECT_COMMANDS


def _is_group_admin(chat_id_, user_id) -> bool:
    try:
        member = R._api(_token(), "getChatMember", json_body={"chat_id": chat_id_, "user_id": user_id})
    except R.RichSendError:
        return False
    return member.get("status") in POSTING


def _is_staff(tg_user_id) -> bool:
    """Customer data goes to this chat, so only NutriZone staff may pick it from Telegram."""
    if not tg_user_id:
        return False
    from apps.telegram_bot.infrastructure.models import TelegramStaffMember

    return TelegramStaffMember.objects.filter(telegram_user_id=tg_user_id, is_active=True).exists()


def _who(user: dict | None) -> str:
    if not user:
        return "Telegram"
    name = " ".join(x for x in (user.get("first_name"), user.get("last_name")) if x)
    return f"Telegram: {name or user.get('username') or user.get('id')}"


def handle_update(update: dict) -> bool:
    """True when the update was about the Orders bot's chats (handled here); False → let the other handlers run."""
    try:
        return _handle(update)
    except Exception:  # noqa: BLE001 - never break the webhook
        logger.exception("Orders channel: failed to handle a chat update.")
        return True


def _handle(update: dict) -> bool:
    mcm = update.get("my_chat_member")
    if mcm:
        chat, member = mcm.get("chat") or {}, mcm.get("new_chat_member") or {}
        if chat.get("type") == "private":
            return False
        status = member.get("status", "")
        can_post = _can_post(chat.get("type", ""), member)
        _remember(chat, status, can_post)
        current = chat_id()
        if str(chat.get("id")) == current and not can_post:
            obj = _settings()
            if obj.chat_id == current:
                obj.last_error = "Bot kanaldan chiqarildi yoki xabar yuborish ruxsati olib qo'yildi." if status in ("left", "kicked") else "Botda «Xabar yuborish» ruxsati yo'q."
                obj.save(update_fields=["last_error", "updated_at"])
            logger.warning("Orders channel: bot lost posting rights in %s (status %s).", current, status)
        elif can_post and status in POSTING and not current and _is_staff((mcm.get("from") or {}).get("id")):
            connect(chat, _who(mcm.get("from")) + " (avtomatik)")
        elif can_post and str(chat.get("id")) == current:
            obj = _settings()
            if obj.last_error and obj.chat_id == current:
                obj.last_error = ""
                obj.save(update_fields=["last_error", "updated_at"])
        return True

    post = update.get("channel_post")
    if post:
        chat = post.get("chat") or {}
        _remember(chat, "administrator", True)  # channel posts only reach the bot when it is an admin there
        return True

    message = update.get("message") or {}
    chat = message.get("chat") or {}
    if chat.get("type") not in ("group", "supergroup"):
        return False
    if message.get("migrate_to_chat_id"):
        new_id = str(message["migrate_to_chat_id"])
        obj = _settings()
        if obj.chat_id == str(chat.get("id")):
            obj.chat_id, obj.chat_type = new_id, "supergroup"
            obj.save(update_fields=["chat_id", "chat_type", "updated_at"])
            _forget()
        return True
    if _is_command(message.get("text") or ""):
        user = message.get("from") or {}
        if _is_staff(user.get("id")) and _is_group_admin(chat.get("id"), user.get("id")):
            _remember(chat, "member", True)
            connect(chat, _who(user) + " (/ulash)")
        else:
            _send(chat.get("id"), "⛔️ Guruhni buyurtmalar kanali qilib faqat NutriZone xodimi bo'lgan guruh admini ulay oladi. Yoki Dashboard → Telegram botlar markazi orqali ulang.")
        return True
    return False


# ------------------------------------------------------------------------------------------------ messages


def _welcome_text(title: str) -> str:
    return (
        "✅ <b>NutriZone buyurtmalar kanali ulandi</b>\n\n"
        f"«{html.escape(title or 'Kanal')}» endi quyidagilarni oladi:\n"
        "🛒 yangi onlayn buyurtmalar — mahsulotlar, summa, manzil va xarita bilan\n"
        "✔️ «Tasdiqlash / Bekor qilish» tugmalari\n"
        "🧾 kassa savdolari va qaytarishlar\n"
        "↩️ qaytarish va bekor qilish so'rovlari\n\n"
        "<i>Bundan oldingi buyurtmalar qayta yuborilmaydi.</i>"
    )


def _send(chat, text: str) -> bool:
    if not _token() or not chat:
        return False
    try:
        R._api(_token(), "sendMessage", json_body={"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True})
        return True
    except R.RichSendError as exc:
        logger.warning("Orders channel: sendMessage to %s failed: %s", chat, exc)
        obj = _settings()
        if obj.chat_id == str(chat):
            obj.last_error = str(exc)[:500]
            obj.save(update_fields=["last_error", "updated_at"])
        return False


def send_test(by: str) -> tuple[bool, str]:
    target = chat_id()
    if not target:
        return False, "Buyurtmalar kanali hali ulanmagan."
    if not _token():
        return False, "Orders bot tokeni (TELEGRAM_ORDERS_BOT_TOKEN) sozlanmagan."
    stamp = timezone.localtime().strftime("%d.%m.%Y %H:%M")
    ok = _send(target, f"🧪 <b>Test xabar</b> · {stamp}\nBuyurtmalar kanali ishlayapti. Yuborgan: {html.escape(by)}")
    if ok:
        obj = _settings()
        if obj.last_error:
            obj.last_error = ""
            obj.save(update_fields=["last_error", "updated_at"])
        return True, "Test xabar kanalga yuborildi."
    return False, "Xabar yuborilmadi: " + (_settings().last_error or "bot kanalda admin emas.")


def status() -> dict:
    from apps.telegram_bot.infrastructure.models import OrdersChannelSettings, TelegramBotChat

    obj = OrdersChannelSettings.objects.filter(pk=1).first()
    stored = obj.chat_id if obj else ""
    env = _env_chat()
    current = stored or env
    chats = list(TelegramBotChat.objects.filter(bot="orders").exclude(status__in=("left", "kicked"))[:20])
    chats.sort(key=lambda c: str(c.chat_id) != current)  # the connected one first
    return {
        "connected": bool(current),
        "source": "dashboard" if stored else ("env" if env else ""),
        "chat_id": current,
        "title": (obj.title if stored and obj else "") or next((c.title for c in chats if str(c.chat_id) == current), ""),
        "username": obj.username if stored and obj else "",
        "chat_type": obj.chat_type if stored and obj else "",
        "connected_at": obj.connected_at if stored and obj else None,
        "connected_by": obj.connected_by if stored and obj else "",
        "error": obj.last_error if obj else "",
        "token": bool(_token()),
        "bot_username": (getattr(settings, "TELEGRAM_ORDERS_BOT_USERNAME", "") or "").lstrip("@"),
        "chats": [{"id": c.chat_id, "title": c.title or str(c.chat_id), "type": c.chat_type, "username": c.username, "status": c.status,
                   "can_post": c.can_post, "current": str(c.chat_id) == current} for c in chats],
    }
