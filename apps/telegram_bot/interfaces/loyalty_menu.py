"""
Telegram bot → "🪙 Bonuslarim" (loyalty & wallet) section.

    menu:loyalty      wallet card: balance, tier, progress to next tier, expiring coins
    menu:loyalty_ref  personal invite link + share button + invite stats
    menu:loyalty_hist last coin movements

Plus the referral deep link: /start ref_<CODE>. A brand-new Telegram user's
code is parked in Redis until onboarding creates their account
(apply_pending_referral), an existing customer's is applied immediately if
they are still eligible (no delivered order yet).

All numbers come from apps.loyalty's own services -- this module only renders.
"""
from __future__ import annotations

import logging
from urllib.parse import quote

from django.conf import settings
from django.utils import timezone

from core.caching.redis_client import cache_key, get_redis_client

logger = logging.getLogger("nutrizone.app")

_OWN_ORDER_KINDS = ("earn", "spend", "refund", "reversal")  # a referral row references the friend's order -- never shown
_PENDING_TTL = 60 * 60 * 24  # a day to finish onboarding after tapping an invite link

TIER_EMOJI = {"bronze": "🥉", "silver": "🥈", "gold": "🥇", "platinum": "💠", "diamond": "💎", "elite": "🛡", "legend": "🔥", "vip": "👑"}

