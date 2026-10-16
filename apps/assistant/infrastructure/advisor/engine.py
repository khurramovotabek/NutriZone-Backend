"""
The free NutriZone advisor: one customer turn without any paid AI service.

Same event contract as the Claude engine (status / text / products / chips / done), so the website widget and the
Telegram bot use either one unchanged. Flow: parse the message (nlu) → merge profile facts into the conversation's
memory (meta.profile) → answer by intent: a personal stack with daily needs (recommend), usage guidance, live shop
facts (stores, payment, coins, delivery...), or a catalogue search. Products shown are counted for learning (reco).
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from asgiref.sync import sync_to_async
from django.utils import timezone

from apps.assistant.infrastructure import tools
from apps.assistant.infrastructure.advisor import kb, needs, nlu, reco

logger = logging.getLogger("nutrizone.assistant.local")
LOCALES = ("uz", "ru", "en")
CHEAPER = ("arzon", "qimmat", "дешевле", "дорого", "бюджет", "cheaper", "too expensive", "budget")

CHIPS = {
    "start": {"uz": ["Massa olish uchun tavsiya", "Ozish uchun nima kerak?", "Kreatin qanday ichiladi?", "Do'konlar qayerda?"],
              "ru": ["Что для набора массы?", "Что нужно для похудения?", "Как принимать креатин?", "Где магазины?"],
              "en": ["What for muscle gain?", "What do I need for fat loss?", "How to take creatine?", "Where are your stores?"]},
    "after_reco": {"uz": ["Arzonroq variant", "Qanday ichiladi?", "Yetkazib berish", "To'lov usullari"],
                   "ru": ["Вариант дешевле", "Как принимать?", "Доставка", "Способы оплаты"],
                   "en": ["Cheaper option", "How to take them?", "Delivery", "Payment methods"]},
    "faq": {"uz": ["Menga mahsulot tanlab bering", "Original ekanini qanday bilaman?", "Coin nima?"],
            "ru": ["Подберите мне продукт", "Как убедиться в оригинальности?", "Что такое коины?"],
            "en": ["Pick a product for me", "How do I know it's original?", "What are coins?"]},
}


def money(v) -> str:
    try:
        return f"{int(v):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "—"


CUR = {"uz": "so'm", "ru": "сум", "en": "UZS"}


def _profile_line(p: dict, loc: str) -> str:
    unit = {"uz": ("sm", "kg", "yosh"), "ru": ("см", "кг", "лет"), "en": ("cm", "kg", "y.o.")}[loc]
    parts = []
    if p.get("height"):
        parts.append(f"{p['height']} {unit[0]}")
    if p.get("weight"):
        parts.append(f"{p['weight']:g} {unit[1]}")
    if p.get("age"):
        parts.append(f"{p['age']} {unit[2]}")
    if p.get("goal"):
        parts.append(kb.T["goal_name"][loc][p["goal"]])
    return " · ".join(parts)


def recommend_answer(profile: dict, loc: str) -> tuple[str, list[str], list[str]]:
    n = needs.compute(profile)
    picks = reco.stack(profile, loc, n)
    L = {
        "uz": ("**Profilingiz:**", "Kunlik ehtiyoj", "kaloriya", "oqsil", "suv", "kreatin", "Sizga mos to'plam", "Qanday ichish", "Jami", "byudjetingiz", "BMI"),
        "ru": ("**Ваш профиль:**", "Суточная потребность", "калории", "белок", "вода", "креатин", "Подходящий набор", "Как принимать", "Итого", "ваш бюджет", "ИМТ"),
        "en": ("**Your profile:**", "Daily needs", "calories", "protein", "water", "creatine", "Your stack", "How to take", "Total", "your budget", "BMI"),
    }[loc]
    band = {"uz": {"under": "kam vazn", "normal": "me'yorda", "over": "ortiqcha vazn", "obese": "semizlik"},
            "ru": {"under": "дефицит веса", "normal": "норма", "over": "избыточный вес", "obese": "ожирение"},
            "en": {"under": "underweight", "normal": "normal", "over": "overweight", "obese": "obese"}}[loc]
    lines = [f"{L[0]} {_profile_line(profile, loc)}"]
    if n:
        kcal = {"uz": "kkal", "ru": "ккал", "en": "kcal"}[loc]
        lines += ["", f"**{L[1]}:**", f"• {L[10]}: {n.bmi} ({band[n.bmi_band]})", f"• {L[2]}: ~{money(n.calories)} {kcal}",
                  f"• {L[3]}: {n.protein_low}–{n.protein_high} g", f"• {L[4]}: ~{n.water_l:g} l"]
        if n.creatine_g:
            lines.append(f"• {L[5]}: {n.creatine_g} g")
    ids: list[str] = []
    if picks:
        lines += ["", f"**{L[6]}:**"]
        total = 0
        for i, (kind, p) in enumerate(picks, 1):
            total += p.get("price_uzs") or 0
            lines.append(f"{i}. **{kb.T['kind_name'][loc][kind]}** — {p['name']} ({money(p.get('price_uzs'))} {CUR[loc]}): {kb.T['why'][loc][kind]}.")
            lines.append(f"   _{L[7]}:_ {kb.T['usage'][loc][kind]}")
            ids.append(p["id"])
        budget = profile.get("budget")
        lines.append(f"\n**{L[8]}:** {money(total)} {CUR[loc]}" + (f" ({L[9]}: {money(budget)} {CUR[loc]})" if budget else ""))
        if budget and total > budget:
            lines.append({"uz": "_Byudjetga to'liq mos variant hozir omborda yo'q — eng arzon mosini ko'rsatdim. Avval eng muhimidan (protein) boshlashni tavsiya qilaman._",
                          "ru": "_Полностью укладывающегося в бюджет варианта сейчас нет — показал самый доступный. Советую начать с главного (протеин)._",
                          "en": "_Nothing in stock fits the budget fully — I showed the most affordable match. Start with the essential one (protein)._"}[loc])
    lines += ["", kb.T["disclaimer"][loc]]
    return "\n".join(lines), ids, [k for k, _p in picks]


def answer(conv_meta: dict, text: str, loc: str) -> tuple[str, list[str], list[str], dict]:
    """(reply text, product ids to show, quick-reply chips, updated meta). Pure sync -- DB reads only."""
    meta = dict(conv_meta or {})
    profile = dict(meta.get("profile") or {})
    p = nlu.parse(text)
    profile.update(p.facts)
    if p.goal:
        profile["goal"] = p.goal
    t = p.text
    if meta.get("last") == "recommend" and any(s in t for s in CHEAPER):
        last_total = meta.get("last_total") or profile.get("budget") or 600_000
        profile["budget"] = int(last_total * 0.7)
        p.intent = "recommend"
    meta["profile"] = profile

    if p.intent == "greet":
        meta["last"] = "greet"
        return kb.T["greet"][loc], [], CHIPS["start"][loc], meta
    if p.intent == "thanks":
        return kb.T["thanks"][loc], [], CHIPS["faq"][loc], meta
    if p.intent == "operator":
        return kb.T["operator"][loc].format(contacts=kb.contacts(loc)), [], [], meta
    if p.intent in kb.FAQ:
        meta["last"] = p.intent
        return kb.FAQ[p.intent][loc], [], CHIPS["faq"][loc], meta
    if p.intent == "faq_stores":
        meta["last"] = p.intent
        return kb.stores_text(loc), [], CHIPS["faq"][loc], meta
    if p.intent == "faq_payment":
        return kb.payment_text(loc), [], CHIPS["faq"][loc], meta
    if p.intent == "faq_loyalty":
        return kb.loyalty_text(loc), [], CHIPS["faq"][loc], meta
    if p.intent == "usage" and p.concept:
        found = tools.search_products({"query": reco.QUERIES.get(p.concept, p.concept), "limit": 3, "in_stock_only": True}, loc)["products"]
        head = f"**{kb.T['kind_name'][loc][p.concept]}** — {kb.T['why'][loc][p.concept]}.\n\n{kb.T['usage'][loc][p.concept]}"
        tail = {"uz": "\n\nOmbordagi variantlar:", "ru": "\n\nВ наличии:", "en": "\n\nIn stock:"}[loc] if found else ""
        return head + tail + "\n\n" + kb.T["disclaimer"][loc], [x["id"] for x in found], CHIPS["after_reco"][loc], meta
    if p.intent == "usage" and meta.get("last_ids") and meta.get("last") == "recommend":
        kinds = meta.get("last_kinds") or []
        body = "\n".join(f"• **{kb.T['kind_name'][loc][k]}:** {kb.T['usage'][loc][k]}" for k in kinds)
        return body + "\n\n" + kb.T["disclaimer"][loc], [], CHIPS["after_reco"][loc], meta
    if p.intent == "recommend" or (p.goal and not p.concept):
        gaps = needs.missing(profile)
        if gaps:
            meta["last"] = "ask"
            fields = ", ".join(kb.T["fields"][loc][g] for g in gaps)
            known = _profile_line(profile, loc)
            prefix = ({"uz": "Tushundim: ", "ru": "Понял: ", "en": "Got it: "}[loc] + known + "\n\n") if known else ""
            return prefix + kb.T["ask"][loc].format(fields=fields), [], [], meta
        reply, ids, kinds = recommend_answer(profile, loc)
        meta.update(last="recommend", last_ids=ids, last_kinds=kinds, last_total=None)
        return reply, ids, CHIPS["after_reco"][loc], meta
    # plain product question → catalogue search (the smart search understands misspellings and all 3 languages)
    query = text.strip()[:120]
    found = tools.search_products({"query": query, "limit": 4, "in_stock_only": False}, loc)["products"]
    meta["last"] = "search"
    if not found:
        return kb.T["nothing"][loc].format(q=query[:60]), [], CHIPS["start"][loc], meta
    lines = [kb.T["found"][loc]]
    for x in found:
        price = f"{money(x.get('price_uzs'))} {CUR[loc]}" if x.get("price_uzs") else ""
        old = f" ~~{money(x['old_price_uzs'])}~~" if x.get("old_price_uzs") else ""
        stock = "" if x.get("in_stock") else {"uz": " — hozir yo'q", "ru": " — нет в наличии", "en": " — out of stock"}[loc]
        lines.append(f"• **{x['name']}** — {price}{old}{stock}")
    return "\n".join(lines), [x["id"] for x in found], CHIPS["after_reco"][loc], meta


GOAL_FROM_ACCOUNT = {"muscle_gain": "muscle", "fat_loss": "weight_loss", "healthy_lifestyle": "health"}
GOAL_TO_ACCOUNT = {v: k for k, v in GOAL_FROM_ACCOUNT.items()}


def account_facts(customer_id) -> dict:
    """What a signed-in customer already told us in their profile (height, weight, age, goal) -- never asked again."""
    from apps.identity.infrastructure.models import User

    user = User.objects.filter(pk=customer_id).only("height_cm", "weight_kg", "goal", "birthday").first() if customer_id else None
    if user is None:
        return {}
    facts: dict = {}
    if user.height_cm:
        facts["height"] = int(round(user.height_cm))
    if user.weight_kg:
        facts["weight"] = float(user.weight_kg)
    if user.birthday:
        today = timezone.localdate()
        age = today.year - user.birthday.year - ((today.month, today.day) < (user.birthday.month, user.birthday.day))
        if 10 <= age <= 100:
            facts["age"] = age
    if user.goal in GOAL_FROM_ACCOUNT:
        facts["goal"] = GOAL_FROM_ACCOUNT[user.goal]
    return facts


def save_account_facts(customer_id, profile: dict) -> None:
    """Facts told in the chat fill the customer's empty profile fields (what they set themselves is never overwritten)."""
    from apps.identity.infrastructure.models import User

    user = User.objects.filter(pk=customer_id).only("height_cm", "weight_kg", "goal").first() if customer_id else None
    if user is None:
        return
    changes = {}
    if not user.height_cm and profile.get("height") and 30 <= float(profile["height"]) <= 300:
        changes["height_cm"] = float(profile["height"])
    if not user.weight_kg and profile.get("weight") and 10 <= float(profile["weight"]) <= 500:
        changes["weight_kg"] = float(profile["weight"])
    if not user.goal and profile.get("goal") in GOAL_TO_ACCOUNT:
        changes["goal"] = GOAL_TO_ACCOUNT[profile["goal"]]
    if changes:
        User.objects.filter(pk=user.pk).update(**changes)


