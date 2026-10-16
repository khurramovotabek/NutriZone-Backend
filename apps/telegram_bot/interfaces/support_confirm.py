"""
A customer whose account staff created from a phone call (apps.support) registers in the bot: show what the operator
wrote down and let them confirm it, take the name they typed in onboarding, or type a new one.
"""
from __future__ import annotations

import html

from core.caching.redis_client import cache_key, get_redis_client

_TTL = 1800
TEXT = {
    "ask": {
        "uz": "📞 Siz bilan avval NutriZone operatori gaplashgan va ma'lumotlaringizni yozib olgan:\n\n👤 Ism: <b>{name}</b>\n📱 Telefon: <b>{phone}</b>\n\nMa'lumotlar to'g'rimi?",
        "ru": "📞 С вами ранее говорил оператор NutriZone и записал ваши данные:\n\n👤 Имя: <b>{name}</b>\n📱 Телефон: <b>{phone}</b>\n\nВсё верно?",
        "en": "📞 A NutriZone operator spoke with you earlier and noted your details:\n\n👤 Name: <b>{name}</b>\n📱 Phone: <b>{phone}</b>\n\nIs this correct?",
    },
    "ok": {"uz": "✅ Rahmat! Ma'lumotlaringiz tasdiqlandi.", "ru": "✅ Спасибо! Данные подтверждены.", "en": "✅ Thanks! Your details are confirmed."},
    "yes": {"uz": "✅ Ha, to'g'ri", "ru": "✅ Да, верно", "en": "✅ Yes, correct"},
    "use": {"uz": "✏️ «{name}» deb yozing", "ru": "✏️ Записать «{name}»", "en": "✏️ Use «{name}»"},
    "rename": {"uz": "📝 Boshqa ism yozaman", "ru": "📝 Напишу другое имя", "en": "📝 I'll type another name"},
    "prompt": {"uz": "Ismingizni yozing (masalan: Aziz Karimov):", "ru": "Напишите ваше имя (например: Азиз Каримов):", "en": "Type your name (e.g. Aziz Karimov):"},
    "unknown": {"uz": "Noma'lum", "ru": "Не указано", "en": "Unknown"},
}


def _key(chat_id, kind: str) -> str:
    return cache_key(chat_id, namespace=f"telegram_bot:support_{kind}")


def ask(chat_id: int, user, lang: str, suggested_name: str | None = None) -> bool:
    """Sends the confirmation when this user has an unconfirmed staff-made profile. True when it was sent."""
    from apps.support.infrastructure.services import pending_confirmation
    from apps.telegram_bot.interfaces.callback_router import _send

    if user is None or pending_confirmation(user) is None:
        return False
    lang = lang if lang in ("uz", "ru", "en") else "uz"
    rows = [[{"text": TEXT["yes"][lang], "callback_data": "sup:ok"}]]
    current = (user.full_name or "").strip()
    if suggested_name and suggested_name.strip() and suggested_name.strip() != current:
        get_redis_client().set(_key(chat_id, "suggest"), suggested_name.strip()[:120], ex=_TTL)
        rows.append([{"text": TEXT["use"][lang].format(name=suggested_name.strip()[:30]), "callback_data": "sup:use"}])
    rows.append([{"text": TEXT["rename"][lang], "callback_data": "sup:rename"}])
    _send(chat_id, TEXT["ask"][lang].format(name=html.escape(current or TEXT["unknown"][lang], quote=False), phone=html.escape(user.phone_number, quote=False)), rows)
    return True


def handle(user, chat_id: int, action: str, lang: str) -> None:
    from apps.support.infrastructure.services import confirm_profile
    from apps.telegram_bot.interfaces.callback_router import _send

    client = get_redis_client()
    if action == "ok":
        confirm_profile(user)
        _send(chat_id, TEXT["ok"][lang])
    elif action == "use":
        confirm_profile(user, client.get(_key(chat_id, "suggest")) or None)
        _send(chat_id, TEXT["ok"][lang])
    elif action == "rename":
        client.set(_key(chat_id, "rename"), "1", ex=_TTL)
        _send(chat_id, TEXT["prompt"][lang])


def take_typed_name(user, chat_id: int, text: str, lang: str) -> bool:
    """The next text after «I'll type another name» is the name. True when consumed."""
    from apps.support.infrastructure.services import confirm_profile
    from apps.telegram_bot.interfaces.callback_router import _send

    client = get_redis_client()
    if not client.get(_key(chat_id, "rename")):
        return False
    client.delete(_key(chat_id, "rename"))
    name = " ".join(text.split())[:120]
    if len(name) < 2:
        return False
    confirm_profile(user, name)
    _send(chat_id, TEXT["ok"][lang])
    return True