TEXT = {
    "uz": {
        "title": "🪙 <b>NutriZone Coins</b>",
        "balance": "💰 Balans: <b>{balance} coin</b>",
        "tier": "{emoji} Tarif: <b>{tier}</b> · har xariddan <b>{percent}%</b>",
        "no_tier": "Birinchi yetkazilgan buyurtmadan so'ng tarifingiz faollashadi.",
        "progress": "{bar}  {progress}%\n➡️ <b>{next}</b> ({next_percent}%) gacha yana <b>{amount} so'm</b>",
        "top": "👑 Siz eng oliy tarifdasiz!",
        "window": "ℹ️ Tarif oxirgi {days} kundagi xaridlaringiz asosida hisoblanadi.",
        "expiring": "⏳ <b>{coins} coin</b> {date} kuni kuyadi — xaridda ishlating!",
        "redeem": "🛒 Buyurtmaning {percent}% gacha qismini coin bilan to'lash mumkin (1 coin = 1 so'm).",
        "btn_ref": "🤝 Do'st taklif qilish",
        "btn_hist": "📜 Coinlar tarixi",
        "btn_site": "🌐 Saytda ochish",
        "btn_back": "⬅️ Menyu",
        "ref_title": "🤝 <b>Do'stlaringizni taklif qiling</b>",
        "ref_body": "Do'stingiz havola orqali ro'yxatdan o'tib, birinchi buyurtmasi yetkazilganda:\n• sizga <b>+{referrer} coin</b>\n• do'stingizga <b>+{referee} coin</b>",
        "ref_code": "Sizning kodingiz: <code>{code}</code>",
        "ref_link": "🔗 Havola: {link}",
        "ref_stats": "👥 Taklif qilinganlar: <b>{invited}</b> · bonus olinganlar: <b>{rewarded}</b> · jami: <b>{earned} coin</b>",
        "ref_share_text": "NutriZone'da sport ovqatlanishini xarid qiling va {coins} coin bonus oling! 🎁",
        "btn_share": "📤 Havolani ulashish",
        "ref_disabled": "Taklif dasturi hozircha to'xtatilgan.",
        "hist_title": "📜 <b>Oxirgi harakatlar</b>",
        "hist_empty": "Hali coin harakatlari yo'q.",
        "kind": {"earn": "Buyurtma uchun", "referral": "Taklif bonusi", "refund": "Qaytarildi", "adjustment": "Tuzatish", "spend": "Xaridda sarflandi", "reversal": "Qaytarib olindi", "expiry": "Muddati tugadi"},
        "ref_applied": "🎁 Taklif kodi qabul qilindi! Birinchi buyurtmangiz yetkazilganda <b>+{coins} coin</b> olasiz.",
        "ref_rejected": "Taklif kodi qo'llanilmadi: bu kod yangi mijozlar uchun.",
    },
    "ru": {
        "title": "🪙 <b>NutriZone Coins</b>",
        "balance": "💰 Баланс: <b>{balance} коинов</b>",
        "tier": "{emoji} Уровень: <b>{tier}</b> · <b>{percent}%</b> с покупки",
        "no_tier": "Уровень активируется после первого доставленного заказа.",
        "progress": "{bar}  {progress}%\n➡️ До <b>{next}</b> ({next_percent}%) осталось <b>{amount} сум</b>",
        "top": "👑 У вас высший уровень!",
        "window": "ℹ️ Уровень считается по покупкам за последние {days} дней.",
        "expiring": "⏳ <b>{coins} коинов</b> сгорят {date} — потратьте их!",
        "redeem": "🛒 Коинами можно оплатить до {percent}% заказа (1 коин = 1 сум).",
        "btn_ref": "🤝 Пригласить друга",
        "btn_hist": "📜 История коинов",
        "btn_site": "🌐 Открыть на сайте",
        "btn_back": "⬅️ Меню",
        "ref_title": "🤝 <b>Приглашайте друзей</b>",
        "ref_body": "Когда друг зарегистрируется по ссылке и получит первый заказ:\n• вам <b>+{referrer} коинов</b>\n• другу <b>+{referee} коинов</b>",
        "ref_code": "Ваш код: <code>{code}</code>",
        "ref_link": "🔗 Ссылка: {link}",
        "ref_stats": "👥 Приглашено: <b>{invited}</b> · с бонусом: <b>{rewarded}</b> · всего: <b>{earned} коинов</b>",
        "ref_share_text": "Покупайте спортивное питание в NutriZone и получите {coins} бонусных коинов! 🎁",
        "btn_share": "📤 Поделиться ссылкой",
        "ref_disabled": "Реферальная программа временно приостановлена.",
        "hist_title": "📜 <b>Последние операции</b>",
        "hist_empty": "Операций с коинами пока нет.",
        "kind": {"earn": "За заказ", "referral": "Бонус за приглашение", "refund": "Возврат", "adjustment": "Корректировка", "spend": "Оплата заказа", "reversal": "Списано (возврат)", "expiry": "Сгорели"},
        "ref_applied": "🎁 Код приглашения принят! Когда ваш первый заказ будет доставлен, вы получите <b>+{coins} коинов</b>.",
        "ref_rejected": "Код не применён: он предназначен для новых покупателей.",
    },
    "en": {
        "title": "🪙 <b>NutriZone Coins</b>",
        "balance": "💰 Balance: <b>{balance} coins</b>",
        "tier": "{emoji} Tier: <b>{tier}</b> · <b>{percent}%</b> back per order",
        "no_tier": "Your tier activates after your first delivered order.",
        "progress": "{bar}  {progress}%\n➡️ <b>{amount} UZS</b> more to <b>{next}</b> ({next_percent}%)",
        "top": "👑 You're on the top tier!",
        "window": "ℹ️ Your tier is based on purchases in the last {days} days.",
        "expiring": "⏳ <b>{coins} coins</b> expire on {date} — use them!",
        "redeem": "🛒 Coins can cover up to {percent}% of an order (1 coin = 1 UZS).",
        "btn_ref": "🤝 Invite a friend",
        "btn_hist": "📜 Coin history",
        "btn_site": "🌐 Open on the website",
        "btn_back": "⬅️ Menu",
        "ref_title": "🤝 <b>Invite your friends</b>",
        "ref_body": "When a friend signs up with your link and their first order is delivered:\n• you get <b>+{referrer} coins</b>\n• they get <b>+{referee} coins</b>",
        "ref_code": "Your code: <code>{code}</code>",
        "ref_link": "🔗 Link: {link}",
        "ref_stats": "👥 Invited: <b>{invited}</b> · rewarded: <b>{rewarded}</b> · total: <b>{earned} coins</b>",
        "ref_share_text": "Shop sports nutrition at NutriZone and get {coins} bonus coins! 🎁",
        "btn_share": "📤 Share link",
        "ref_disabled": "The referral programme is paused right now.",
        "hist_title": "📜 <b>Recent activity</b>",
        "hist_empty": "No coin activity yet.",
        "kind": {"earn": "Order reward", "referral": "Referral bonus", "refund": "Refunded", "adjustment": "Adjustment", "spend": "Spent at checkout", "reversal": "Reversed", "expiry": "Expired"},
        "ref_applied": "🎁 Invite code accepted! You'll get <b>+{coins} coins</b> when your first order is delivered.",
        "ref_rejected": "Invite code not applied: it's for new customers only.",
    },
}


