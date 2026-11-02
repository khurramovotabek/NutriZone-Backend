"""
The free advisor reads the catalogue like a shop assistant reads the tub: answers about one product (composition,
protein per serving, calories and sugar, servings and how long a tub lasts, price per serving, directions, flavours,
sizes, warnings and allergens, country), about a brand (story, country, best sellers) and a category (what it is, its
sections, best sellers) -- from what the shop entered on the dashboard, nothing invented. A field the card doesn't
have is said plainly and recorded for the shop to fill in (AI maslahatchini o'qitish).

"uning tarkibi qanday?" after a product was shown asks about that product (meta["focus"]).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from apps.assistant.infrastructure.advisor import nlu

# what is asked about a product, in the order they are answered; matched as word prefixes (nlu._has)
ASPECTS: dict[str, tuple[str, ...]] = {
    "protein": ("necha gramm oqsil", "qancha oqsil", "oqsil miqdori", "necha gramm protein", "qancha protein bor", "сколько белка", "белка в порции", "сколько протеина в",
                "how much protein", "protein per serving", "grams of protein"),
    "calories": ("kaloriya", "kkal", "shakar", "uglevod", "калори", "ккал", "сахар", "углевод", "calorie", "kcal", "sugar", "carbs"),
    "facts": ("tarkib", "ingredient", "nimadan iborat", "состав", "ингредиент", "из чего", "what's in it", "what is in it", "supplement facts", "nutrition facts"),
    "servings": ("necha porsiya", "nechta porsiya", "porsiya soni", "necha kunga", "qancha vaqtga yetadi", "necha marta ichsa bo'ladi", "сколько порций", "на сколько хватает",
                 "на сколько хватит", "servings", "how long will it last", "how long does it last"),
    "per_serving": ("porsiya narxi", "bir porsiya necha pul", "цена порции", "стоимость порции", "price per serving", "cost per serving"),
    "directions": ("qanday ich", "qanday qabul", "qachon ich", "qanday tayyorla", "qanday aralashtir", "как принимать", "как пить", "когда пить", "как разводить",
                   "how to take", "how to use", "how do i take", "when to take", "how to mix", "directions"),
    "flavours": ("ta'mlar", "qanday ta'm", "qaysi ta'm", "ta'mi bor", "вкус", "flavour", "flavor"),
    "sizes": ("hajm", "qadoq", "necha kg", "necha kilo", "katta banka", "размер", "объём", "объем", "фасовк", "вес банки", "size", "how big"),
    "warnings": ("allergi", "laktoza", "soya", "glyuten", "gluten", "nojo'ya", "kimga mumkin emas", "kimlarga mumkin emas", "zararli tomoni", "противопоказ", "аллерг",
                 "побочн", "лактоз", "глютен", "side effect", "allergen", "lactose", "contraindic", "who should not"),
    "origin": ("qaysi davlat", "qayerda ishlab", "qayerniki", "qaysi mamlakat", "kimniki", "страна", "чья фирма", "где производ", "кто производит", "made in", "country",
               "where is it made", "who makes"),
    "about": ("haqida", "nima bu", "qanaqa mahsulot", "yaxshimi", "расскажи", "что за", "про ", "отзыв", "about", "tell me", "is it good", "review", "worth it"),
}
ORDER = ("about", "facts", "protein", "calories", "servings", "per_serving", "directions", "flavours", "sizes", "warnings", "origin")
FOLLOW_UP = ("uning", "shuning", "bunda", "bu mahsulot", "shu mahsulot", "unda", "его", "у него", "в нём", "в нем", "этого", "it's", "its ", "this one", "this product")
FACT_WORDS = {"protein": ("oqsil", "белок", "белка", "protein"), "calories": ("energiya", "kkal", "kaloriya", "uglevod", "shakar", "yog'", "калори", "ккал", "углевод",
                                                                           "сахар", "жир", "calorie", "kcal", "carbohydrate", "sugar", "fat")}
ASPECT_WORDS = re.compile(r"\b(tarkib\w*|haqida|nima|bu|qanaqa|qanday|qancha|necha|nechta|gramm|oqsil\w*|kaloriya\w*|shakar\w*|porsiya\w*|ta'm\w*|hajm\w*|qadoq\w*|"
                          r"ich\w*|qabul|davlat\w*|ishlab|chiqar\w*|allergi\w*|yaxshi\w*|bor|mi|kim\w*|mumkin|emas|uning|shu\w*|"
                          r"состав|сколько|белка?|калори\w*|сахар\w*|порци\w*|вкус\w*|размер\w*|как|принимать|пить|страна|производ\w*|расскажи|что|за|про|о|его|"
                          r"what|is|in|it|how|much|many|per|serving\w*|calories|sugar|flavou?rs?|sizes?|take|use|country|made|about|tell|me|the|of|this|good)\b")


@dataclass
class Answer:
    text: str
    product_ids: list = field(default_factory=list)
    chips: list = field(default_factory=list)
    focus: str | None = None
    missing: bool = False  # a field the card doesn't have -- recorded for the shop


def _l(loc: str, uz: str, ru: str, en: str) -> str:
    return {"uz": uz, "ru": ru, "en": en}[loc]


def _money(v) -> str:
    try:
        return f"{int(float(v)):,}".replace(",", " ")
    except (TypeError, ValueError):
        return ""


def aspects_in(text: str) -> list[str]:
    t = nlu.normalize(text)
    both = f"{t} {t.translate(nlu.LATIN_FROM_CYR)}"
    found = [a for a, stems in ASPECTS.items() if nlu._has(both, stems)]
    if "protein" in found and "facts" in found:
        found.remove("facts")
    return [a for a in ORDER if a in found]


QUESTION_WORDS = re.compile(r"\b(qaysi\w*|qayer\w*|kim\w*|bormi|bor|mavjud\w*|sizda\w*|bo'lim\w*|kategoriya\w*|turkum\w*|brend\w*|firma\w*|kompaniya\w*|"
                            r"есть|ли|у|вас|бренд\w*|фирм\w*|компани\w*|раздел\w*|категори\w*|do|you|have|brand\w*|company|category|section)\b")
# one-word aspect stems ("allergi", "laktoza", "вкус") -- any word they start is about the question, not the product's name
_ASPECT_STEMS = tuple(stem for stems in ASPECTS.values() for stem in stems if " " not in stem.strip() and len(stem.strip()) >= 3)


def _product_query(text: str) -> str:
    q = QUESTION_WORDS.sub(" ", ASPECT_WORDS.sub(" ", nlu.normalize(re.sub(r"[?!.,]", " ", text))))
    words = [w for w in q.split() if not any(w.startswith(stem.strip()) for stem in _ASPECT_STEMS)]
    return " ".join(words).strip()


def _only_kind_words(query: str) -> bool:
    """"protein", "kreatin" alone name a kind, not a product -- the knowledge base answers those."""
    words = [w for w in query.split() if len(w) > 1]
    rest = nlu.normalize(" ".join(w for w in words if not nlu.concepts_in(w)))
    return not rest or len(rest) < 3


def _find_product(text: str, loc: str, focus: str | None) -> str | None:
    from apps.assistant.infrastructure.advisor import brain

    query = _product_query(text)
    if query and not _only_kind_words(query):
        found = brain._search(query, loc, limit=1, in_stock=False)
        if found and _names_it(found[0]["name"] or "", query):
            return found[0]["id"]
    t = nlu.normalize(text)
    if focus and (not query or nlu._has(t, FOLLOW_UP)):  # "kreatin qanday ichiladi" is about creatine, not the tub shown before
        return focus
    return None


def _compact(text: str) -> str:
    return re.sub(r"[^0-9a-zа-яёўқғҳ]", "", nlu.normalize(text))


def _names_it(name: str, query: str) -> bool:
    """The search hit really is the product asked about: a word of the question that isn't a kind ("vitamin", "protein")
    starts a part of its name -- "goldstandart" in "Optimum Nutrition Gold Standard", not "ko'p mashg'ulotda" in "Vitamin C"."""
    compact = _compact(name)
    words = [_compact(w) for w in query.split() if len(w) >= 3 and not nlu.concepts_in(nlu.normalize(w))]
    return any(len(w) >= 3 and w[:5] in compact for w in words)


def _fact_lines(facts: str, words=None) -> list[str]:
    lines = [re.sub(r"\s+", " ", x).strip(" •-") for x in (facts or "").splitlines()]
    lines = [x for x in lines if x]
    if words:
        lines = [x for x in lines if nlu._has(" " + nlu.normalize(x), words)]
    return lines


def _protein_grams(facts: str) -> float | None:
    for line in _fact_lines(facts, FACT_WORDS["protein"]):
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:g|г|gr)\b", line.lower())
        if m and not re.search(r"manba|источник|source", line.lower()):
            return float(m.group(1).replace(",", "."))
    return None


def _sentences(text: str, limit: int = 380) -> str:
    out = ""
    for s in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text or "").strip()):
        if len(out) + len(s) > limit and out:
            break
        out = f"{out} {s}".strip()
    return out


def product_answer(text: str, loc: str, aspects: list[str], focus: str | None) -> Answer | None:  # noqa: C901 - one plain branch per aspect, in the order answered
    from apps.assistant.infrastructure import tools

    pid = _find_product(text, loc, focus)
    if not pid:
        return None
    try:
        d = tools.get_product_details({"product_id": pid}, loc)
    except tools.ToolError:
        return None
    facts = d.get("supplement_facts") if isinstance(d.get("supplement_facts"), str) else ""
    nutrition = d.get("nutrition") or {}
    serving_g, servings = nutrition.get("serving_size_grams"), nutrition.get("servings_per_container")
    price = d.get("price_uzs")
    protein = _protein_grams(facts)
    lines = [f"**{d['name']}**" + (f" · {d['brand']}" if d.get("brand") else "")]
    missing = False

    def nothing(what: str) -> str:
        nonlocal missing
        missing = True
        return _l(loc, f"Kartochkada {what} haqida ma'lumot hali kiritilmagan — operator aniq aytib beradi.",
                  f"На карточке пока нет данных: {what} — уточните у оператора.", f"The product card has no {what} yet — our team can tell you.")

    for a in aspects:
        if a == "about":
            desc = _sentences(d.get("description") or "")
            key = []
            if protein:
                key.append(_l(loc, f"{protein:g} g oqsil/porsiya", f"{protein:g} г белка/порция", f"{protein:g} g protein/serving"))
            if servings:
                key.append(_l(loc, f"{servings:g} porsiya", f"{servings:g} порций", f"{servings:g} servings"))
            if d.get("flavours"):
                key.append(_l(loc, f"{len(d['flavours'])} xil ta'm", f"{len(d['flavours'])} вкусов", f"{len(d['flavours'])} flavours"))
            if price:
                key.append(f"{_money(price)} so'm")
            lines.append(desc or nothing(_l(loc, "tavsif", "описание", "a description")))
            if key:
                lines.append("• " + " · ".join(key))
        elif a == "facts":
            rows = _fact_lines(facts)
            lines.append(("🧪 " + _l(loc, "**Tarkibi**", "**Состав**", "**Composition**") + "\n" + "\n".join(f"• {x}" for x in rows[:14])) if rows
                         else nothing(_l(loc, "tarkib", "состав", "the composition")))
        elif a == "protein":
            if protein:
                share = f" ({round(protein * 100 / serving_g)}%)" if serving_g else ""
                size = f" ({serving_g:g} g)" if serving_g else ""
                lines.append("💪 " + _l(loc, f"Bir porsiyada{size} **{protein:g} g oqsil**{share}.", f"В порции{size} **{protein:g} г белка**{share}.",
                                       f"One serving{size} has **{protein:g} g of protein**{share}."))
            else:
                lines.append(nothing(_l(loc, "oqsil miqdori", "количество белка", "the protein per serving")))
        elif a == "calories":
            rows = _fact_lines(facts, FACT_WORDS["calories"])
            if nutrition.get("calories") and not rows:
                rows = [_l(loc, f"Energiya: {nutrition['calories']:g} kkal", f"Энергия: {nutrition['calories']:g} ккал", f"Energy: {nutrition['calories']:g} kcal")]
            lines.append(("🔥 " + "\n".join(f"• {x}" for x in rows[:7])) if rows else nothing(_l(loc, "kaloriya", "калорийность", "calories")))
        elif a in ("servings", "per_serving"):
            if servings:
                body = _l(loc, f"📦 Bankada **{servings:g} porsiya**" + (f" ({serving_g:g} g)" if serving_g else "") +
                          f": kuniga 1 porsiyada ~{servings:g} kunga, 2 porsiyada ~{servings / 2:g} kunga yetadi.",
                          f"📦 В банке **{servings:g} порций**" + (f" ({serving_g:g} г)" if serving_g else "") +
                          f": при 1 порции в день — ~{servings:g} дней, при 2 — ~{servings / 2:g}.",
                          f"📦 **{servings:g} servings** per tub" + (f" ({serving_g:g} g)" if serving_g else "") +
                          f": ~{servings:g} days at 1 a day, ~{servings / 2:g} at 2.")
                if price and (a == "per_serving" or "per_serving" not in aspects):
                    body += " " + _l(loc, f"Bir porsiya ≈ **{_money(price / servings)} so'm**.", f"Порция ≈ **{_money(price / servings)} сум**.",
                                     f"One serving ≈ **{_money(price / servings)} UZS**.")
                if body not in lines:
                    lines.append(body)
            elif a == "servings" or "servings" not in aspects:
                lines.append(nothing(_l(loc, "porsiyalar soni", "число порций", "the number of servings")))
        elif a == "directions":
            lines.append(("🥤 " + _l(loc, "**Qanday ichiladi**", "**Как принимать**", "**How to take it**") + "\n" + _sentences(d["directions"], 520)) if d.get("directions")
                         else nothing(_l(loc, "qo'llash usuli", "способ применения", "directions")))
        elif a == "flavours":
            fl = d.get("flavours") or []
            lines.append(("😋 " + _l(loc, f"**{len(fl)} xil ta'm:** ", f"**Вкусов: {len(fl)}:** ", f"**{len(fl)} flavours:** ") + ", ".join(fl[:14]) + (" …" if len(fl) > 14 else ""))
                         if fl else _l(loc, "Bu mahsulot bitta ta'mda (yoki ta'msiz).", "У этого продукта один вкус (или без вкуса).", "This product comes in one flavour (or unflavoured)."))
        elif a == "sizes":
            vs = [v for v in d.get("variants") or [] if v.get("size")]
            seen_sizes, rows = set(), []
            for v in vs:
                if v["size"] in seen_sizes:
                    continue
                seen_sizes.add(v["size"])
                rows.append(f"• {v['size']} — {_money(v.get('price_uzs') or price)} so'm" + ("" if v.get("in_stock") else _l(loc, " (hozir yo'q)", " (нет в наличии)", " (out of stock)")))
            lines.append(("⚖️ " + _l(loc, "**Hajmlari:**", "**Фасовки:**", "**Sizes:**") + "\n" + "\n".join(rows[:8])) if rows else nothing(_l(loc, "hajm", "фасовка", "sizes")))
        elif a == "warnings":
            lines.append(("⚠️ " + _sentences(d["warnings"], 520)) if d.get("warnings") else nothing(_l(loc, "ogohlantirish va allergenlar", "противопоказания и аллергены",
                                                                                                        "warnings and allergens")))
        elif a == "origin":
            country = _brand_country(pid, loc)
            lines.append("🌍 " + (_l(loc, f"Brend: **{d.get('brand') or '—'}**, ishlab chiqaruvchi davlat: **{country}**.", f"Бренд: **{d.get('brand') or '—'}**, страна: **{country}**.",
                                    f"Brand: **{d.get('brand') or '—'}**, country: **{country}**.") if country else nothing(_l(loc, "ishlab chiqaruvchi davlat", "страна производства", "the country of origin"))))
    if d.get("branches_with_stock") and any(a in aspects for a in ("about", "sizes")):
        lines.append("🏪 " + _l(loc, "Bor: ", "Есть в: ", "In stock at: ") + ", ".join(b["name"] for b in d["branches_with_stock"][:3]))
    chips = [_l(loc, "Qanday ichiladi?", "Как принимать?", "How to take it?"), _l(loc, "Tarkibi qanday?", "Какой состав?", "What's in it?"),
             _l(loc, "Arzonroq variant", "Вариант дешевле", "Cheaper option")]
    return Answer("\n\n".join(lines), [pid], chips, focus=pid, missing=missing)


def _brand_country(product_id, loc: str) -> str:
    from apps.products.infrastructure import models as orm

    p = orm.Product.objects.filter(pk=product_id).select_related("brand__country").first()
    country = p.brand.country if p and p.brand_id and p.brand else None
    if country is None:
        return ""
    names = dict(country.translations.values_list("locale_code", "name"))
    return f"{country.icon or ''} {names.get(loc) or names.get('uz') or country.code}".strip()


ABOUT_BRAND = ASPECTS["about"] + ASPECTS["origin"] + ("brend", "brand", "бренд", "фирма", "kompaniya", "компания", "company", "original")


def brand_answer(text: str, loc: str, brand_ids: list) -> Answer | None:
    """"Olimp qaysi davlatniki?", "Optimum Nutrition haqida", "расскажи о бренде Rule 1"."""
    from apps.assistant.infrastructure.advisor import brain
    from apps.products.infrastructure import models as orm

    b = orm.Brand.objects.filter(pk=brand_ids[0], deleted_at__isnull=True).select_related("country").first()
    if b is None:
        return None
    tr = {t.locale_code: t for t in b.translations.all()}
    t = tr.get(loc) or tr.get("uz") or next(iter(tr.values()), None)
    if t is None:
        return None
    desc = (t.description or "").strip() or ((tr.get("uz").description or "").strip() if tr.get("uz") else "")
    country = ""
    if b.country_id:
        names = dict(b.country.translations.values_list("locale_code", "name"))
        country = f"{b.country.icon or ''} {names.get(loc) or names.get('uz') or b.country.code}".strip()
    count = orm.Product.objects.filter(brand_id=b.pk, status="published", deleted_at__isnull=True).count()
    top = brain._search(loc=loc, limit=3, brand=b.pk, sort="-popularity")
    lines = [f"🏷 **{t.name}**" + (f" · {country}" if country else "")]
    lines.append(_sentences(desc, 520) if desc else _l(loc, "Brend haqida tavsif hali kiritilmagan.", "Описание бренда пока не добавлено.", "No brand description yet."))
    if count:
        lines.append(_l(loc, f"NutriZone'da **{count} ta** mahsuloti bor. Eng ko'p tanlanadiganlar:", f"В NutriZone **{count}** товаров бренда. Самые популярные:",
                        f"NutriZone carries **{count}** of its products. Most popular:"))
    return Answer("\n\n".join(lines), [p["id"] for p in top], [_l(loc, "Eng arzoni qaysi?", "Какой самый дешёвый?", "Which is the cheapest?"),
                                                                 _l(loc, "Menga tanlab bering", "Подберите мне", "Pick one for me")], missing=not desc)


def category_answer(text: str, loc: str, category_ids: list) -> Answer | None:
    """"Aminokislotalar bo'limida nima bor?", "расскажи про категорию гейнеры"."""
    from apps.assistant.infrastructure import tools
    from apps.assistant.infrastructure.advisor import brain
    from apps.products.infrastructure import models as orm

    name = orm.CategoryTranslation.objects.filter(category_id=category_ids[0], locale_code__in=(loc, "uz")).values_list("name", flat=True).first()
    info = tools.get_category_info({"name": name}, loc) if name else {"found": False}
    if not info.get("found"):
        return None
    top = brain._search(loc=loc, limit=4, category=category_ids[0], sort="-popularity")
    lines = [f"📂 **{info['name']}**", _sentences(info.get("description") or "", 600) or _l(loc, "Bo'lim tavsifi hali kiritilmagan.", "Описание раздела пока не добавлено.",
                                                                                           "No description for this section yet.")]
    if info.get("subcategories"):
        lines.append(_l(loc, "Bo'limlar: ", "Разделы: ", "Sections: ") + ", ".join(info["subcategories"][:10]))
    if info.get("products"):
        lines.append(_l(loc, f"Jami **{info['products']} ta** mahsulot. Eng ko'p tanlanadiganlar:", f"Всего **{info['products']}** товаров. Самые популярные:",
                        f"**{info['products']}** products in total. Most popular:"))
    return Answer("\n\n".join(lines), [p["id"] for p in top], [_l(loc, "Menga tanlab bering", "Подберите мне", "Pick one for me")], missing=not info.get("description"))


CATEGORY_CUES = ("bo'lim", "kategoriya", "turkum", "раздел", "категори", "category", "section")
DESCRIBE = ("haqida", "расскажи", "про ", "about", "tell me")


def respond(meta: dict, text: str, loc: str) -> Answer | None:
    """A catalogue answer when the message asks about a product, a brand or a category -- else None."""
    from apps.assistant.infrastructure.advisor import brain

    aspects = aspects_in(text)
    seen = brain.understand(text)
    # safety notes and "A yoki B" comparisons answer those; an allergy question about a product is answered from its card
    if set(seen.health) - {"allergy"} or brain.COMPARE_SPLIT.search(seen.text):
        return None
    t = nlu.normalize(text)
    both = f"{t} {t.translate(nlu.LATIN_FROM_CYR)}"
    query = _product_query(text)
    brands = seen.brands or _brands_named(query)  # "Olimp" is "Olimp Sport Nutrition"
    names_a_product = bool(query) and not _only_kind_words(query) and not (brands and _is_just_the_brand(query, brands)) and _find_product(text, loc, None) is not None
    if aspects and (names_a_product or (meta.get("focus") and (not query or nlu._has(t, FOLLOW_UP)))):
        if aspects == ["about"] and brands and not names_a_product:
            return brand_answer(text, loc, brands)
        if (r := product_answer(text, loc, aspects, meta.get("focus"))) is not None:
            return r
    if brands and nlu._has(both, ABOUT_BRAND) and not names_a_product:
        return brand_answer(text, loc, brands)
    # "geynerlar bo'limi haqida", "расскажи про категорию витамины" -- the message is the category and a request to describe it,
    # not a question that happens to contain its name ("c vitaminini ko'p ichsam yaxshimi" is the knowledge base's)
    if (seen.cats and not brands and not names_a_product and nlu._has(both, CATEGORY_CUES + DESCRIBE)
            and len(_product_query(text).split()) <= 2):
        return category_answer(text, loc, seen.cats)
    return None


def _brands_named(query: str) -> list:
    """Brands whose name is the query or starts with it as a whole word ("olimp" → Olimp Sport Nutrition)."""
    from apps.products.infrastructure import models as orm

    q = nlu.normalize(query)
    if len(q) < 3:
        return []
    out = []
    for bid, name in orm.BrandTranslation.objects.filter(brand__deleted_at__isnull=True).values_list("brand_id", "name"):
        n = nlu.normalize(name)
        if (n == q or n.startswith(q + " ")) and bid not in out:
            out.append(bid)
    return out


def _is_just_the_brand(query: str, brand_ids: list) -> bool:
    """"olimp" / "optimum nutrition" alone is the brand, not one of its products."""
    from apps.products.infrastructure import models as orm

    names = {nlu.normalize(n) for n in orm.BrandTranslation.objects.filter(brand_id__in=brand_ids).values_list("name", flat=True)}
    q = nlu.normalize(query)
    return any(q == n or (n.startswith(q) and len(q) >= 3) or (q.startswith(n) and len(q) - len(n) <= 3) for n in names)
