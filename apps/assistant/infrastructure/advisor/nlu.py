"""
Understanding a shopper's message without an LLM: intent + profile facts, in Uzbek (Latin / Cyrillic), Russian and English.

`parse(text)` returns the intent ("recommend", "faq_delivery", "usage", "search", ...) and whatever profile facts the
message contains ("180 sm, 82 kg, 25 yosh, massa olmoqchiman" → height 180, weight 82, age 25, goal muscle).
Deliberately rule-based: predictable, instant, free, never invents facts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

APOS = str.maketrans({"ʻ": "'", "‘": "'", "’": "'", "`": "'", "ʼ": "'"})

# intent -> trigger stems (matched as word prefixes on the normalized text)
INTENTS: dict[str, tuple[str, ...]] = {
    "greet": ("salom", "assalom", "hello", "hi", "hey", "привет", "здравств", "добрый", "салом", "ассалом"),
    "thanks": ("rahmat", "raxmat", "tashakkur", "спасибо", "благодар", "thank", "thx", "рахмат"),
    "operator": ("operator", "odam bilan", "jonli", "менеджер", "оператор", "человек", "human", "agent", "support"),
    "faq_delivery": ("yetkaz", "dostav", "kuryer", "kurer", "достав", "курьер", "delivery", "deliver", "shipping", "етказ"),
    "faq_payment": ("to'lov", "tolov", "payme", "click", "uzum", "karta", "naqd", "оплат", "карт", "налич", "payment", "pay ", "card", "cash", "тўлов"),
    "faq_stores": ("do'kon", "dokon", "filial", "manzil", "qayerda", "joylash", "адрес", "магазин", "филиал", "где наход", "store", "shop location", "address", "where are you", "дўкон"),
    "faq_loyalty": ("coin", "bonus", "keshbek", "cashback", "кешбэк", "бонус", "баллы", "loyalty", "points", "коин"),
    "faq_original": ("original", "sertifikat", "qalbaki", "soxta", "оригинал", "подделк", "сертификат", "fake", "genuine", "authentic", "certificate"),
    "faq_returns": ("qaytar", "almashtir", "vozvrat", "возврат", "обмен", "return", "refund", "exchange"),
    "faq_order": ("buyurtmam", "zakazim", "заказ", "где мой", "my order", "order status", "track"),
    "usage": ("qanday ich", "qanday qabul", "qachon ich", "doza", "dozirovka", "как приним", "как пить", "когда пить", "дозиров", "how to take", "how to use", "when to take", "dosage", "how much should"),
    "recommend": ("tavsiya", "maslahat", "tanlab", "nima ich", "qaysi", "taklif", "kerak bo'l", "nima olay", "посовет", "что выбрать", "какой", "какую", "рекоменд", "подбер", "recommend", "suggest", "which", "what should", "advise", "best for", "maqsad"),
    "profile": ("bo'y", "vazn", "yosh", "рост", "вес", "лет", "height", "weight", "years old"),
}

GOALS: dict[str, tuple[str, ...]] = {
    "muscle": ("massa", "mushak", "muskul", "kuch", "bulk", "muscle", "mass", "gain", "набор", "масс", "мышц", "сила", "рельеф мышц", "kattalash"),
    "weight_loss": ("ozish", "ozmoq", "ozay", "ozdir", "ozg'in", "vazn tashla", "vazn yo'qot", "yog' yoq", "quriti", "sushka", "похуд", "сброс", "сушк", "жиросжиг", "lose weight", "weight loss", "fat loss", "cut", "slim", "lean"),
    "endurance": ("chidam", "energiya", "yugur", "marafon", "velosiped", "futbol", "boks", "выносл", "энерги", "бег", "марафон", "endurance", "stamina", "running", "cardio", "energy"),
    "health": ("salomat", "sog'l", "immunitet", "vitamin", "здоров", "иммун", "витамин", "health", "immunity", "wellness"),
}

CONCEPT_WORDS: dict[str, tuple[str, ...]] = {
    "protein": ("protein", "proteyn", "whey", "izolyat", "isolate", "kazein", "casein", "oqsil", "протеин", "белок", "изолят", "казеин"),
    "creatine": ("kreatin", "creatine", "креатин"),
    "gainer": ("gainer", "geyner", "гейнер"),
    "bcaa": ("bcaa", "eaa", "amino", "аминокисл", "глютамин", "glutamin"),
    "preworkout": ("preworkout", "pre-workout", "predtren", "предтрен"),
    "carnitine": ("karnitin", "carnitine", "карнитин", "fat burner", "жиросжиг"),
    "omega": ("omega", "baliq yog'", "fish oil", "омега"),
    "vitamin": ("vitamin", "multivitamin", "витамин", "мультивитамин"),
    "collagen": ("kollagen", "collagen", "коллаген", "bo'g'im", "сустав", "joint"),
}

LATIN_FROM_CYR = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l",
    "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ц": "ts", "ч": "ch", "ш": "sh",
    "ъ": "'", "ь": "", "э": "e", "ю": "yu", "я": "ya", "ў": "o'", "қ": "q", "ғ": "g'", "ҳ": "h",
})


@dataclass
class Parsed:
    intent: str = "search"
    facts: dict = field(default_factory=dict)
    goal: str | None = None
    concept: str | None = None
    text: str = ""


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().translate(APOS)).strip()


def _has(text: str, stems) -> bool:
    return any(re.search(r"(?:^|[\s,.!?;:(\"'-])" + re.escape(s), text) for s in stems)


def _num(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


def extract_facts(t: str) -> dict:
    """Height (cm), weight (kg), age, sex, activity, budget (so'm), lactose / vegan flags from free text."""
    facts: dict = {}
    h = _num(r"(1[4-9]\d|2[0-2]\d)\s*(?:sm|cm|см|санти)", t) or _num(r"(?:bo'y\w*|boy\w*|рост\w*|height)\D{0,12}(1[4-9]\d|2[0-2]\d)", t)
    if h is None:
        mh = re.search(r"\b(1)[.,]([5-9]\d)\s*(?:m|м)\b", t)
        h = float(mh.group(1) + mh.group(2)) if mh else None
    w = _num(r"(\d{2,3}(?:[.,]\d)?)\s*(?:kg|кг|kilo|кило)", t) or _num(r"(?:vazn\w*|og'irlig\w*|вес\w*|weight)\D{0,12}(\d{2,3}(?:[.,]\d)?)", t)
    a = _num(r"(\d{2})\s*(?:yosh|ёш|лет|год|years?|y\.?o)", t) or _num(r"(?:yosh\w*|возраст\w*|age)\D{0,10}(\d{2})", t)
    if h and 140 <= h <= 229:
        facts["height"] = int(h)
    if w and 30 <= w <= 250:
        facts["weight"] = round(w, 1)
    if a and 12 <= a <= 90:
        facts["age"] = int(a)
    if _has(t, ("ayol", "qiz", "женщин", "девушк", "female", "woman", "girl", "аёл")):
        facts["sex"] = "f"
    elif _has(t, ("erkak", "yigit", "мужчин", "парень", "male", "man ", "guy", "эркак")):
        facts["sex"] = "m"
    per_week = _num(r"(?:haftada|в неделю|раз в неделю|a week|per week|times)\D{0,6}(\d)", t) or _num(r"(\d)\s*(?:marta|kun|раз|times|days)\D{0,10}(?:haftada|в неделю|week)", t)
    if per_week is not None:
        facts["activity"] = "low" if per_week <= 2 else "medium" if per_week <= 4 else "high"
    elif _has(t, ("har kuni", "каждый день", "every day", "daily", "professional", "профессион")):
        facts["activity"] = "high"
    elif _has(t, ("yangi boshla", "endi boshla", "новичок", "начина", "beginner", "just started")):
        facts["activity"] = "low"
    b = re.search(r"(\d[\d\s.,]*)\s*(mln|million|миллион|млн|ming|тыс|k\b|so'm|сум|sum\b|uzs)", t)
    if b:
        try:
            amount = float(b.group(1).replace(" ", "").replace(",", "."))
            unit = b.group(2)
            amount *= 1_000_000 if unit in ("mln", "million", "миллион", "млн") else 1000 if unit in ("ming", "тыс", "k") else 1
            if 50_000 <= amount <= 20_000_000:
                facts["budget"] = int(amount)
        except ValueError:
            pass
    if _has(t, ("laktoza", "лактоз", "lactose", "sut ichol", "molochn")):
        facts["lactose_free"] = True
    if _has(t, ("vegan", "vegetar", "вегетар", "веган", "o'simlik", "plant")):
        facts["vegan"] = True
    return facts


def parse(text: str) -> Parsed:
    t = normalize(text)
    latin = t.translate(LATIN_FROM_CYR)  # Uzbek typed in Cyrillic still matches the Latin stems
    both = f"{t} {latin}"
    p = Parsed(text=t, facts=extract_facts(t))
    p.goal = next((g for g, stems in GOALS.items() if _has(both, stems)), None)
    p.concept = next((c for c, stems in CONCEPT_WORDS.items() if _has(both, stems)), None)
    for intent in ("operator", "faq_order", "faq_returns", "faq_original", "faq_loyalty", "faq_payment", "faq_delivery", "faq_stores", "usage", "recommend"):
        if _has(both, INTENTS[intent]):
            p.intent = intent
            break
    else:
        if p.facts or p.goal:
            p.intent = "recommend"
        elif _has(both, INTENTS["greet"]) and len(t) < 40:
            p.intent = "greet"
        elif _has(both, INTENTS["thanks"]) and len(t) < 40:
            p.intent = "thanks"
    if p.intent == "usage" and not p.concept:
        p.intent = "recommend" if p.goal else "usage"
    return p