def _t(lang: str) -> dict:
    from apps.platform.infrastructure.branding import rebrand

    return {k: rebrand(v) for k, v in TEXT.get(lang, TEXT["uz"]).items()}


def _fmt(n) -> str:
    return f"{int(n):,}".replace(",", " ")


def _pct(d) -> str:
    return f"{d.normalize():f}"


def _bar(progress: int, width: int = 10) -> str:
    filled = max(0, min(width, round(progress * width / 100)))
    return "▰" * filled + "▱" * (width - filled)


def _site_url(path: str) -> str | None:
    base = (getattr(settings, "FRONTEND_URL", "") or "").rstrip("/")
    return f"{base}{path}" if base.startswith("https://") else None


def referral_links(code: str) -> tuple[str | None, str | None]:
    bot = getattr(settings, "TELEGRAM_BOT_USERNAME", "") or ""
    bot_link = f"https://t.me/{bot}?start=ref_{code}" if bot else None
    site = _site_url(f"/?ref={code}")
    return bot_link, site


def show_wallet(user, chat_id: int, lang: str) -> None:
    from apps.loyalty.infrastructure import services
    from apps.telegram_bot.interfaces.callback_router import _send

    T = _t(lang)
    s = services.summary(user.id)
    cfg = services.programme()
    lines = [T["title"], "", T["balance"].format(balance=_fmt(s.balance))]
    if s.current_tier:
        lines.append(T["tier"].format(emoji=TIER_EMOJI.get(s.current_tier.icon, "⭐"), tier=s.current_tier.name, percent=_pct(s.current_tier.percent)))
    else:
        lines.append(T["no_tier"])
    if s.next_tier:
        lines += ["", T["progress"].format(bar=_bar(s.progress_percent), progress=s.progress_percent, next=s.next_tier.name, next_percent=_pct(s.next_tier.percent), amount=_fmt(s.amount_to_next or 0))]
    elif s.current_tier:
        lines += ["", T["top"]]
    coins, first = services.expiring_soon(user.id, within_days=30)
    if coins and first:
        lines += ["", T["expiring"].format(coins=_fmt(coins), date=timezone.localtime(first).strftime("%d.%m.%Y"))]
    if cfg.redeem_enabled:
        lines += ["", T["redeem"].format(percent=cfg.max_redeem_percent)]
    if cfg.tier_window_days:
        lines.append(T["window"].format(days=cfg.tier_window_days))

    keyboard = [[{"text": T["btn_ref"], "callback_data": "menu:loyalty_ref"}], [{"text": T["btn_hist"], "callback_data": "menu:loyalty_hist"}]]
    site = _site_url("/account/loyalty")
    if site:
        keyboard.append([{"text": T["btn_site"], "url": site}])
    keyboard.append([{"text": T["btn_back"], "callback_data": "menu:home"}])
    _send(chat_id, "\n".join(lines), keyboard)


