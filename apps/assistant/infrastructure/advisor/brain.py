"""
NutriZone Brain v2 -- the free advisor's understanding layer, run before the classic flow in engine.answer().

It recognises what the shop's own database knows -- brands, categories, branches (city / district / name), health
conditions -- and answers the questions shoppers actually ask with live data:

    price ("Olimp whey narxi?"), branch stock ("Applied kreatin Chilonzorda bormi?"), best sellers, comparisons
    ("kreatin va protein farqi"), promotions, contacts, opening hours, a category / brand list ("vitamin D bormi"),
    and safety-first answers when someone mentions a condition (heart, pregnancy, children, medication...).

Returns None when none of this applies, and the classic flow (profile → personal stack, usage, FAQ, search) answers.
Everything is read live and cached for a few minutes; nothing is invented.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from apps.assistant.infrastructure.advisor import nlu

LOCALES = ("uz", "ru", "en")
_CACHE: dict = {"at": 0.0}
TTL = 300

# --------------------------------------------------------------------------- vocabularies

PRICE = ("narx", "narhi", "qancha tur", "necha pul", "qanchaga", "qancha so'm", "nechpul", "цена", "сколько стоит", "стоимост", "почем", "price", "how much", "cost")
HAVE = ("bormi", "bor mi", "mavjudmi", "qoldimi", "sotasiz", "sotiladimi", "topsa bo'ladimi", "есть ли", "есть в", "в наличии", "имеется", "продаете", "do you have", "in stock", "available")
BEST = ("eng ko'p sotil", "ko'p sotil", "top", "xit", "mashhur", "eng yaxshi", "eng zo'r", "zo'r", "хит", "популяр", "самый продаваем", "лучш", "топ", "best seller", "bestseller", "best", "popular", "top rated")
COMPARE = ("farq", "farqi", "yoki", "qaysi biri", "solishtir", "taqqosla", "или", "разниц", "отлича", "сравн", "что лучше", "versus", " vs ", "difference", "compare", "or ", "better than")
PROMO = ("chegirma", "aksiya", "skidka", "arzonlash", "sale", "скидк", "акци", "распродаж", "discount", "promo", "deal")
CONTACT = ("telefon", "raqam", "nomer", "aloqa", "bog'lan", "qo'ng'iroq", "телефон", "номер", "контакт", "связ", "позвон", "phone", "contact", "call you", "number")
HOURS = ("ish vaqt", "soat nechagacha", "soat nechada", "nechagacha", "ochiqmi", "ochiq", "yopiq", "ishlaysiz", "dam olish", "время работ", "график", "до скольки", "во сколько", "открыт", "работает", "работаете", "hours", "open", "close", "working time")
CAN_I = ("bo'ladimi", "mumkinmi", "ichsam", "ichsa", "beraversa", "bersam", "bersa", "можно ли", "можно", "безопасно", "can i", "is it safe", "safe to", "should i")
HEALTH = {
    "heart": ("yurak", "bosim", "gipertoni", "aritmi", "сердц", "давлен", "гипертон", "аритм", "heart", "blood pressure", "hypertension"),
    "pregnant": ("homilador", "emiz", "beremen", "беремен", "кормлю грудью", "лактац", "pregnan", "breastfeed"),
    "child": ("bola", "bolam", "bolalar", "farzand", "o'smir", "ребен", "дет", "подрост", "child", "kid", "teen", "son ", "daughter"),
    "kidney": ("buyrak", "jigar", "почк", "печен", "kidney", "liver"),
    "diabetes": ("diabet", "qand", "диабет", "сахар", "diabetes", "blood sugar"),
    "meds": ("dori ich", "dori qabul", "antidepress", "лекарств", "таблетк", "medication", "pills", "medicine"),
    "allergy": ("allergi", "аллерги", "allergy", "allergic"),
}
FILLER = re.compile(
    r"\b(bormi|bor|mi|mavjudmi|narxi|narx|qancha|turadi|necha|pul|sizda|sizlarda|kerak|menga|bering|ko'rsating|haqida|degan|"
    r"есть|ли|у|вас|сколько|стоит|цена|почем|покажите|мне|нужен|нужна|"
    r"do|you|have|how|much|is|the|price|of|show|me|please|any)\b", re.I)


@dataclass
class Reply:
    text: str
    product_ids: list = field(default_factory=list)
    chips: list = field(default_factory=list)
    venues: list = field(default_factory=list)  # [{"title", "address", "lat", "lng"}] -- the bot sends real map pins
    last: str = "brain"


def _l(loc: str, uz: str, ru: str, en: str) -> str:
    return {"uz": uz, "ru": ru, "en": en}[loc]


def _money(v) -> str:
    try:
        return f"{int(float(v)):,}".replace(",", " ") + " so'm"
    except (TypeError, ValueError):
        return ""


def _has(text: str, stems) -> bool:
    return nlu._has(text, stems)


# --------------------------------------------------------------------------- live vocabulary from the database


def _index() -> dict:
    if time.time() - _CACHE["at"] < TTL and "brands" in _CACHE:
        return _CACHE
    from apps.products.infrastructure import models as orm
    from apps.stores.infrastructure.models import Store

    brands: dict = {}
    for bid, name in orm.BrandTranslation.objects.filter(brand__deleted_at__isnull=True).values_list("brand_id", "name"):
        key = nlu.normalize(name)
        if len(key) >= 3:
            brands[key] = bid
    cats: dict = {}
    for cid, name in orm.CategoryTranslation.objects.filter(category__deleted_at__isnull=True).values_list("category_id", "name"):
        key = nlu.normalize(name)
        if len(key) >= 4:
            cats[key] = cid
    stores = []
    for s in Store.objects.filter(kind="store", status="active"):
        keys = {nlu.normalize(x) for x in (s.city, s.district) if x and len(x) >= 4}
        keys |= {w for w in re.findall(r"[a-zа-я']{4,}", nlu.normalize(s.name)) if w not in ("lifesport", "nutrizone", "store", "shop", "filial", "магазин")}
        stores.append({"obj": s, "keys": keys})
    _CACHE.update(at=time.time(), brands=brands, cats=cats, stores=stores)
    return _CACHE


def _find_long(text: str, table: dict) -> list:
    """Keys of `table` that occur in the text (word-prefix match, longest first, no overlaps), as values."""
    found, used = [], []
    for key in sorted(table, key=len, reverse=True):
        stem = key if len(key) <= 6 else key[: max(6, len(key) - 2)]  # tolerate suffixes: "kreatinni", "vitaminlar"
        m = re.search(r"(?:^|[\s,.!?;:(\"'-])" + re.escape(stem), text)
        if m and not any(a <= m.start() < b for a, b in used):
            used.append((m.start(), m.start() + len(stem)))
            if table[key] not in found:
                found.append(table[key])
    return found


def _stores_in(text: str) -> list:
    t = nlu.normalize(text)
    latin = t.translate(nlu.LATIN_FROM_CYR)
    hits = []
    for s in _index()["stores"]:
        for k in s["keys"]:
            stem = k[: max(4, min(len(k), 6))]
            if re.search(r"(?:^|[\s,.!?;:(\"'-])" + re.escape(stem), f"{t} {latin}"):
                hits.append(s["obj"])
                break
    return hits


@dataclass
class Seen:
    text: str
    both: str
    brands: list
    cats: list
    concepts: list
    stores: list
    health: list


def understand(text: str) -> Seen:
    t = nlu.normalize(text)
    both = f"{t} {t.translate(nlu.LATIN_FROM_CYR)}"
    idx = _index()
    concepts = [c for c, stems in nlu.CONCEPT_WORDS.items() if _has(both, stems)]
    return Seen(text=t, both=both, brands=_find_long(both, idx["brands"]), cats=_find_long(both, idx["cats"]), concepts=concepts,
                stores=_stores_in(text), health=[h for h, stems in HEALTH.items() if _has(both, stems)])


# --------------------------------------------------------------------------- catalogue helpers


ALIASES = {r"\bon\b": "optimum nutrition", r"\bmp\b": "myprotein", r"\bmt\b": "muscletech", r"\bbsn\b": "bsn", r"\bgold standard\b": "gold standard goldstandart"}


def _variants(query: str) -> list[str]:
    """The query as typed, with known abbreviations spelled out, and with neighbouring words glued ("gold standard" →
    "goldstandard") -- tub names are often written as one word."""
    out = [query]
    expanded = query
    for pat, full in ALIASES.items():
        expanded = re.sub(pat, full, expanded)
    if expanded != query:
        out.append(expanded)
    words = expanded.split()
    if len(words) >= 2:
        out.append(" ".join(words[:-2] + [words[-2] + words[-1]]))
        out.append(" ".join(w for w in words if len(w) > 2))
    return [q for i, q in enumerate(out) if q and q not in out[:i]]


def _search(query: str = "", loc: str = "uz", limit: int = 4, category=None, brand=None, sort: str | None = None, on_sale=False, in_stock=True) -> list[dict]:
    if query:
        for q in _variants(query):
            found = _search_once(q, loc, limit, category, brand, sort, on_sale, in_stock)
            if found:
                return found
        return []
    return _search_once(query, loc, limit, category, brand, sort, on_sale, in_stock)


def _search_once(query: str, loc: str, limit: int, category, brand, sort, on_sale, in_stock) -> list[dict]:
    from apps.assistant.infrastructure import tools
    from apps.products.infrastructure.selectors import DjangoProductSearchBackend

    filters: dict = {}
    if category:
        filters["category_id"] = str(category)
    if brand:
        filters["brand_ids"] = [str(brand)]
    if on_sale:
        filters["on_sale"] = True
    if in_stock:
        filters["in_stock"] = True
    page = DjangoProductSearchBackend().search(query, filters, 1, limit, sort or ("relevance" if query else "-popularity"), loc)
    rows = page["results"]
    stock = tools._stock([tools._safe_uuid(r.get("default_variant_id")) for r in rows])
    return [{"id": str(r["id"]), "name": r.get("name"), "price": r.get("price"), "old": r.get("compare_at_price"), "discount": r.get("discount_percent"),
             "variant": r.get("default_variant_id"), "in_stock": stock.get(tools._safe_uuid(r.get("default_variant_id")), 0) > 0} for r in rows]


def _clean_query(text: str) -> str:
    q = FILLER.sub(" ", nlu.normalize(text))
    q = re.sub(r"[?!.,]", " ", q)
    return re.sub(r"\s+", " ", q).strip()[:100]


def _lines(items: list[dict], loc: str) -> str:
    out = []
    for i, p in enumerate(items, 1):
        price = _money(p["price"])
        old = f" ~~{_money(p['old'])}~~" if p.get("old") and p.get("price") and float(p["old"]) > float(p["price"]) else ""
        stock = "" if p["in_stock"] else _l(loc, " · tugagan", " · нет в наличии", " · out of stock")
        out.append(f"{i}. **{p['name']}** — {price}{old}{stock}")
    return "\n".join(out)


def _general_hours() -> str:
    from apps.platform.infrastructure.models import SiteSettings

    site = SiteSettings.objects.filter(pk=1).first()
    return (getattr(site, "working_hours", "") or "").strip() if site else ""


def venues_for(text: str, limit: int = 3) -> list[dict]:
    """Map pins of the branches a message names ("Andijon filiali qayerda?")."""
    return [v for s in _stores_in(text)[:limit] if (v := _venue(s)) is not None]


def _venue(s) -> dict | None:
    if s.latitude is None or s.longitude is None:
        return None
    return {"title": s.name, "address": ", ".join(x for x in (s.city, s.district, s.address) if x), "lat": float(s.latitude), "lng": float(s.longitude)}


def _hours_line(s, loc: str) -> str:
    h = s.today_hours()
    if h.get("unknown"):
        general = _general_hours()
        return (_l(loc, "odatda ", "обычно ", "usually ") + general) if general else _l(loc, "ish vaqtini telefon orqali aniqlang", "уточните часы по телефону", "please call for hours")
    if h.get("closed"):
        return _l(loc, "bugun yopiq", "сегодня закрыто", "closed today")
    state = _l(loc, "hozir ochiq", "сейчас открыто", "open now") if s.is_open_now() else _l(loc, "hozir yopiq", "сейчас закрыто", "closed now")
    return f"{_l(loc, 'bugun', 'сегодня', 'today')} {h['open']}–{h['close']} ({state})"


# --------------------------------------------------------------------------- answers


def _health(seen: Seen, loc: str) -> Reply:
    conds = set(seen.health)
    parts = []
    if "pregnant" in conds:
        parts.append(_l(loc, "Homiladorlik va emizish davrida sport qo'shimchalarini (ayniqsa pre-workout, yog' yoqiruvchi, yuqori kofeinli mahsulotlar) faqat shifokor ruxsati bilan qabul qiling.",
                        "При беременности и кормлении спортивные добавки (особенно предтрены, жиросжигатели и всё с высоким кофеином) — только с разрешения врача.",
                        "During pregnancy or breastfeeding, take sports supplements (especially pre-workouts, fat burners and high-caffeine products) only with your doctor's approval."))
    if "heart" in conds:
        parts.append(_l(loc, "Yurak yoki qon bosimi muammosida **pre-workout, kofeinli va yog' yoqiruvchi mahsulotlar tavsiya etilmaydi** — ular yurak urishini va bosimni oshirishi mumkin. Avval kardiolog bilan maslahatlashing.",
                        "При проблемах с сердцем или давлением **предтрены, кофеин и жиросжигатели не рекомендуются** — они повышают пульс и давление. Сначала проконсультируйтесь с кардиологом.",
                        "With heart or blood-pressure problems, **pre-workouts, caffeine and fat burners are not recommended** — they raise heart rate and blood pressure. Check with a cardiologist first."))
    if "child" in conds:
        parts.append(_l(loc, "Bolalar va 18 yoshgacha o'smirlarga sport ozuqasi (pre-workout, kreatin, yog' yoqiruvchi) berilmaydi. Vitamin va omega-3 uchun **bolalar uchun mo'ljallangan** mahsulotni pediatr tavsiyasi bilan tanlang.",
                        "Детям и подросткам до 18 лет спортивное питание (предтрены, креатин, жиросжигатели) не дают. Витамины и омега-3 — только **детские формы** и по совету педиатра.",
                        "Children and teens under 18 shouldn't take sports supplements (pre-workouts, creatine, fat burners). For vitamins and omega-3, choose **kids' formulas** with a paediatrician's advice."))
    if "kidney" in conds:
        parts.append(_l(loc, "Buyrak yoki jigar kasalligida protein, kreatin va boshqa qo'shimchalarni faqat shifokor ruxsati bilan ichish mumkin.",
                        "При болезнях почек или печени протеин, креатин и другие добавки — только с разрешения врача.",
                        "With kidney or liver disease, take protein, creatine or other supplements only with your doctor's approval."))
    if "diabetes" in conds:
        parts.append(_l(loc, "Qandli diabetda geyner va shakarli mahsulotlardan qoching; har qanday qo'shimchani endokrinolog bilan kelishing.",
                        "При диабете избегайте гейнеров и продуктов с сахаром; любые добавки согласуйте с эндокринологом.",
                        "With diabetes, avoid gainers and sugary products, and agree any supplement with your endocrinologist."))
    if "meds" in conds or "allergy" in conds:
        parts.append(_l(loc, "Dori ichayotgan yoki allergiyangiz bo'lsa, mahsulot tarkibini shifokorga ko'rsatib, ruxsat oling.",
                        "Если вы принимаете лекарства или есть аллергия — покажите состав продукта врачу.",
                        "If you take medication or have allergies, show the product's ingredients to your doctor first."))
    ids, chips = [], []
    if "child" in conds:
        idx = _index()["cats"]
        kids = [cid for name, cid in idx.items() if any(w in name for w in ("bolalar", "детск", "kids", "children"))]
        if kids:
            ids = [p["id"] for p in _search(loc=loc, category=kids[0], limit=3)]
    text = "⚠️ " + "\n\n".join(parts) + "\n\n" + _l(loc, "Sog'lom odamlar uchun xavfsiz variantlar haqida so'rasangiz, yordam beraman.",
                                                    "Если нужно, подскажу безопасные варианты для здоровых людей.", "Happy to suggest safe options for healthy adults if you need.")
    if ids:
        text += "\n\n" + _l(loc, "Bolalar uchun mo'ljallangan mahsulotlar:", "Детские продукты:", "Products made for kids:")
    chips = [_l(loc, "Operator bilan bog'lanish", "Связаться с оператором", "Talk to a person")]
    return Reply(text, ids, chips, last="health")


def _contacts(seen: Seen, loc: str) -> Reply:
    from apps.assistant.infrastructure.advisor import kb

    stores = seen.stores
    lines = [kb.contacts(loc)]
    venues = []
    if stores:
        for s in stores[:3]:
            phones = ", ".join(s.phone_numbers[:2]) if isinstance(s.phone_numbers, list) else ""
            lines.append(f"🏪 **{s.name}** — {phones or '—'} · {_hours_line(s, loc)}")
            if (v := _venue(s)) is not None:
                venues.append(v)
    else:
        lines.append(_l(loc, "Filial telefonini bilish uchun shahar yoki tuman nomini yozing.", "Напишите город или район — дам телефон филиала.", "Tell me your city or district for the branch phone."))
    return Reply("\n".join(x for x in lines if x), [], [_l(loc, "Do'konlar qayerda?", "Где магазины?", "Where are your stores?")], venues, last="contacts")


def _hours(seen: Seen, loc: str) -> Reply:
    from apps.stores.infrastructure.models import Store

    stores = seen.stores or list(Store.objects.filter(kind="store", status="active").order_by("city", "name")[:10])
    head = _l(loc, "🕘 **Ish vaqti**", "🕘 **Часы работы**", "🕘 **Opening hours**")
    lines = [f"• **{s.name}** — {_hours_line(s, loc)}" for s in stores]
    tail = "" if seen.stores else "\n\n" + _l(loc, "Online buyurtma 24/7 qabul qilinadi.", "Онлайн-заказы принимаем 24/7.", "Online orders are open 24/7.")
    venues = [v for s in seen.stores[:2] if (v := _venue(s))]
    return Reply(head + "\n" + "\n".join(lines) + tail, [], [_l(loc, "Telefon raqamingiz", "Ваш телефон", "Your phone number")], venues, last="hours")


def _promo(seen: Seen, loc: str) -> Reply:
    from apps.assistant.infrastructure import knowledge

    items = _search(loc=loc, sort="-discount", on_sale=True, limit=5, category=seen.cats[0] if seen.cats else None)
    promos = [h.entry for h in knowledge.search(seen.text + " aksiya", limit=2) if h.entry.topic == "promo"]
    parts = [e.answer(loc) for e in promos]
    if items:
        parts.append(_l(loc, "🔥 **Hozir chegirmadagi mahsulotlar:**", "🔥 **Сейчас со скидкой:**", "🔥 **On sale now:**") + "\n" + _lines(items, loc))
    if not parts:
        parts.append(_l(loc, "Hozir faol chegirma yo'q. Har xariddan esa **NutriZone Coins** cashback olasiz (1% dan 8% gacha).",
                        "Сейчас активных скидок нет. Но с каждой покупки вы получаете кешбэк **NutriZone Coins** (от 1% до 8%).",
                        "No active sales right now — but every purchase earns **NutriZone Coins** cashback (1% to 8%)."))
    return Reply("\n\n".join(parts), [p["id"] for p in items[:4]], [_l(loc, "Coin nima?", "Что такое коины?", "What are coins?")], last="promo")


def _compare(seen: Seen, loc: str) -> Reply | None:
    from apps.assistant.infrastructure.advisor import kb

    kinds = seen.concepts[:2]
    if len(kinds) < 2:
        return None
    a, b = kinds
    name = kb.T["kind_name"][loc]
    why = kb.T["why"][loc]
    use = kb.T["usage"][loc]
    text = _l(loc, f"⚖️ **{name[a]} va {name[b]}** — farqi:", f"⚖️ **{name[a]} или {name[b]}** — в чём разница:", f"⚖️ **{name[a]} vs {name[b]}**:")
    text += f"\n\n• **{name[a]}** — {why[a]}. _{use[a]}_\n• **{name[b]}** — {why[b]}. _{use[b]}_"
    pair = {frozenset(("protein", "creatine")), frozenset(("protein", "bcaa")), frozenset(("protein", "gainer"))}
    if frozenset(kinds) in pair:
        text += "\n\n" + _l(loc, "Ular bir-birini almashtirmaydi — birga ichsa bo'ladi. Maqsadingizni yozsangiz (massa, ozish, chidamlilik), to'g'ri juftlikni tanlab beraman.",
                            "Они не заменяют друг друга — их можно сочетать. Напишите цель (масса, похудение, выносливость) — подберу правильную пару.",
                            "They don't replace each other — you can take both. Tell me your goal (muscle, fat loss, endurance) and I'll pick the right pair.")
    else:
        text += "\n\n" + _l(loc, "Qaysi biri kerakligi maqsadingizga bog'liq — yozing, aniq tanlab beraman.", "Выбор зависит от цели — напишите её, подберу точно.",
                            "The right one depends on your goal — tell me and I'll choose.")
    from apps.assistant.infrastructure.advisor import reco

    ids = []
    for k in kinds:
        found = _search(reco.QUERIES.get(k, k), loc, limit=1)
        ids += [p["id"] for p in found]
    return Reply(text, ids, [_l(loc, "Massa uchun", "Для массы", "For muscle"), _l(loc, "Ozish uchun", "Для похудения", "For fat loss")], last="compare")


def _branch_stock(seen: Seen, loc: str, query: str) -> Reply | None:
    from apps.stores.infrastructure.availability import branches

    items = _search(query, loc, limit=3, category=seen.cats[0] if seen.cats and not query else None, brand=seen.brands[0] if seen.brands and not query else None, in_stock=False)
    if not items:
        return None
    store_ids = {str(s.id) for s in seen.stores}
    rows = branches([p["variant"] for p in items if p.get("variant")])
    lines, venues = [], []
    for p in items:
        here = [b for b in rows.get(p["variant"], []) if b["store_id"] in store_ids]
        if here and here[0]["available_quantity"] > 0:
            lines.append("✅ " + _l(loc, f"**{p['name']}** — {here[0]['name']}da bor ({here[0]['available_quantity']} dona), {_money(p['price'])}",
                                   f"**{p['name']}** — есть в {here[0]['name']} ({here[0]['available_quantity']} шт), {_money(p['price'])}",
                                   f"**{p['name']}** — in stock at {here[0]['name']} ({here[0]['available_quantity']} pcs), {_money(p['price'])}"))
        else:
            other = [b for b in rows.get(p["variant"], []) if b["available_quantity"] > 0][:2]
            alt = ", ".join(b["name"] for b in other)
            lines.append("❌ " + _l(loc, f"**{p['name']}** — bu filialda hozir yo'q" + (f". Bor: {alt}" if alt else ". Saytdan buyurtma qilsangiz, yetkazib beramiz."),
                                   f"**{p['name']}** — в этом филиале сейчас нет" + (f". Есть: {alt}" if alt else ". Можно заказать на сайте с доставкой."),
                                   f"**{p['name']}** — not at this branch right now" + (f". Available at: {alt}" if alt else ". Order on the site for delivery.")))
    for s in seen.stores[:1]:
        if (v := _venue(s)) is not None:
            venues.append(v)
            lines.append(f"\n📍 **{s.name}** — {v['address']} · {_hours_line(s, loc)}")
    return Reply("\n".join(lines), [p["id"] for p in items], [_l(loc, "Yetkazib berish", "Доставка", "Delivery")], venues, last="branch_stock")


def _price(seen: Seen, loc: str, query: str) -> Reply | None:
    items = _search(query, loc, limit=4, in_stock=False) if query else []
    if not items and (seen.cats or seen.brands):
        items = _search(loc=loc, limit=4, category=seen.cats[0] if seen.cats else None, brand=seen.brands[0] if seen.brands else None, in_stock=False)
    if not items:
        return None
    head = _l(loc, "💰 **Narxlar:**", "💰 **Цены:**", "💰 **Prices:**")
    tail = _l(loc, "Kartochkada hajm va ta'mlarni tanlab, savatga qo'shishingiz mumkin.", "В карточке выберите объём и вкус и добавьте в корзину.",
              "Pick the size and flavour on the card and add it to the cart.")
    return Reply(f"{head}\n{_lines(items, loc)}\n\n{tail}", [p["id"] for p in items], [_l(loc, "Arzonroq variant", "Вариант дешевле", "Cheaper option")], last="price")


def _best(seen: Seen, loc: str) -> Reply | None:
    from apps.assistant.infrastructure.advisor import reco

    cat = seen.cats[0] if seen.cats else None
    brand = seen.brands[0] if seen.brands else None
    query = "" if (cat or brand) else (reco.QUERIES.get(seen.concepts[0], seen.concepts[0]) if seen.concepts else "")
    items = _search(query, loc, limit=4, category=cat, brand=brand, sort="-popularity")
    if not items:
        return None
    head = _l(loc, "🏆 **Eng ko'p tanlanadiganlar:**", "🏆 **Самые популярные:**", "🏆 **Most popular:**")
    tail = _l(loc, "Maqsadingiz, vazningiz va byudjetingizni yozsangiz, aynan sizga mosini tanlab beraman.",
              "Напишите цель, вес и бюджет — подберу именно под вас.", "Tell me your goal, weight and budget and I'll pick the one that fits you.")
    return Reply(f"{head}\n{_lines(items, loc)}\n\n{tail}", [p["id"] for p in items], [_l(loc, "Menga tanlab bering", "Подберите мне", "Pick one for me")], last="best")


def _listing(seen: Seen, loc: str) -> Reply | None:
    cat = seen.cats[0] if seen.cats else None
    brand = seen.brands[0] if seen.brands else None
    if not (cat or brand):
        return None
    items = _search(loc=loc, limit=4, category=cat, brand=brand)
    if not items:
        return Reply(_l(loc, "Hozir bu yo'nalishda mavjud mahsulot yo'q. Kelganda xabar berishimiz uchun saytdagi «Mahsulot topib bering» xizmatidan foydalaning.",
                        "Сейчас в наличии нет. Оставьте заявку «Найти товар» на сайте — сообщим, когда появится.",
                        "Nothing in stock in this line right now. Use «Find a product for me» on the site and we'll tell you when it arrives."), [], [], last="listing")
    head = _l(loc, "✅ **Ha, bor:**", "✅ **Да, есть:**", "✅ **Yes, we have:**")
    tail = _l(loc, "Qaysi biri kerakligini bilmasangiz, maqsadingizni yozing — tanlab beraman.", "Если сомневаетесь — напишите цель, подберу.",
              "Not sure which? Tell me your goal and I'll choose.")
    return Reply(f"{head}\n{_lines(items, loc)}\n\n{tail}", [p["id"] for p in items], [_l(loc, "Qanday ichiladi?", "Как принимать?", "How to take it?")], last="listing")


def respond(meta: dict, text: str, loc: str) -> Reply | None:
    """An answer from live shop data for the questions Brain v2 understands, else None."""
    loc = loc if loc in LOCALES else "uz"
    seen = understand(text)
    b = seen.both
    parsed = nlu.parse(text)
    if seen.health and (seen.concepts or seen.cats or _has(b, CAN_I)):
        return _health(seen, loc)
    if _has(b, CONTACT) and not seen.concepts:
        return _contacts(seen, loc)
    if _has(b, HOURS) and not seen.concepts and not seen.cats:
        return _hours(seen, loc)
    if _has(b, PROMO):
        return _promo(seen, loc)
    if len(seen.concepts) >= 2 and _has(b, COMPARE):
        if (r := _compare(seen, loc)) is not None:
            return r
    query = _clean_query(text)
    for s in seen.stores:  # the branch's own words aren't part of the product name
        for k in ({nlu.normalize(x) for x in (s.city, s.district, s.name) if x}):
            query = re.sub(re.escape(k[: max(4, min(len(k), 6))]) + r"\w*", " ", query)
    query = re.sub(r"\s+", " ", query).strip()
    if seen.stores and (seen.concepts or seen.cats or seen.brands or (query and _has(b, HAVE))):
        if (r := _branch_stock(seen, loc, query)) is not None:
            return r
    if _has(b, PRICE):
        if (r := _price(seen, loc, query)) is not None:
            return r
    if _has(b, BEST) and (seen.concepts or seen.cats or seen.brands) and parsed.intent != "usage" and not parsed.facts:
        if (r := _best(seen, loc)) is not None:
            return r
    if (_has(b, HAVE) or (len(seen.text.split()) <= 3 and (seen.cats or seen.brands))) and parsed.intent not in ("usage",) and not parsed.facts:
        if (r := _listing(seen, loc)) is not None:
            return r
        if query and (items := _search(query, loc, limit=4, in_stock=False)):
            head = _l(loc, "✅ **Topdim:**", "✅ **Нашёл:**", "✅ **Found it:**")
            return Reply(f"{head}\n{_lines(items, loc)}", [p["id"] for p in items], [_l(loc, "Qanday ichiladi?", "Как принимать?", "How to take it?")], last="listing")
    return None
