"""
NutriZoneAnalyticsBot -- the management's own Telegram bot (a third bot, next to the customer bot and the Orders
bot): scheduled daily / weekly / monthly business reports, on-demand reports from a button menu, and the
"javobsiz chat" alerts of the support desk.

Who may use it: only the chat ids listed in TELEGRAM_ANALYTICS_CHAT_IDS (people or groups). These reports carry
company-wide money figures, so access is an explicit server-side allowlist -- never self-service. Anyone else who
writes to the bot only learns their own chat id (to hand to the administrator).

Scheduled reports are de-duplicated per (report, period, chat) in Redis, so a re-run beat tick, a retried task or
two workers never deliver the same report twice.

Settings:
    TELEGRAM_ANALYTICS_BOT_TOKEN       the bot's token (@BotFather)
    TELEGRAM_ANALYTICS_BOT_USERNAME    NutriZoneAnalyticsBot
    TELEGRAM_ANALYTICS_WEBHOOK_SECRET  X-Telegram-Bot-Api-Secret-Token of its webhook (/api/v1/telegram/analytics-webhook)
    TELEGRAM_ANALYTICS_CHAT_IDS        comma-separated recipients, e.g. "123456789,-1001234567890"
"""
from __future__ import annotations

import contextlib
import logging
from datetime import timedelta
from html import escape

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("nutrizone.telegram_bot.analytics")

SCHEDULED = ("today", "week", "month")  # 23:59 daily, Monday weekly, 1st-of-month monthly
DEDUPE_TTL = 60 * 60 * 24 * 40
COMMANDS = [
    ("bugun", "📈 Bugungi puls"), ("kecha", "📅 Kechagi hisobot"), ("hafta", "🗓 O'tgan hafta"), ("oy", "🗓 O'tgan oy"),
    ("moliya", "💵 Moliya va to'lovlar (30 kun)"), ("filiallar", "🏪 Filiallar reytingi (bugun)"), ("mahsulotlar", "🔥 Top mahsulotlar (7 kun)"),
    ("ombor", "📦 Ombor nazorati"), ("nazorat", "🛡 Nazorat markazi (jonli)"), ("reja", "🎯 Sotuv rejasi (oy)"), ("chatlar", "💬 Javobsiz chatlar"), ("filial", "🏪 Filialni tanlash"), ("menu", "☰ Menyu"), ("id", "🆔 Chat ID"),
]
ALIASES = {"today": "bugun", "yesterday": "kecha", "week": "hafta", "month": "oy", "start": "menu", "help": "menu", "stores": "filiallar",
           "products": "mahsulotlar", "stock": "ombor", "chats": "chatlar", "finance": "moliya", "filial": "store", "branch": "store", "control": "nazorat", "live": "nazorat", "plan": "reja"}
# command → (period key, layout)
REPORTS = {
    "bugun": ("today", None), "kecha": ("yesterday", None), "hafta": ("week", None), "oy": ("month", None),
    "moliya": ("30d", "finance"), "filiallar": ("today", "stores"), "mahsulotlar": ("7d", "products"), "ombor": ("today", "inventory"),
    "7kun": ("7d", None), "30kun": ("30d", None), "shuoy": ("this_month", None),
}


# ---------------------------------------------------------------- config


def token() -> str:
    return getattr(settings, "TELEGRAM_ANALYTICS_BOT_TOKEN", None) or ""


def username() -> str:
    return getattr(settings, "TELEGRAM_ANALYTICS_BOT_USERNAME", None) or "NutriZoneAnalyticsBot"


def recipients() -> list[str]:
    raw = getattr(settings, "TELEGRAM_ANALYTICS_CHAT_IDS", "") or ""
    return [c.strip() for c in str(raw).replace(";", ",").split(",") if c.strip().lstrip("-").isdigit()]


def is_live() -> bool:
    return getattr(settings, "NUTRIZONE_TELEGRAM_GATEWAY", "disabled") == "live" and bool(token())


def is_configured() -> bool:
    return is_live() and bool(recipients())


