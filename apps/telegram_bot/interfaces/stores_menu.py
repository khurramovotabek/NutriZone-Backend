"""
"📍 Do'konlar" in the customer bot: every open branch with today's hours, phone and a map pin, and "nearest store"
from a shared location (a location sent outside checkout lands here instead of being ignored).

    menu:stores / /filiallar  → the list
    st:map:<store id>         → sendVenue (opens in the customer's map app) + call / website buttons
    st:near                   → asks for the location (one-time reply keyboard)
"""
from __future__ import annotations

import html
import logging
import math

from django.conf import settings

from apps.telegram_bot.interfaces.i18n import t

logger = logging.getLogger("nutrizone.telegram_bot")


def _stores():
    from apps.stores.infrastructure.models import Store

    return list(Store.objects.filter(kind="store", status="active").order_by("name"))


def _send(chat_id, text: str, keyboard: list | None = None) -> None:
    from apps.telegram_bot.interfaces.callback_router import _send as send

    send(chat_id, text, keyboard)


def _gateway():
    from apps.notifications.infrastructure import composition

    return composition.build_telegram_gateway()


def _hours_line(store, lang: str) -> str:
    try:
        today = store.today_hours()
        open_now = store.is_open_now()
    except Exception:  # noqa: BLE001 - malformed hours must not hide the store
        return ""
    if today.get("closed") or not today.get("open"):
        return t("st_closed_today", lang)
    state = t("st_open_now", lang) if open_now else t("st_closed_now", lang)
    return f"{state} · {today['open']}–{today['close']}"


def _store_url(store) -> str | None:
    base = (getattr(settings, "FRONTEND_URL", None) or "").rstrip("/")
    return f"{base}/store/{store.slug}" if base.startswith("https://") and store.slug else None


def _card(store, lang: str, distance_km: float | None = None) -> str:
    lines = [f"🏪 <b>{html.escape(store.name)}</b>" + (f" · {distance_km:.1f} km" if distance_km is not None else "")]
    place = ", ".join(p for p in (store.address, store.city) if p)
    if place:
        lines.append(f"📍 {html.escape(place)}")
    hours = _hours_line(store, lang)
    if hours:
        lines.append(f"🕒 {hours}")
    phones = [p for p in (store.phone_numbers or []) if p]
    if phones:
        lines.append("📞 " + ", ".join(html.escape(p) for p in phones[:2]))
    return "\n".join(lines)


def show(chat_id, lang: str) -> None:
    stores = _stores()
    if not stores:
        _send(chat_id, t("st_none", lang), [[{"text": t("home_button", lang), "callback_data": "menu:home"}]])
        return
    text = t("st_title", lang) + "\n\n" + "\n\n".join(_card(s, lang) for s in stores)
    keyboard = [[{"text": f"🗺 {s.name[:40]}", "callback_data": f"st:map:{s.id}"}] for s in stores if s.latitude is not None and s.longitude is not None]
    keyboard.append([{"text": t("st_near_button", lang), "callback_data": "st:near"}])
    keyboard.append([{"text": t("home_button", lang), "callback_data": "menu:home"}])
    _send(chat_id, text, keyboard)


def send_map(chat_id, store_id: str, lang: str) -> None:
    from apps.stores.infrastructure.models import Store

    store = Store.objects.filter(pk=store_id, kind="store", status="active").first() if store_id else None
    if store is None or store.latitude is None or store.longitude is None:
        _send(chat_id, t("st_none", lang), [[{"text": t("home_button", lang), "callback_data": "menu:home"}]])
        return
    buttons = []
    url = _store_url(store)
    if url:
        buttons.append([{"text": t("st_open_page", lang), "url": url}])
    buttons.append([{"text": t("back_button", lang), "callback_data": "menu:stores"}, {"text": t("home_button", lang), "callback_data": "menu:home"}])
    address = ", ".join(p for p in (store.address, store.city) if p) or store.name
    try:
        _gateway().send_venue(str(chat_id), store.latitude, store.longitude, store.name, address, inline_keyboard=buttons)
    except Exception:  # noqa: BLE001 - fall back to a text card
        logger.warning("stores menu: sendVenue failed for chat %s", chat_id)
        _send(chat_id, _card(store, lang), buttons)


def ask_location(chat_id, lang: str) -> None:
    try:
        _gateway().send_location_request(str(chat_id), t("st_ask_location", lang), t("share_location_button", lang))
    except Exception:  # noqa: BLE001
        logger.warning("stores menu: location request failed for chat %s", chat_id)


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest(chat_id, latitude: float, longitude: float, lang: str, limit: int = 3) -> None:
    ranked = sorted(((distance_km(latitude, longitude, s.latitude, s.longitude), s) for s in _stores() if s.latitude is not None and s.longitude is not None),
                    key=lambda x: x[0])[:limit]
    if not ranked:
        _send(chat_id, t("st_none", lang), [[{"text": t("home_button", lang), "callback_data": "menu:home"}]])
        return
    text = t("st_nearest_title", lang) + "\n\n" + "\n\n".join(_card(s, lang, d) for d, s in ranked)
    keyboard = [[{"text": f"🗺 {s.name[:40]}", "callback_data": f"st:map:{s.id}"}] for _, s in ranked]
    keyboard.append([{"text": t("home_button", lang), "callback_data": "menu:home"}])
    _send(chat_id, text, keyboard)


def handle_callback(chat_id, action: str, arg: str | None, lang: str) -> None:
    if action == "map":
        send_map(chat_id, arg, lang)
    elif action == "near":
        ask_location(chat_id, lang)
    else:
        show(chat_id, lang)