def show_referral(user, chat_id: int, lang: str) -> None:
    from apps.loyalty.infrastructure import services
    from apps.loyalty.infrastructure.models import Referral, ReferralStatus, WalletTransaction
    from apps.telegram_bot.interfaces.callback_router import _send

    T = _t(lang)
    cfg = services.programme()
    back = [[{"text": T["btn_back"], "callback_data": "menu:loyalty"}]]
    if not cfg.referral_enabled:
        _send(chat_id, T["ref_disabled"], back)
        return
    code = services.referral_code_for(user.id)
    bot_link, site_link = referral_links(code)
    link = bot_link or site_link or code
    made = Referral.objects.filter(referrer_id=user.id)
    earned = sum(WalletTransaction.objects.filter(wallet__user_id=user.id, kind="referral", referral__referrer_id=user.id).values_list("amount", flat=True))
    text = "\n".join([
        T["ref_title"], "",
        T["ref_body"].format(referrer=_fmt(cfg.referrer_reward), referee=_fmt(cfg.referee_reward)), "",
        T["ref_code"].format(code=code),
        T["ref_link"].format(link=link), "",
        T["ref_stats"].format(invited=made.count(), rewarded=made.filter(status=ReferralStatus.REWARDED).count(), earned=_fmt(earned)),
    ])
    share = f"https://t.me/share/url?url={quote(link)}&text={quote(T['ref_share_text'].format(coins=_fmt(cfg.referee_reward)))}"
    _send(chat_id, text, [[{"text": T["btn_share"], "url": share}], *back])


def show_history(user, chat_id: int, lang: str) -> None:
    from apps.loyalty.infrastructure.models import WalletTransaction
    from apps.telegram_bot.interfaces.callback_router import _send

    T = _t(lang)
    rows = list(WalletTransaction.objects.filter(wallet__user_id=user.id).order_by("-created_at")[:8])
    if not rows:
        body = T["hist_empty"]
    else:
        body = "\n".join(
            f"{'🟢' if r.amount > 0 else '🔴'} <b>{'+' if r.amount > 0 else '−'}{_fmt(abs(r.amount))}</b> · {T['kind'].get(r.kind, r.kind)}"
            f"{f' #{r.order_number}' if r.order_number and r.kind in _OWN_ORDER_KINDS else ''} · {timezone.localtime(r.created_at).strftime('%d.%m.%Y')}"
            for r in rows
        )
    _send(chat_id, f"{T['hist_title']}\n\n{body}", [[{"text": T["btn_back"], "callback_data": "menu:loyalty"}]])


# ---------------------------------------------------------------- /start ref_<CODE>


def _pending_key(telegram_user_id: int) -> str:
    return cache_key(telegram_user_id, namespace="telegram_bot:pending_referral")


def park_referral(telegram_user_id: int, code: str) -> None:
    get_redis_client().set(_pending_key(telegram_user_id), code.strip().upper()[:16], ex=_PENDING_TTL)


def apply_referral(user, code: str, chat_id: int, lang: str) -> None:
    from apps.loyalty.infrastructure import services
    from apps.telegram_bot.interfaces.callback_router import _send

    T = _t(lang)
    try:
        services.claim_referral(user.id, code, channel="telegram")
    except services.LoyaltyError:
        _send(chat_id, T["ref_rejected"])
        return
    _send(chat_id, T["ref_applied"].format(coins=_fmt(services.programme().referee_reward)))


def apply_pending_referral(user, telegram_user_id: int, chat_id: int, lang: str) -> None:
    """Called right after onboarding creates the account."""
    client = get_redis_client()
    raw = client.get(_pending_key(telegram_user_id))
    if not raw:
        return
    client.delete(_pending_key(telegram_user_id))
    code = raw.decode() if isinstance(raw, bytes) else str(raw)
    try:
        apply_referral(user, code, chat_id, lang)
    except Exception:  # noqa: BLE001 - never break onboarding over a bonus
        logger.exception("Telegram bot: applying pending referral failed for telegram_user_id=%s", telegram_user_id)