def authorized(chat_id) -> bool:
    return str(chat_id) in recipients()


def mask_chat(chat_id: str) -> str:
    s = str(chat_id)
    return s if len(s) <= 4 else f"{s[:2]}…{s[-3:]}"


# ---------------------------------------------------------------- Bot API


class BotApiError(Exception):
    pass


def call(method: str, payload: dict) -> dict:
    """One Bot API call with the analytics bot's token. The token is only in the URL, which is never logged."""
    if not is_live():
        raise BotApiError("analytics bot is not configured (TELEGRAM_ANALYTICS_BOT_TOKEN / NUTRIZONE_TELEGRAM_GATEWAY=live)")
    base = getattr(settings, "TELEGRAM_API_BASE_URL", "https://api.telegram.org").rstrip("/")
    timeout = float(getattr(settings, "TELEGRAM_TIMEOUT_SECONDS", 10) or 10)
    try:
        response = requests.post(f"{base}/bot{token()}/{method}", json=payload, timeout=timeout)
        body = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise BotApiError(f"{method}: {exc.__class__.__name__}") from exc
    if not body.get("ok"):
        raise BotApiError(f"{method}: {body.get('description', response.status_code)}")
    return body.get("result") or {}


def send(chat_id, text: str, keyboard: list | None = None) -> dict:
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}}
    if keyboard:
        payload["reply_markup"] = {"inline_keyboard": keyboard}
    return call("sendMessage", payload)


def send_many(chat_id, messages: list[str], keyboard: list | None = None) -> int:
    """Sends a split report in order; the keyboard goes under the last part."""
    for i, text in enumerate(messages):
        send(chat_id, text, keyboard if i == len(messages) - 1 else None)
    return len(messages)


# ---------------------------------------------------------------- reports


def build_messages(command: str, on_demand: bool = True) -> list[str]:
    from apps.platform.infrastructure import business_analytics as ba
    from apps.telegram_bot.infrastructure import analytics_report as rep

    key, layout = REPORTS[command]
    return rep.render(ba.build(ba.period(key)), layout=layout, on_demand=on_demand)


def dedupe_key(kind: str, chat_id) -> str:
    from apps.platform.infrastructure import business_analytics as ba

    p = ba.period(kind)
    return f"nz:analytics_bot:sent:{kind}:{p.first_day.isoformat()}:{chat_id}"


def _claim(key: str) -> bool:
    """True once per key (Redis SET NX). Redis being down must not cause a flood of duplicates -- then nothing is sent."""
    from core.caching.redis_client import get_redis_client

    try:
        return bool(get_redis_client().set(key, timezone.now().isoformat(), nx=True, ex=DEDUPE_TTL))
    except Exception:  # noqa: BLE001
        logger.exception("analytics bot: dedupe store unavailable, skipping %s", key)
        return False


def _release(key: str) -> None:
    from core.caching.redis_client import get_redis_client

    with contextlib.suppress(Exception):
        get_redis_client().delete(key)


# ---------------------------------------------------------------- audience & rich reports


def audience() -> list[dict]:
    """Who gets the scheduled reports: the allowlist (company-wide, or the branch they picked) and every branch owner
    who started the bot (their own branches only). One entry per chat."""
    from apps.telegram_bot.infrastructure import staff_access
    from apps.telegram_bot.infrastructure.models import TelegramBotSubscriber

    out, seen = [], set()
    picks = dict(TelegramBotSubscriber.objects.filter(bot="analytics").values_list("chat_id", "store_filter"))
    for chat in recipients():
        pick = picks.get(int(chat)) if chat.lstrip("-").isdigit() else None
        out.append({"chat_id": chat, "store_ids": [pick] if pick else None, "all_access": True})
        seen.add(str(chat))
    for sub in staff_access.subscribers("analytics"):
        if str(sub.chat_id) in seen:
            continue
        stores, _name = staff_access.owned_stores(sub.telegram_user_id or sub.chat_id)
        if stores:
            ids = [st.id for st in stores]
            out.append({"chat_id": str(sub.chat_id), "store_ids": [sub.store_filter] if sub.store_filter in ids else ids, "all_access": False})
            seen.add(str(sub.chat_id))
    return out


