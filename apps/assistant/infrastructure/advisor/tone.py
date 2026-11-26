"""
How the shopper sounds, not just what they ask: an upset or urgent message ("pulimni qaytaring!!!", "ВЫ МЕНЯ ОБМАНУЛИ",
"hali ham kelmadi") gets an apology and a way to a person BEFORE the factual answer -- the free advisor never answers
an angry customer with a dry policy line. Plain keyword + punctuation signals, no model needed.
"""
from __future__ import annotations

import re

from apps.assistant.infrastructure.advisor import nlu

UPSET = ("ishlamadi", "ishlamayapti", "ishlamaydi", "foyda bermadi", "foydasi yo'q", "pulimni qaytar", "pulni qaytar", "aldad", "aldov", "aldash",
         "jahlim", "jahl", "norozi", "shikoyat", "hali ham kelmadi", "hali kelmadi", "kelmadi", "kech qoldi", "kechikdi",
         "soxta", "qalbaki", "uyat", "dahshat", "bema'ni", "javob bermayapsiz", "javob yo'q",
         "верните деньги", "верните", "обман", "обманули", "мошен", "ужас", "кошмар", "безобраз", "не пришел", "не пришёл", "до сих пор",
         "не работает", "не помог", "подделк", "фальшив", "жалоб", "недоволен", "никто не отвечает",
         "refund", "money back", "scam", "fake", "terrible", "awful", "worst", "still not", "never arrived", "didn't arrive", "angry", "disappointed")
# how a product *is* -- upset only when it came that way ("singan keldi"), not when asking about it
# ("muddati o'tgan protein ichsa bo'ladimi")
STATE = ("buzilgan", "singan", "yaroqsiz", "muddati o'tgan", "muddati otgan", "просрочен", "сломан", "испорчен", "broken", "expired", "damaged")
CAME = ("keldi", "kelgan", "sotdingiz", "sotishdi", "berdingiz", "yubordingiz", "yuborishdi", "olib keldi", "пришел", "пришёл", "прислали", "привезли",
        "продали", "получил", "arrived", "came", "sent me", "sold me", "delivered", "received")
URGENT = ("tezroq", "zudlik bilan", "srochno", "срочно", "быстрее", "urgent", "asap", "right now")

LEAD = {
    "uz": "Noqulaylik uchun chin dildan uzr so'raymiz 🙏 Vaziyatingizni tushunaman — buni albatta hal qilamiz.",
    "ru": "Искренне извиняемся за неудобство 🙏 Понимаю, как это неприятно — мы обязательно всё решим.",
    "en": "We're truly sorry about this 🙏 I understand how frustrating it is — we'll make it right.",
}
LEAD_URGENT = {
    "uz": "Tushundim, bu shoshilinch ⏱ Darhol yordam beraman.",
    "ru": "Понял, это срочно ⏱ Помогаю сразу.",
    "en": "Got it, this is urgent ⏱ Helping right away.",
}
TAIL = {
    "uz": "👤 Tezroq hal qilish uchun **operator** bilan bog'laning — buyurtma raqamini yozsangiz, xodimimiz darhol ko'rib chiqadi.",
    "ru": "👤 Чтобы решить быстрее, свяжитесь с **оператором** — напишите номер заказа, и сотрудник сразу разберётся.",
    "en": "👤 For the fastest fix, reach an **operator** — send your order number and a team member will look right away.",
}
OPERATOR_CHIP = {"uz": "Operator bilan bog'lanish", "ru": "Связаться с оператором", "en": "Talk to a person"}


def mood(text: str) -> str | None:
    """"upset", "urgent" or None."""
    raw = text or ""
    t = nlu.normalize(raw)
    both = f"{t} {t.translate(nlu.LATIN_FROM_CYR)}"
    letters = [c for c in raw if c.isalpha()]
    shouting = len(letters) >= 12 and sum(c.isupper() for c in letters) / len(letters) > 0.7
    came_bad = any(s in both for s in STATE) and any(s in both for s in CAME)
    if any(s in both for s in UPSET) or came_bad or shouting or re.search(r"[!?]{3,}", raw) and len(t.split()) >= 3:
        return "upset"
    if any(s in both for s in URGENT):
        return "urgent"
    return None


def soften(reply: str, chips: list[str], text: str, loc: str) -> tuple[str, list[str]]:
    """Wraps the factual reply: empathy first, the way to a person last (once -- a reply that already apologises is left alone)."""
    m = mood(text)
    loc = loc if loc in LEAD else "uz"
    if not m or any(w in (reply or "")[:160].lower() for w in ("uzr", "извин", "sorry", "kechirasiz")):
        return reply, chips
    if m == "urgent":
        return f"{LEAD_URGENT[loc]}\n\n{reply}", chips
    chips = [OPERATOR_CHIP[loc]] + [c for c in (chips or []) if c != OPERATOR_CHIP[loc]][:3]
    return f"{LEAD[loc]}\n\n{reply}\n\n{TAIL[loc]}", chips
