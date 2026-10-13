"""
Bot: "📰 Yangiliklar va aksiyalar" -- subscribe to news & promotions (apps.notifications.subscriptions).

Reached from the main menu or the site's deep link t.me/<bot>?start=news. A visitor who isn't registered yet is
"parked" and subscribed right after onboarding creates the account. Subscribers get broadcasts aimed at them and a
one-time coin gift on their first purchase after subscribing.
"""
from __future__ import annotations

import logging

from apps.notifications.infrastructure import subscriptions
from core.caching.redis_client import cache_key, get_redis_client

logger = logging.getLogger("nutrizone.app")
_PENDING_TTL = 7 * 24 * 3600

_T = {
    "uz": {
        "title": "\U0001F4F0 <b>Yangiliklar va aksiyalar</b>",
        "on": "✅ Siz obunachisiz. Aksiyalar, yangi mahsulotlar va foydali maqolalar haqida birinchilardan bo'lib xabar olasiz.",
        "off": "Obuna bo'ling — aksiyalar, chegirmalar, yangi mahsulotlar va foydali maqolalar haqida birinchilardan bo'lib biling.",
        "gift": "\U0001F381 Sovg'a: obunadan keyingi birinchi xaridingiz uchun <b>{coins} coin</b> (1 coin = 1 so'm).",
        "gift_done": "\U0001F381 Obuna sovg'asi olingan: +{coins} coin.",
        "btn_on": "\U0001F514 Obuna bo'lish", "btn_off": "\U0001F515 Obunani bekor qilish", "btn_home": "\U0001F3E0 Bosh menyu",
        "subscribed": "\U0001F389 <b>Obuna bo'ldingiz!</b> Endi eng so'nggi aksiyalar sizda birinchi bo'ladi.",
        "unsubscribed": "Obuna bekor qilindi. Istalgan vaqtda qayta obuna bo'lishingiz mumkin.",
    },
    "ru": {
        "title": "\U0001F4F0 <b>Новости и акции</b>",
        "on": "✅ Вы подписаны. Вы первыми узнаёте об акциях, новинках и полезных статьях.",
        "off": "Подпишитесь — узнавайте первыми об акциях, скидках, новинках и полезных статьях.",
        "gift": "\U0001F381 Подарок: <b>{coins} коинов</b> за первую покупку после подписки (1 коин = 1 сум).",
        "gift_done": "\U0001F381 Подарок за подписку получен: +{coins} коинов.",
        "btn_on": "\U0001F514 Подписаться", "btn_off": "\U0001F515 Отписаться", "btn_home": "\U0001F3E0 Главное меню",
        "subscribed": "\U0001F389 <b>Вы подписались!</b> Теперь свежие акции — первыми у вас.",
        "unsubscribed": "Подписка отменена. Вернуться можно в любой момент.",
    },
    "en": {
        "title": "\U0001F4F0 <b>News & promotions</b>",
        "on": "✅ You're subscribed. You'll be first to hear about promotions, new products and useful articles.",
        "off": "Subscribe — be the first to know about promotions, discounts, new products and useful articles.",
        "gift": "\U0001F381 Gift: <b>{coins} coins</b> on your first purchase after subscribing (1 coin = 1 UZS).",
        "gift_done": "\U0001F381 Subscription gift received: +{coins} coins.",
        "btn_on": "\U0001F514 Subscribe", "btn_off": "\U0001F515 Unsubscribe", "btn_home": "\U0001F3E0 Main menu",
        "subscribed": "\U0001F389 <b>You're subscribed!</b> The newest deals now reach you first.",
        "unsubscribed": "Unsubscribed. You can come back any time.",
    },
}


def _t(lang: str) -> dict:
    return _T.get(lang) or _T["uz"]


def _fmt(n: int) -> str:
    return f"{int(n):,}".replace(",", " ")


def show(user, chat_id: int, lang: str, lead: str | None = None) -> None:
    from apps.notifications.infrastructure.models import NewsSubscription
    from apps.telegram_bot.interfaces.callback_router import _send

    T = _t(lang)
    sub = NewsSubscription.objects.filter(user_id=user.id).first()
    on = bool(sub and sub.is_active)
    lines = [lead] if lead else []
    lines += [T["title"], "", T["on"] if on else T["off"]]
    coins = subscriptions.gift_coins()
    if sub and sub.gift_granted_at:
        lines.append(T["gift_done"].format(coins=_fmt(sub.gift_coins)))
    elif coins:
        lines.append(T["gift"].format(coins=_fmt(coins)))
    button = {"text": T["btn_off"], "callback_data": "news:off"} if on else {"text": T["btn_on"], "callback_data": "news:on"}
    _send(chat_id, "\n".join(lines), [[button], [{"text": T["btn_home"], "callback_data": "menu:home"}]])


def handle(user, chat_id: int, action: str, lang: str) -> None:
    T = _t(lang)
    if action == "on":
        _sub, fresh = subscriptions.subscribe(user.id, source="bot")
        show(user, chat_id, lang, lead=T["subscribed"] if fresh else None)
    elif action == "off":
        subscriptions.unsubscribe(user.id)
        show(user, chat_id, lang, lead=T["unsubscribed"])
    else:
        show(user, chat_id, lang)


# ---------------------------------------------------------------- /start news


def _key(telegram_user_id: int) -> str:
    return cache_key(telegram_user_id, namespace="telegram_bot:pending_news")


def park(telegram_user_id: int) -> None:
    get_redis_client().set(_key(telegram_user_id), "1", ex=_PENDING_TTL)


def subscribe_from_link(user, chat_id: int, lang: str) -> None:
    _sub, fresh = subscriptions.subscribe(user.id, source="site")
    show(user, chat_id, lang, lead=_t(lang)["subscribed"] if fresh else None)


def apply_pending(user, telegram_user_id: int, chat_id: int, lang: str) -> None:
    """Right after onboarding: a visitor who came from the site's "subscribe" link gets subscribed."""
    try:
        client = get_redis_client()
        if not client.get(_key(telegram_user_id)):
            return
        client.delete(_key(telegram_user_id))
        subscribe_from_link(user, chat_id, lang)
    except Exception:  # noqa: BLE001 - never break onboarding over a subscription
        logger.exception("Telegram bot: pending news subscription failed for telegram_user_id=%s", telegram_user_id)