def report_doc(command: str, store_ids=None, scheduled: bool = False):
    from apps.platform.infrastructure import business_analytics as ba
    from apps.telegram_bot.infrastructure import analytics_rich

    key, _layout = REPORTS[command]
    return analytics_rich.build_doc(ba.build(ba.period(key), store_ids=store_ids), scheduled=scheduled, dashboard_url=dashboard_url())


def send_report(chat_id, command: str, store_ids=None, scheduled: bool = False, doc=None, all_access: bool = True) -> int:
    from apps.telegram_bot.infrastructure import rich as R

    doc = doc or report_doc(command, store_ids, scheduled)
    try:
        return R.send(token(), chat_id, doc, menu_keyboard(all_access=all_access))
    except R.RichSendError as exc:
        raise BotApiError(str(exc)) from exc


def send_scheduled(kind: str) -> dict:
    """The beat entry point (23:59 daily, Monday weekly, 1st monthly): each recipient's own report, once per period."""
    if kind not in SCHEDULED:
        return {"sent": 0, "reason": "unknown report"}
    if not is_live():
        return {"sent": 0, "reason": "not configured"}
    command = {"today": "bugun", "week": "hafta", "month": "oy"}[kind]
    docs: dict = {}
    sent, skipped, failed = 0, 0, 0
    for target in audience():
        key = dedupe_key(kind, target["chat_id"])
        if not _claim(key):
            skipped += 1
            continue
        scope_key = tuple(sorted(str(x) for x in target["store_ids"])) if target["store_ids"] else ("*",)
        try:
            if scope_key not in docs:
                docs[scope_key] = report_doc(command, target["store_ids"], scheduled=True)
            send_report(target["chat_id"], command, doc=docs[scope_key], all_access=target["all_access"])
            sent += 1
        except BotApiError as exc:
            logger.warning("analytics bot: %s report to %s failed: %s", kind, mask_chat(target["chat_id"]), exc)
            _release(key)  # let a retry deliver it
            failed += 1
        except Exception:  # noqa: BLE001
            logger.exception("analytics bot: building the %s report failed", kind)
            _release(key)
            failed += 1
    return {"sent": sent, "skipped": skipped, "failed": failed}


def send_now(command: str, chat_ids=None) -> dict:
    """Dashboard "send now" button -- an explicit on-demand report to the allowlist (company-wide), not de-duplicated."""
    if not is_live():
        return {"sent": 0, "reason": "not configured"}
    doc = report_doc(command)
    sent, failed = 0, []
    for chat in chat_ids or recipients():
        try:
            send_report(chat, command, doc=doc)
            sent += 1
        except BotApiError as exc:
            logger.warning("analytics bot: send_now to %s failed: %s", mask_chat(chat), exc)
            failed.append(mask_chat(chat))
    return {"sent": sent, "failed": failed, "parts": 1}


# ---------------------------------------------------------------- unanswered chats