def _turn_sync(conversation_id, user_text: str) -> dict:
    from django.db import transaction
    from django.db.models import F

    from apps.assistant.infrastructure.models import AssistantConversation

    conv = AssistantConversation.objects.get(pk=conversation_id)
    loc = conv.locale if conv.locale in LOCALES else "uz"
    start = dict(conv.meta or {})
    if conv.customer_id:
        start["profile"] = {**account_facts(conv.customer_id), **(start.get("profile") or {})}
    reply, ids, chips, meta = answer(start, user_text, loc)
    if conv.customer_id:
        save_account_facts(conv.customer_id, meta.get("profile") or {})
    cards = tools.cards([tools._uuid(i) for i in ids], loc) if ids else []
    if cards:
        reco.record_shown([c["id"] for c in cards])
        if meta.get("last") == "recommend":
            meta["last_total"] = sum(int(float(c["price"])) for c in cards if c.get("price"))
    now = timezone.now().isoformat()
    with transaction.atomic():
        row = AssistantConversation.objects.select_for_update().get(pk=conversation_id)
        row.transcript = list(row.transcript) + [
            {"role": "user", "text": user_text, "at": now},
            {"role": "assistant", "text": reply, "products": cards, "at": now, "feedback": None},
        ]
        row.meta = meta
        row.engine = "local"
        row.turns = F("turns") + 1
        row.products_shown = F("products_shown") + len(cards)
        row.last_message = user_text[:300]
        row.save()
        row.refresh_from_db(fields=["turns"])
    return {"reply": reply, "cards": cards, "chips": chips, "turns": row.turns}


async def run_turn(conversation_id, user_text: str) -> AsyncIterator[dict]:
    yield {"type": "status", "stage": "searching"}
    result = await sync_to_async(_turn_sync)(conversation_id, user_text)
    yield {"type": "text", "delta": result["reply"]}
    if result["cards"]:
        yield {"type": "products", "items": result["cards"]}
    if result["chips"]:
        yield {"type": "chips", "items": result["chips"]}
    yield {"type": "done", "conversation_id": str(conversation_id), "turns": result["turns"], "saved": True}