def waiting_chat_items() -> list[dict]:
    from apps.chat.infrastructure.automation import waiting_conversations
    from apps.identity.infrastructure.models import User
    from apps.platform.infrastructure.business_analytics import duration

    items = waiting_conversations(timedelta(0))
    users = {u.id: u for u in User.objects.filter(id__in=[i["customer_id"] for i in items])}
    out = []
    for it in sorted(items, key=lambda i: i["message"].created_at):
        u, m = users.get(it["customer_id"]), it["message"]
        minutes = int((timezone.now() - m.created_at).total_seconds() // 60)
        out.append({"conversation_id": it["conversation_id"], "who": customer_label(u), "ago": duration(minutes), "preview": preview(m)})
    return out


def customer_label(u) -> str:
    """Name + a masked phone: enough for staff to recognise the chat, without spreading full numbers into Telegram."""
    if u is None:
        return "Mijoz"
    phone = (u.phone_number or "").strip()
    masked = f"{phone[:-7]}•••{phone[-2:]}" if len(phone) >= 9 else ""
    return " · ".join(x for x in (u.full_name or "Mijoz", masked) if x)


def preview(m) -> str:
    if m.message_type == "sticker":
        return "😀 stiker"
    text = m.content or {"attachment": "📷 rasm", "card": "🔗 karta"}.get(m.message_type, "")
    return text if len(text) <= 160 else text[:157] + "…"


def desk_keyboard(conversation_id=None) -> list:
    from apps.chat.infrastructure.automation import _base_url

    base = _base_url()
    if not base.startswith("https://"):
        return []
    url = f"{base}/django-admin/chat/" + (f"?c={conversation_id}" if conversation_id else "")
    return [[{"text": "Javob berish →" if conversation_id else "Chat markazini ochish →", "url": url}]]


def chat_alert(text: str, conversation_id) -> bool:
    """Support desk → the analytics bot's recipients (used by chat.automation.alert_waiting). False = not delivered anywhere."""
    if not is_configured():
        return False
    delivered = False
    for chat in recipients():
        try:
            send(chat, text, desk_keyboard(conversation_id))
            delivered = True
        except BotApiError:
            logger.exception("analytics bot: chat alert to %s failed", mask_chat(chat))
    return delivered


# ---------------------------------------------------------------- interaction


def dashboard_url() -> str | None:
    base = (getattr(settings, "PUBLIC_BASE_URL", None) or "").rstrip("/")
    return f"{base}/django-admin/analytics/" if base.startswith("https://") else None


def menu_keyboard(all_access: bool = True, store_label: str = "") -> list:
    b = lambda text, cmd: {"text": text, "callback_data": f"an:{cmd}"}  # noqa: E731
    url = dashboard_url()
    rows = [[{"text": "🖥 Dashboard'da ochish", "url": url}]] if url and all_access else []
    rows += [
        [b("📈 Bugun", "bugun"), b("📅 Kecha", "kecha"), b("🗓 Hafta", "hafta")],
        [b("🗓 Oy", "oy"), b("📆 30 kun", "30kun"), b("💬 Chatlar", "chatlar")],
        [b("🛡 Nazorat", "nazorat"), b("🎯 Reja", "reja")],
        [b(f"🏪 Filial: {store_label or 'tanlash'}", "store")],
    ]
    return rows


def _unauthorized_text(chat_id) -> str:
    return ("🔒 <b>NutriZone Analytics</b>\n"
            "Bu bot NutriZone rahbariyati va filial egalari uchun.\n\n"
            f"Sizning chat ID: <code>{escape(str(chat_id))}</code>\n"
            "Kirish uchun ushbu raqamni administratorga yuboring.")


def _scope(chat_id, telegram_user_id=None):
    from apps.telegram_bot.infrastructure import staff_access

    return staff_access.scope("analytics", chat_id, telegram_user_id)


def _subscriber(chat_id):
    from apps.telegram_bot.infrastructure.models import TelegramBotSubscriber

    return TelegramBotSubscriber.objects.filter(bot="analytics", chat_id=chat_id).first()


def _view(sc, chat_id) -> tuple[list | None, str]:
    """(store_ids, label) for this chat: the picked branch if allowed, else everything they may see."""
    sub = _subscriber(chat_id)
    pick = sub.store_filter if sub else None
    if pick and sc.can_see(pick):
        name = next((st.name for st in sc.stores if st.id == pick), "Filial")
        return [pick], name
    if sc.all_access:
        return None, "Barchasi"
    return [st.id for st in sc.stores], (sc.stores[0].name if len(sc.stores) == 1 else f"{len(sc.stores)} ta filial")


def _rich_text(chat_id, html_parts: list[str], fallback: str, keyboard: list | None = None) -> None:
    from apps.telegram_bot.infrastructure import rich as R

    doc = R.RichDoc()
    doc.add(*html_parts)
    doc.fallback = fallback
    R.send(token(), chat_id, doc, keyboard)


def _welcome(chat_id, sc) -> None:
    from apps.telegram_bot.infrastructure import rich as R

    who = R.e(sc.name.split()[0]) if sc.name else ""
    stores = ", ".join(R.b(st.name) for st in sc.stores[:6])
    _rich_text(chat_id, [
        R.h(1, "📊 NutriZone Analytics"),
        R.p(f"Assalomu alaykum{', ' + who if who else ''}! " + ("Siz <b>butun kompaniya</b> analitikasini ko'rasiz — istalgan filialni tanlab kuzatishingiz mumkin."
                                                            if sc.all_access else f"Siz {stores} filiali bo'yicha analitikani ko'rasiz.")),
        R.checklist([("Har kuni 23:59 da — kunning to'liq hisoboti: grafiklar, filiallar, mahsulotlar, kassirlar, to'lovlar", True),
                     ("Dushanba 09:00 — haftalik, oyning 1-kuni — oylik hisobot", True),
                     ("Nazorat markazi: katta chegirma, tezkor qaytarish, kassa farqi, ochilmagan smena haqida darhol xabar", True),
                     ("Javobsiz chatlar haqida darhol xabar" + ("" if sc.all_access else " (filialingiz chatlari)"), True),
                     ("Istalgan payt: Bugun / Kecha / Hafta / Oy / 30 kun tugmalari", True)]),
    ], "📊 <b>NutriZone Analytics</b>\nHar kuni 23:59 da kunlik hisobot keladi.")


def _store_picker(chat_id, sc) -> None:
    from apps.telegram_bot.infrastructure import rich as R

    rows = [[{"text": "🌐 Barcha filiallar", "callback_data": "an:store:all"}]] if sc.all_access or len(sc.stores) > 1 else []
    for k in range(0, len(sc.stores), 2):
        rows.append([{"text": f"🏪 {st.name}"[:40], "callback_data": f"an:store:{st.id}"} for st in sc.stores[k:k + 2]])
    _rich_text(chat_id, [R.h(3, "🏪 Qaysi filialni kuzatamiz?"), R.p("Tanlangan filial barcha hisobotlarga — avtomatik kunlik hisobotga ham — qo'llanadi.")],
               "🏪 Qaysi filialni kuzatamiz?", rows)


def _set_store(chat_id, sc, value: str) -> str:
    import uuid as _uuid

    from apps.telegram_bot.infrastructure.models import TelegramBotSubscriber

    pick = None
    if value != "all":
        try:
            pick = _uuid.UUID(value)
        except ValueError:
            return "?"
        if not sc.can_see(pick):
            return "?"
    TelegramBotSubscriber.objects.filter(bot="analytics", chat_id=chat_id).update(store_filter=pick)
    return next((st.name for st in sc.stores if st.id == pick), "Barcha filiallar")


def _start_report(chat_id, store_ids, label: str, keyboard) -> None:
    """/start: today's report so far for this chat's view (one branch, the owner's branches, or the company)."""
    with contextlib.suppress(BotApiError):
        call("sendChatAction", {"chat_id": chat_id, "action": "upload_photo"})
    try:
        from apps.telegram_bot.infrastructure import rich as R

        _rich_text(chat_id, [f"<p>🏪 Ko'rinish: <b>{escape(label)}</b> · bugungi hisobot 👇</p>"], f"🏪 {escape(label)}")
        R.send(token(), chat_id, report_doc("bugun", store_ids), keyboard)
    except Exception:  # noqa: BLE001 - the welcome already went out; the menu still works
        logger.exception("analytics bot: start report failed for %s", mask_chat(chat_id))
        send(chat_id, f"🏪 Ko'rinish: <b>{escape(label)}</b> · hisobotni tanlang 👇", keyboard)


def _customer_bot_url() -> str:
    name = (getattr(settings, "TELEGRAM_BOT_USERNAME", None) or "").lstrip("@")
    return f"https://t.me/{name}" if name else ""


def _unauthorized(chat_id, telegram_user_id=None) -> None:
    """Why this chat sees nothing yet, and the one step that fixes it."""
    from apps.identity.infrastructure.models import User
    from apps.telegram_bot.infrastructure import rich as R

    user = User.objects.filter(telegram_user_id=telegram_user_id or chat_id).first()
    keyboard = None
    if user is None:
        hint = ("Filial egasi bo'lsangiz: avval shu Telegram akkaunti bilan NutriZone botida ro'yxatdan o'ting (telefon raqamingiz bilan), "
                "so'ng administrator filialni sizga biriktiradi va bu yerda /start bosasiz.")
        url = _customer_bot_url()
        keyboard = [[{"text": "🛍 NutriZone botida ro'yxatdan o'tish", "url": url}], [{"text": "🔄 Qayta tekshirish", "callback_data": "an:start"}]] if url else None
    else:
        hint = (f"Akkauntingiz topildi ({user.phone_number or user.full_name}), lekin sizga hali filial biriktirilmagan. "
                "Administrator Dashboard → Filiallar'da sizni filial egasi qilib belgilagach, /start bosing — filialingiz hisoboti darhol keladi.")
        keyboard = [[{"text": "🔄 Qayta tekshirish", "callback_data": "an:start"}]]
    _rich_text(chat_id, [R.h(2, "🔒 NutriZone Analytics"), R.p("Bu bot NutriZone rahbariyati va filial egalari uchun."), R.quote(R.e(hint)),
                         R.p(f"Rahbariyat uchun chat ID: {R.code(chat_id)}")],
               _unauthorized_text(chat_id) + "\n\n" + escape(hint), keyboard)


def _store_chats(chat_id, store_ids, label: str, keyboard) -> None:
    """A branch owner's own waiting customer chats (the support desk's list is for the company view)."""
    from apps.chat.infrastructure.models import ConversationModel, MessageModel, ParticipantModel
    from apps.identity.infrastructure.models import User
    from apps.platform.infrastructure.business_analytics import duration
    from apps.telegram_bot.infrastructure import rich as R

    convs = dict(ConversationModel.objects.filter(conversation_type="customer_sales", status="open", store_id__in=list(store_ids)).values_list("id", "store_id"))
    customers = dict(ParticipantModel.objects.filter(conversation_id__in=list(convs), role="customer").values_list("conversation_id", "user_id"))
    waiting = [m for m in MessageModel.objects.filter(conversation_id__in=list(convs)).order_by("conversation_id", "-created_at").distinct("conversation_id")
               if customers.get(m.conversation_id) == m.sender_id]
    users = {u.id: u for u in User.objects.filter(id__in=[m.sender_id for m in waiting])}
    rows = [[R.b(customer_label(users.get(m.sender_id))), R.e(preview(m)[:60]), R.e(duration(int((timezone.now() - m.created_at).total_seconds() // 60)))]
            for m in sorted(waiting, key=lambda m: m.created_at)]
    parts = [R.h(2, f"💬 Javobsiz chatlar · {R.e(label)}")]
    parts.append(R.table(["Mijoz", "Xabar", "Kutmoqda"], rows, align=["left", "left", "center"]) if rows else R.p("✅ Hamma chatlarga javob berilgan"))
    _rich_text(chat_id, parts, f"💬 Javobsiz chatlar: {len(rows)} ta", keyboard)


def _plan(chat_id, store_ids, label: str, keyboard) -> None:
    """/reja: the month against the sales plan (company, or the branches this chat sees)."""
    from apps.platform.infrastructure import sales_plan
    from apps.telegram_bot.infrastructure import rich as R

    try:
        R.send(token(), chat_id, sales_plan.telegram_doc(store_ids, label), keyboard)
    except Exception:  # noqa: BLE001
        logger.exception("analytics bot: reja failed")
        send(chat_id, "⚠️ Reja hisobotini tayyorlab bo'lmadi. Birozdan keyin qayta urinib ko'ring.", keyboard)


def _control(chat_id, store_ids, label: str, keyboard) -> None:
    """/nazorat: branches right now (tills, money vs yesterday) + the control centre's open alerts."""
    from apps.platform.infrastructure import control_center
    from apps.telegram_bot.infrastructure import rich as R

    try:
        R.send(token(), chat_id, control_center.live_doc(store_ids, label), keyboard)
    except Exception:  # noqa: BLE001
        logger.exception("analytics bot: nazorat failed")
        send(chat_id, "⚠️ Nazorat holatini tayyorlab bo'lmadi. Birozdan keyin qayta urinib ko'ring.", keyboard)


def _ack(chat_id, sc, alert_id: str, keyboard) -> None:
    """"✅ Ko'rildi" under an alert: closes it -- company-wide recipients any alert, a branch owner only their branches'."""
    import uuid as _uuid

    from apps.platform.infrastructure import control_center

    try:
        aid = _uuid.UUID(alert_id)
    except ValueError:
        return
    done = control_center.resolve(aid, f"{sc.name or 'Telegram'} (Telegram)", "Telegram'da ko'rildi", None if sc.all_access else sc.store_ids)
    send(chat_id, "✅ Signal yopildi." if done else "ℹ️ Bu signal allaqachon yopilgan yoki sizga tegishli emas.", keyboard)


def _store_command(chat_id, sc, command: str) -> None:
    """The branch picker, or the branch picked from it (an:store:<id>)."""
    if command == "store":
        _store_picker(chat_id, sc)
        return
    name = _set_store(chat_id, sc, command.split(":", 1)[1])
    _store_ids, label = _view(sc, chat_id)
    _rich_text(chat_id, [f"<p>✅ Endi ko'rinish: <b>{escape(name)}</b></p>"], f"✅ {escape(name)}", menu_keyboard(sc.all_access, label))


def _control_command(chat_id, sc, command: str, store_ids, label: str, keyboard) -> None:
    if command == "nazorat":
        _control(chat_id, store_ids, label, keyboard)
    elif command == "reja":
        _plan(chat_id, store_ids, label, keyboard)
    elif command.startswith(("trq:", "trs:")):
        _transfer_request(chat_id, sc, command, keyboard)
    else:
        _ack(chat_id, sc, command.split(":", 1)[1], keyboard)


def _transfer_request(chat_id, sc, command: str, keyboard) -> None:
    """"📦 Transfer so'rash": a transfer draft warehouse → branch (one product, or everything the branch is short of)."""
    import uuid as _uuid

    from apps.platform.infrastructure import control_center
    from apps.telegram_bot.infrastructure import rich as R

    kind, raw = command.split(":", 1)
    try:
        target = _uuid.UUID(raw)
    except ValueError:
        return
    actor = f"{sc.name or 'Telegram'} (Telegram)"
    allowed = None if sc.all_access else sc.store_ids
    try:
        res = (control_center.request_transfer_for_alert(target, actor, allowed) if kind == "trq"
               else control_center.request_transfer(target, actor, None, allowed))
    except Exception:  # noqa: BLE001 - never leave the button without an answer
        logger.exception("analytics bot: transfer request failed")
        res = {"ok": False, "reason": "Transfer qoralamasini yaratib bo'lmadi. Dashboard'da tekshiring."}
    if not res["ok"]:
        send(chat_id, f"ℹ️ {escape(res['reason'])}", keyboard)
        return
    t = res["transfer"]
    base = (getattr(settings, "PUBLIC_BASE_URL", None) or "").rstrip("/")
    link = [[{"text": "🖥 Transferni ochish", "url": f"{base}/django-admin/stores/stocktransfer/{t.pk}/work/"}]] if base.startswith("https://") else []
    _rich_text(chat_id, [
        R.h(3, f"📦 {R.e(t.number)} — transfer so'rovi yaratildi"),
        R.table([], [[R.e("Qayerdan"), R.b(res["source"].name)], [R.e("Qayerga"), R.b(res["store"].name)],
                     [R.e("Mahsulotlar"), R.b(str(res["lines"]))], [R.e("Jami"), R.b(f"{res['units']} dona")]], align=["left", "left"]),
        R.p("Bu — qoralama: sklad tekshirib, band qiladi va jo'natadi. Qoldiq hozircha o'zgarmadi."),
    ], f"📦 <b>{escape(t.number)}</b> — transfer so'rovi: {escape(res['source'].name)} → {escape(res['store'].name)}, {res['lines']} mahsulot, {res['units']} dona.", link + keyboard)


def run_command(chat_id, command: str, telegram_user_id=None) -> None:
    starting = command == "start"
    command = ALIASES.get(command, command)
    if command == "id":
        send(chat_id, f"🆔 Chat ID: <code>{escape(str(chat_id))}</code>")
        return
    sc = _scope(chat_id, telegram_user_id)
    if not sc.allowed:
        _unauthorized(chat_id, telegram_user_id)
        return
    store_ids, label = _view(sc, chat_id)
    keyboard = menu_keyboard(sc.all_access, label)
    if command == "menu":
        _welcome(chat_id, sc)
        if starting:  # /start: the report for what this chat may see right away -- a branch owner gets their own branch
            _start_report(chat_id, store_ids, label, keyboard)
            return
        _rich_text(chat_id, [f"<p>🏪 Ko'rinish: <b>{escape(label)}</b> · hisobotni tanlang 👇</p>"], f"🏪 {escape(label)}", keyboard)
        return
    if command == "store" or command.startswith("store:"):
        _store_command(chat_id, sc, command)
        return
    if command in ("nazorat", "reja") or command.startswith(("ack:", "trq:", "trs:")):
        _control_command(chat_id, sc, command, store_ids, label, keyboard)
        return
    if command == "chatlar":
        if sc.all_access and store_ids is None:
            from apps.telegram_bot.infrastructure import analytics_report as rep

            send_many(chat_id, rep.split([rep.chats(waiting_chat_items())]), desk_keyboard() + keyboard)
        else:
            _store_chats(chat_id, store_ids, label, keyboard)
        return
    if command not in REPORTS:
        send(chat_id, "Bunday buyruq yo'q. /menu", keyboard)
        return
    with contextlib.suppress(BotApiError):
        call("sendChatAction", {"chat_id": chat_id, "action": "upload_photo"})
    try:
        doc = report_doc(command, store_ids)
        from apps.telegram_bot.infrastructure import rich as R

        R.send(token(), chat_id, doc, keyboard)
    except Exception:  # noqa: BLE001 - never leave the user without an answer
        logger.exception("analytics bot: building %s failed", command)
        send(chat_id, "⚠️ Hisobotni tayyorlab bo'lmadi. Birozdan keyin qayta urinib ko'ring.", keyboard)


def handle_update(update: dict) -> None:
    """One webhook / getUpdates update."""
    from apps.telegram_bot.infrastructure import staff_access

    callback = update.get("callback_query")
    if callback:
        chat_id = ((callback.get("message") or {}).get("chat") or {}).get("id")
        data = callback.get("data") or ""
        with contextlib.suppress(BotApiError):
            call("answerCallbackQuery", {"callback_query_id": callback.get("id")})
        if chat_id and data.startswith("an:"):
            run_command(chat_id, data[3:], (callback.get("from") or {}).get("id"))
        return
    message = update.get("message") or update.get("channel_post")
    if not message:
        return
    chat_id = (message.get("chat") or {}).get("id")
    if chat_id and (message.get("chat") or {}).get("type") == "private":
        staff_access.register("analytics", message)
    text = (message.get("text") or "").strip()
    who = (message.get("from") or {}).get("id")
    if not chat_id or not text.startswith("/"):
        if chat_id and message.get("chat", {}).get("type") == "private":
            run_command(chat_id, "menu", who)
        return
    command = text[1:].split()[0].split("@")[0].lower()
    run_command(chat_id, command, who)


def set_commands() -> None:
    call("setMyCommands", {"commands": [{"command": c, "description": d} for c, d in COMMANDS]})
    call("setMyDescription", {"description": "NutriZone rahbariyati uchun biznes analitikasi: kunlik, haftalik va oylik hisobotlar, filiallar, mahsulotlar, ombor va javobsiz chatlar."})
    call("setMyShortDescription", {"short_description": "NutriZone biznes analitikasi"})
