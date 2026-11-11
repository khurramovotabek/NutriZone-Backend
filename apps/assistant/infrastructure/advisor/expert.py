"""
The sports-nutrition expert layer of the free advisor: what a good shop consultant does that a search box can't.

* Strict product kinds. "kreatin kerak" lists only the Creatine section of the category tree, never a protein whose
  description mentions creatine; "izolyat", "gidrolizat", "kazein", "vegan", "mol go'shti proteini", "monogidrat"
  narrow to that very sub-section.
* Budget picks. "500 minggacha protein" → in-stock tubs of that kind under the budget, each with the numbers that
  matter (protein per serving, servings, price of 25 g protein / of a serving / of a kilo) and a reasoned verdict:
  my pick, the best value, the most trusted brand.
* "Qaysi biri yaxshi?" right after a list compares the products just shown -- same scoring, plain reasons.
* Milk and lactose. "sut mahsulotlari yoqmaydi / laktoza ko'tarmayman / аллергия на молоко" → the difference
  between lactose intolerance and a milk-protein allergy, and the right products for each.

Everything here is rule-based and reads live catalogue data only -- it never invents a number the card doesn't have.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from apps.assistant.infrastructure.advisor import nlu

# ---------------------------------------------------------------------------------------------------- product kinds

# advisor concept → English name of its section in the category tree (category_catalog.py)
KIND_CATEGORY = {
    "protein": "Proteins", "creatine": "Creatine", "gainer": "Gainers", "bcaa": "Amino Acids", "preworkout": "Pre-Workout",
    "carnitine": "Fat Burners", "vitamin": "Multivitamins", "omega": "Omega", "collagen": "Collagen", "glutamine": "Glutamine",
    "citrulline": "Citrulline", "beta_alanine": "Beta-Alanine", "electrolytes": "Hydration", "magnesium": "Magnesium", "zinc": "Zinc",
    "calcium": "Calcium", "iron": "Iron", "vitamin_d": "Vitamin D3", "vitamin_c": "Vitamin C", "melatonin": "Melatonin",
    "sleep": "Sleep Support", "glucosamine": "Glucosamine", "test_booster": "Testosterone Support",
}

# sub-kind → (parent concept, category English name, trigger stems)
SUBTYPES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "hydro": ("protein", "Hydrolyzed Whey", ("gidrolizat", "gidroliz", "hydroly", "hydrolys", "гидролиз", "hydro whey", "iso100")),
    "isolate": ("protein", "Whey Isolate", ("izolyat", "izolat", "isolate", "изолят", "iso ")),
    "casein": ("protein", "Casein", ("kazein", "casein", "казеин", "kechki protein", "ночной протеин", "night protein")),
    "beef": ("protein", "Beef Protein", ("mol go'sht", "go'sht protein", "beef", "говяж", "мясной протеин")),
    "vegan": ("protein", "Vegan Protein", ("vegan", "o'simlik", "plant", "веган", "растительн", "no'xat", "pea protein", "гороховый")),
    "concentrate": ("protein", "Whey Protein", ("konsentrat", "concentrate", "концентрат")),
    "mono": ("creatine", "Creatine Monohydrate", ("monogidrat", "monohydrate", "моногидрат", "creapure", "крепьюр")),
    "hcl": ("creatine", "Creatine HCL", ("hcl", "gidroxlorid", "гидрохлорид", "hydrochloride")),
}

# kinds whose value is protein (compared per 25 g protein); the rest are compared per serving
PROTEIN_KINDS = ("protein",)

# Brand standing in this market: 3 = global flagship with a long record and third-party testing, 2 = established
# international brand, otherwise 1 (still genuine -- just less proven). Matching is by a lower-case name fragment.
BRAND_TIER = {
    3: ("optimum nutrition", "dymatize", "rule 1", "rule one", "myprotein", "bsn", "muscletech", "isopure", "transparent labs", "raw nutrition",
        "applied nutrition", "ghost", "now foods", "olimp", "biotech usa", "biotechusa", "scitec", "cellucor", "universal nutrition", "mutant"),
    2: ("nutrex", "ultimate nutrition", "allmax", "kevin levrone", "ronnie coleman", "musclepharm", "hi-tech", "hi tech", "evl", "evlution",
        "nutricost", "ostrovit", "reckful", "prozis", "weider", "maxler", "ironmaxx", "superior 14", "jym", "kaged", "animal", "6am run",
        "big ramy", "gat sport", "pvl", "ruff", "redcon1", "redcon 1", "bpi", "nutrend", "amix", "trec", "fa nutrition", "sporter", "yava"),
}

DAIRY = ("sut", "laktoz", "lactose", "лактоз", "молок", "молоч", "dairy", "milk", "сут ", "сутли", "sutli", "qatiq")
DAIRY_BAD = ("yoqmaydi", "yoqmay", "ichmayman", "ichol", "ko'tarmay", "kotarmay", "hazm", "qorn", "shishadi", "allergi", "аллерг",
             "не перенош", "не усваива", "непереносим", "вздут", "живот", "не пью", "не люблю", "intoleran", "allergic", "allergy",
             "can't drink", "cannot drink", "don't drink", "upset", "bloat", "dairy-free", "lactose-free", "sutsiz", "laktozasiz", "без лактоз", "безлактоз", "без молок")
ALLERGY = ("allergi", "аллерг", "allergic", "allergy", "toshma", "сыпь", "kazeinga", "белок коровьего")

NEED = ("kerak", "olmoqchi", "olaman", "olay", "sotib ol", "zakaz", "buyurtma qil", "нужен", "нужна", "нужно", "хочу купить", "куплю", "купить",
        "need", "want to buy", "looking for", "i want")  # "kreatin kerak" is a buying request, not a "what is it" question
WHICH_BETTER = ("qaysi biri", "qaysi yaxshi", "qaysisi", "qaysini", "qaysi birini", "qaysi zo'r", "qaysi ma'qul", "qaysini ol", "eng yaxshisi",
                "какой лучше", "какой из них", "что из этого", "какой выбрать", "какую выбрать", "что лучше", "which one", "which is better",
                "which should", "which do you", "best of these", "қайси")


@dataclass
class Row:
    id: str
    name: str
    brand: str
    price: float
    old_price: float = 0
    discount: int = 0
    rating: float = 0
    reviews: int = 0
    in_stock: bool = True
    protein: float | None = None  # g per serving
    servings: float | None = None
    serving_g: float | None = None
    kilos: float | None = None  # size of the tub sold at `price`
    tier: int = 1
    score: float = 0
    flags: list = field(default_factory=list)

    @property
    def per_serving(self) -> float | None:
        return self.price / self.servings if self.price and self.servings else None

    @property
    def per_25g(self) -> float | None:
        """So'm for 25 g of protein -- the fair way to compare tubs of different size and strength."""
        ps = self.per_serving
        return ps / self.protein * 25 if ps and self.protein else None

    @property
    def per_kg(self) -> float | None:
        return self.price / self.kilos if self.price and self.kilos else None


def _both(text: str) -> str:
    t = nlu.normalize(text)
    return f"{t} {t.translate(nlu.LATIN_FROM_CYR)} "


def subtype_in(text: str) -> str | None:
    both = _both(text)
    return next((k for k, (_c, _n, stems) in SUBTYPES.items() if nlu._has(both, stems)), None)


def kind_of(text: str, concept: str | None) -> tuple[str | None, str | None]:
    """(concept, sub-kind) the shopper asked for: "gidrolizat" alone is a protein, "kreatin monogidrat" a creatine."""
    sub = subtype_in(text)
    if sub:
        parent = SUBTYPES[sub][0]
        if concept in (None, parent):
            return parent, sub
        return concept, None  # "kreatin, vegan" -- the sub-kind belongs to another product kind
    return concept, None


def category_id(concept: str | None, sub: str | None = None):
    """The live category for a kind (by its English name; the Uzbek / Russian name works as a fallback)."""
    from apps.products.infrastructure import models as orm

    name = SUBTYPES[sub][1] if sub else KIND_CATEGORY.get(concept or "")
    if not name:
        return None
    qs = orm.CategoryTranslation.objects.filter(name__iexact=name, category__deleted_at__isnull=True)
    return qs.filter(locale_code="en").values_list("category_id", flat=True).first() or qs.values_list("category_id", flat=True).first()


def kind_search(concept: str | None, loc: str, *, sub: str | None = None, limit: int = 4, in_stock: bool = True, max_price: int | None = None,
                fallback_query: str | None = None) -> list[dict]:
    """Products of exactly this kind (its category subtree). Only when the tree has no such section does it fall back to
    the text search -- and then keeps rows whose category still says the kind."""
    from apps.assistant.infrastructure import tools
    from apps.assistant.infrastructure.advisor import reco

    args = {"limit": limit, "in_stock_only": in_stock, **({"max_price": max_price} if max_price else {})}
    if sub and (cat := category_id(concept, sub)):
        found = tools.search_products({**args, "category_id": str(cat)}, loc)["products"]
        if found:
            return found
    if cat := category_id(concept):  # no such sub-section (or it's empty): the whole kind, never another kind
        return tools.search_products({**args, "category_id": str(cat)}, loc)["products"]
    q = fallback_query or reco.QUERIES.get(concept or "", concept or "")
    return tools.search_products({**args, "query": q}, loc)["products"] if q else []


# ---------------------------------------------------------------------------------------------------- scoring


def brand_tier(brand: str, name: str = "") -> int:
    hay = f"{brand} {name}".lower()
    for tier in (3, 2):
        if any(b in hay for b in BRAND_TIER[tier]):
            return tier
    return 1


_SIZE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g|lb|lbs|кг|г)\b", re.I)


def _kilos(size: str) -> float | None:
    m = _SIZE.search(size or "")
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    unit = m.group(2).lower()
    return v if unit in ("kg", "кг") else v / 1000 if unit in ("g", "г") else v * 0.4536


def rows_for(ids: list[str], loc: str, max_price: int | None = None) -> list[Row]:
    """Comparable rows for products: name, brand, price, rating and the card's numbers. With a budget, each product is
    priced at its biggest in-stock size that fits it (servings scaled to that size)."""
    from apps.assistant.infrastructure import tools
    from apps.assistant.infrastructure.advisor import catalog

    out = []
    for pid in ids:
        try:
            d = tools.get_product_details({"product_id": pid}, loc)
        except tools.ToolError:
            continue
        price = float(d.get("price_uzs") or 0)
        if not price:
            continue
        old = float(d.get("old_price_uzs") or 0)
        nutrition = d.get("nutrition") or {}
        facts = d.get("supplement_facts") if isinstance(d.get("supplement_facts"), str) else ""
        variants = d.get("variants") or []
        base = next((v for v in variants if v.get("price_uzs") and float(v["price_uzs"]) == price), variants[0] if variants else {})
        sold, name, scale = base, d.get("name") or "", 1.0
        if max_price and price > max_price:
            fits = [v for v in variants if v.get("in_stock") and v.get("price_uzs") and float(v["price_uzs"]) <= max_price]
            if fits:
                sold = max(fits, key=lambda v: float(v["price_uzs"]))
                price, old = float(sold["price_uzs"]), 0
                bk, sk = _kilos(base.get("size") or ""), _kilos(sold.get("size") or "")
                scale = sk / bk if bk and sk else 0
                name = f"{name} {sold.get('size')}".strip() if sold.get("size") else name
        servings = _f(nutrition.get("servings_per_container"))
        servings = round(servings * scale) if servings and scale else None
        r = Row(id=str(pid), name=name, brand=d.get("brand") or "", price=price, old_price=old if old > price else 0,
                discount=int(round((old - price) / old * 100)) if old > price else 0, rating=float(d.get("rating") or 0), reviews=int(d.get("reviews") or 0),
                in_stock=any(v.get("in_stock") for v in variants) if variants else True, protein=catalog._protein_grams(facts),
                servings=servings, serving_g=_f(nutrition.get("serving_size_grams")), kilos=_kilos(sold.get("size") or ""))
        r.tier = brand_tier(r.brand, r.name)
        out.append(r)
    return out


def _f(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x > 0 else None


def rank(rows: list[Row], concept: str | None) -> list[Row]:
    """Value (cheapest 25 g protein / serving / kilo of the group = 1.0) 50 %, brand standing 35 %, buyers' rating 10 %,
    a live discount 5 %. Out-of-stock rows go last."""
    if not rows:
        return rows
    metric = (lambda r: r.per_25g or None) if concept in PROTEIN_KINDS else (lambda r: r.per_serving)
    vals = [metric(r) for r in rows]
    if sum(1 for v in vals if v) < 2:  # the cards lack nutrition numbers: compare price per kilo, else plain price
        metric = (lambda r: r.per_kg) if sum(1 for r in rows if r.per_kg) >= 2 else (lambda r: r.price)
        vals = [metric(r) for r in rows]
    best = min((v for v in vals if v), default=None)
    for r, v in zip(rows, vals, strict=True):
        value = best / v if best and v else 0.5
        rating = (r.rating / 5) if r.reviews else 0.6
        r.score = 0.5 * value + 0.35 * (r.tier / 3) + 0.1 * rating + 0.05 * min(r.discount, 30) / 30
        r.flags = []
        if best and v == best:
            r.flags.append("value")
    top_tier = max(r.tier for r in rows)
    for r in rows:
        if r.tier == top_tier and top_tier >= 2:
            r.flags.append("brand")
    return sorted(rows, key=lambda r: (r.in_stock, r.score), reverse=True)


# ---------------------------------------------------------------------------------------------------- text


def _l(loc: str, uz: str, ru: str, en: str) -> str:
    return {"uz": uz, "ru": ru, "en": en}[loc]


def money(v) -> str:
    return f"{int(round(float(v or 0))):,}".replace(",", " ")


CUR = {"uz": "so'm", "ru": "сум", "en": "UZS"}


def _numbers(r: Row, loc: str) -> str:
    bits = []
    if r.protein and r.servings:
        bits.append(_l(loc, f"{r.protein:g} g oqsil × {r.servings:g} porsiya", f"{r.protein:g} г белка × {r.servings:g} порций", f"{r.protein:g} g protein × {r.servings:g} servings"))
    elif r.servings:
        bits.append(_l(loc, f"{r.servings:g} porsiya", f"{r.servings:g} порций", f"{r.servings:g} servings"))
    if r.per_25g:
        bits.append(_l(loc, f"25 g oqsil ≈ {money(r.per_25g)} so'm", f"25 г белка ≈ {money(r.per_25g)} сум", f"25 g protein ≈ {money(r.per_25g)} UZS"))
    elif r.per_serving:
        bits.append(_l(loc, f"porsiyasi ≈ {money(r.per_serving)} so'm", f"порция ≈ {money(r.per_serving)} сум", f"≈ {money(r.per_serving)} UZS a serving"))
    elif r.per_kg:
        bits.append(_l(loc, f"1 kg ≈ {money(r.per_kg)} so'm", f"1 кг ≈ {money(r.per_kg)} сум", f"≈ {money(r.per_kg)} UZS per kg"))
    return " · ".join(bits)


def _line(i: int, r: Row, loc: str) -> str:
    old = f" ~~{money(r.old_price)}~~ (−{r.discount}%)" if r.old_price else ""
    stock = "" if r.in_stock else _l(loc, " · tugagan", " · нет в наличии", " · out of stock")
    nums = _numbers(r, loc)
    return f"{i}. **{r.name}** — {money(r.price)} {CUR[loc]}{old}{stock}" + (f"\n   _{nums}_" if nums else "")


def _reasons(r: Row, loc: str, sub: str | None) -> str:
    out = []
    if r.tier == 3:
        out.append(_l(loc, "dunyodagi eng taniqli, mustaqil laboratoriyada ko'p tekshiriladigan brendlardan", "один из самых известных брендов, часто проверяется независимыми лабораториями",
                      "one of the best-known brands, regularly third-party tested"))
    elif r.tier == 2:
        out.append(_l(loc, "ishonchli xalqaro brend", "надёжный международный бренд", "an established international brand"))
    if "value" in r.flags:
        out.append(_l(loc, "guruhdagi eng tejamkor narx (oqsil grammi hisobida)" if r.per_25g else "guruhdagi eng tejamkor narx", "самая выгодная цена в группе (за грамм белка)" if r.per_25g else "самая выгодная цена в группе",
                      "the best value of the group (per gram of protein)" if r.per_25g else "the best value of the group"))
    if r.protein and r.serving_g and r.protein / r.serving_g >= 0.8:
        out.append(_l(loc, f"porsiyada oqsil ulushi yuqori ({round(r.protein / r.serving_g * 100)}%)", f"высокая доля белка в порции ({round(r.protein / r.serving_g * 100)}%)",
                      f"high protein share per scoop ({round(r.protein / r.serving_g * 100)}%)"))
    if sub in ("isolate", "hydro"):
        out.append(_l(loc, "laktoza deyarli yo'q, tez hazm bo'ladi", "почти без лактозы, быстро усваивается", "almost lactose-free, digests fast"))
    if r.reviews and r.rating >= 4.5:
        out.append(_l(loc, f"xaridorlar bahosi {r.rating:.1f}★", f"оценка покупателей {r.rating:.1f}★", f"buyers rate it {r.rating:.1f}★"))
    if r.discount >= 5:
        out.append(_l(loc, f"hozir −{r.discount}% chegirmada", f"сейчас со скидкой −{r.discount}%", f"−{r.discount}% off right now"))
    return "; ".join(out) or _l(loc, "narx va sifat muvozanati eng yaxshi", "лучший баланс цены и качества", "the best balance of price and quality")


def verdict(rows: list[Row], loc: str, sub: str | None = None) -> str:
    """🏆 my pick + 💸 best value + ⭐ most trusted brand (each only when it's a different product)."""
    if not rows:
        return ""
    pick = rows[0]
    out = [_l(loc, f"🏆 **Mening tanlovim: {pick.name}** — {_reasons(pick, loc, sub)}.", f"🏆 **Мой выбор: {pick.name}** — {_reasons(pick, loc, sub)}.",
              f"🏆 **My pick: {pick.name}** — {_reasons(pick, loc, sub)}.")]
    value = next((r for r in rows if "value" in r.flags and r.in_stock), None)
    if value and value is not pick:
        how = _numbers(value, loc).split(" · ")[-1]
        out.append(_l(loc, f"💸 **Eng tejamkori: {value.name}**" + (f" — {how}" if how else "") + ".", f"💸 **Самый выгодный: {value.name}**" + (f" — {how}" if how else "") + ".",
                      f"💸 **Best value: {value.name}**" + (f" — {how}" if how else "") + "."))
    trusted = max((r for r in rows if r.in_stock), key=lambda r: (r.tier, r.rating, -r.price), default=None)
    if trusted and trusted not in (pick, value) and trusted.tier > pick.tier:
        out.append(_l(loc, f"⭐ **Brend ishonchliligi bo'yicha: {trusted.name}**.", f"⭐ **Самый надёжный бренд: {trusted.name}**.", f"⭐ **Most trusted brand: {trusted.name}**."))
    return "\n".join(out)


HOW_COMPARE = {
    "protein": {"uz": "💡 Proteinni tub narxi bilan emas, **25 g oqsil narxi** bilan solishtiring: narx ÷ porsiyalar soni ÷ porsiyadagi oqsil × 25. Qorin sezgir yoki laktoza ko'tarmasa — izolyat yoki gidrolizat; kechga — kazein; sut umuman mumkin bo'lmasa — vegan yoki mol go'shti proteini.",
                "ru": "💡 Сравнивайте протеин не по цене банки, а по **цене 25 г белка**: цена ÷ число порций ÷ белок в порции × 25. Чувствительный желудок или лактоза — изолят или гидролизат; на ночь — казеин; если молочное нельзя совсем — веганский или говяжий протеин.",
                "en": "💡 Compare protein by the **price of 25 g of protein**, not the tub price: price ÷ servings ÷ protein per serving × 25. Sensitive stomach or lactose — isolate or hydrolysate; at night — casein; no dairy at all — vegan or beef protein."},
    "creatine": {"uz": "💡 Kreatinda brend emas, shakl muhim: **monogidrat** eng ko'p o'rganilgan va eng arzon (kuniga 3–5 g). HCl qorin sezgir bo'lsa qulay, lekin samarasi monogidratdan ortiq emas. Solishtirish: narx ÷ porsiyalar = 1 kunlik narx.",
                 "ru": "💡 У креатина важен не бренд, а форма: **моногидрат** самый изученный и самый дешёвый (3–5 г в день). HCl удобен при чувствительном желудке, но эффективнее моногидрата не доказан. Сравнение: цена ÷ порции = цена дня.",
                 "en": "💡 With creatine the form matters more than the brand: **monohydrate** is the most studied and cheapest (3–5 g a day). HCl suits a sensitive stomach but isn't proven better. Compare: price ÷ servings = cost per day."},
    "gainer": {"uz": "💡 Geynerni porsiyadagi kaloriya va oqsil ulushi bilan tanlang: 1 porsiyada kamida 25–30% kaloriya oqsildan bo'lsin. Tez semiradiganlarga — kam shakarli \"lean gainer\" yoki oddiy protein.",
               "ru": "💡 Гейнер выбирайте по калориям и доле белка в порции: не меньше 25–30% калорий из белка. Если легко набираете жир — «lean gainer» или обычный протеин.",
               "en": "💡 Pick a gainer by calories and protein share per serving: at least 25–30% of calories from protein. If you gain fat easily — a lean gainer or plain protein."},
}


def budget_answer(concept: str, sub: str | None, budget: int | None, loc: str, *, cheap: bool = False) -> tuple[str, list[str]] | None:
    """"500 minggacha protein", "eng arzon izolyat", "лучший креатин до 300 тысяч" -- ranked, with numbers and a verdict."""
    from apps.assistant.infrastructure.advisor import kb

    found = kind_search(concept, loc, sub=sub, limit=8, max_price=budget)
    over = False
    if not found and budget:
        found = sorted(kind_search(concept, loc, sub=sub, limit=8), key=lambda x: float(x.get("price_uzs") or 0))[:3]
        over = bool(found)
    if not found:
        return None
    rows = rank(rows_for([x["id"] for x in found], loc, None if over else budget), concept)
    if cheap:  # "eng arzon" -- by the real cost of what you get, not by tub price
        rows.sort(key=lambda r: (not r.in_stock, r.per_25g or r.per_serving or r.per_kg or r.price))
    rows = rows[:5]
    if not rows:
        return None
    kind = kb.T["kind_name"][loc].get(concept, concept)
    sub_name = {"hydro": ("Gidrolizat", "Гидролизат", "Hydrolysate"), "isolate": ("Izolyat", "Изолят", "Isolate"), "casein": ("Kazein", "Казеин", "Casein"),
                "beef": ("Mol go'shti proteini", "Говяжий протеин", "Beef protein"), "vegan": ("Vegan protein", "Веганский протеин", "Vegan protein"),
                "concentrate": ("Whey konsentrat", "Сывороточный концентрат", "Whey concentrate"), "mono": ("Kreatin monogidrat", "Креатин моногидрат", "Creatine monohydrate"),
                "hcl": ("Kreatin HCl", "Креатин HCl", "Creatine HCl")}.get(sub or "")
    title = _l(loc, *sub_name) if sub_name else kind
    if over:
        head = _l(loc, f"**{title}** — {money(budget)} so'mgacha hozir yo'q. Eng yaqin variantlar:", f"**{title}** — до {money(budget)} сум сейчас нет. Ближайшие варианты:",
                  f"**{title}** — nothing up to {money(budget)} UZS right now. The closest options:")
    elif budget:
        head = _l(loc, f"**{title} — {money(budget)} so'mgacha, solishtirib chiqdim:**", f"**{title} до {money(budget)} сум — сравнил для вас:**",
                  f"**{title} up to {money(budget)} UZS — compared for you:**")
    elif cheap:
        head = _l(loc, f"**{title} — haqiqiy narxi bo'yicha eng tejamkorlari:**", f"**{title} — самые выгодные по реальной цене:**", f"**{title} — the best value by real cost:**")
    else:
        head = _l(loc, f"**{title} — ombordagi eng yaxshilari, solishtirib:**", f"**{title} — лучшее в наличии, со сравнением:**", f"**{title} — the best in stock, compared:**")
    body = "\n".join(_line(i, r, loc) for i, r in enumerate(rows, 1))
    tip = HOW_COMPARE.get(concept, {}).get(loc, "")
    text = f"{head}\n{body}\n\n{verdict(rows, loc, sub)}" + (f"\n\n{tip}" if tip else "")
    return text, [r.id for r in rows]


def wants_which(text: str) -> bool:
    return nlu._has(_both(text), WHICH_BETTER)


def compare_shown(ids: list[str], concept: str | None, loc: str, sub: str | None = None) -> tuple[str, list[str]] | None:
    """"Qaysi biri yaxshi?" after a list: the same products, scored, with the reasons."""
    rows = rank(rows_for(ids[:6], loc), concept)
    if len(rows) < 2:
        return None
    head = _l(loc, "**Ko'rsatganlarimni solishtirdim:**", "**Сравнил то, что показал:**", "**I compared what I showed you:**")
    body = "\n".join(_line(i, r, loc) for i, r in enumerate(rows, 1))
    tail = _l(loc, "Maqsadingiz (massa, ozish, kechki qabul) yoki sut ko'tarmasligingizni yozsangiz, tanlovni aniqroq qilaman.",
              "Напишите цель (масса, похудение, приём на ночь) или если не переносите молочное — уточню выбор.",
              "Tell me your goal (mass, fat loss, night-time) or if dairy upsets you and I'll fine-tune the pick.")
    return f"{head}\n{body}\n\n{verdict(rows, loc, sub)}\n\n{tail}", [r.id for r in rows]


# ---------------------------------------------------------------------------------------------------- milk / lactose


def dairy_issue(text: str) -> str | None:
    """"allergy" (milk protein), "lactose" (intolerance / dislike) or None."""
    both = _both(text)
    if not nlu._has(both, DAIRY):
        return None
    if nlu._has(both, ALLERGY):
        return "allergy"
    if nlu._has(both, DAIRY_BAD) or nlu._has(both, ("laktoza", "лактоз", "lactose")):
        return "lactose"
    return None


def dairy_answer(issue: str, loc: str) -> tuple[str, list[str]]:
    if issue == "allergy":
        text = _l(loc,
                  "**Sut oqsiliga allergiya — bu laktoza emas.** Allergiyada organizm sut oqsillari (kazein, zardob)ga qarshi reaksiya beradi, shuning uchun "
                  "**har qanday whey — konsentrat, izolyat va gidrolizat ham — mumkin emas**, kazein ham.\n\n"
                  "✅ Mos variantlar:\n• **Vegan protein** (no'xat, guruch, soya aralashmasi) — to'liq aminokislota tarkibi aralashmada bo'ladi.\n"
                  "• **Mol go'shti proteini (beef)** — sutsiz, kreatin va kollagenga boy.\n• Kreatin, BCAA/EAA, vitaminlar — sutsiz, bemalol.\n\n"
                  "⚠️ Yorliqdagi \"contains milk\" / \"may contain milk\" yozuviga albatta qarang (bir zavodda ishlab chiqarilishi mumkin). Kuchli allergiyada shifokor bilan maslahatlashing.",
                  "**Аллергия на белок молока — это не лактоза.** При аллергии организм реагирует на сами молочные белки (казеин, сыворотку), поэтому "
                  "**любой whey — концентрат, изолят и даже гидролизат — нельзя**, казеин тоже.\n\n"
                  "✅ Подойдут:\n• **Веганский протеин** (горох, рис, соя — смесь даёт полный аминокислотный профиль).\n"
                  "• **Говяжий протеин (beef)** — без молока, богат креатином и коллагеном.\n• Креатин, BCAA/EAA, витамины — без молока.\n\n"
                  "⚠️ Смотрите на этикетке «contains milk» / «may contain milk» (общее производство). При сильной аллергии посоветуйтесь с врачом.",
                  "**A milk-protein allergy is not lactose intolerance.** The body reacts to the milk proteins themselves (casein, whey), so "
                  "**any whey — concentrate, isolate, even hydrolysate — is out**, and casein too.\n\n"
                  "✅ Good options:\n• **Vegan protein** (pea, rice, soy — a blend gives a complete amino profile).\n"
                  "• **Beef protein** — dairy-free, rich in creatine and collagen.\n• Creatine, BCAA/EAA, vitamins — dairy-free.\n\n"
                  "⚠️ Check the label for \"contains milk\" / \"may contain milk\" (shared facilities). With a strong allergy, talk to a doctor.")
        subs = ("vegan", "beef")
    else:
        text = _l(loc,
                  "**Sut yoki laktoza ko'tarmasangiz — protein ichsa bo'ladi, faqat to'g'ri turini tanlang.** Qorin shishishi, og'irlik odatda **laktoza** (sut shakari)dan bo'ladi:\n\n"
                  "• **Whey konsentrat** — porsiyada 1–3 g laktoza: sezgir odamda noqulaylik berishi mumkin.\n"
                  "• **Izolyat** — laktoza <0,5–1 g, ko'pchilik bemalol ko'taradi. ✅\n"
                  "• **Gidrolizat** — oqsil oldindan parchalangan, eng yengil hazm bo'ladi. ✅\n"
                  "• Sut umuman ichmasangiz — **vegan** yoki **mol go'shti proteini**.\n\n"
                  "💡 Maslahat: **suv bilan** aralashtiring (sut emas), kichik porsiyadan boshlang (½ qoshiq), shakarsiz/laktazali mahsulot tanlang. "
                  "Agar toshma, qichishish, nafas qisishi bo'lsa — bu allergiya, whey umuman mumkin emas.",
                  "**Не переносите молоко или лактозу — протеин можно, просто выберите правильный вид.** Вздутие и тяжесть обычно из-за **лактозы** (молочного сахара):\n\n"
                  "• **Сывороточный концентрат** — 1–3 г лактозы в порции: у чувствительных может вызывать дискомфорт.\n"
                  "• **Изолят** — лактозы <0,5–1 г, большинство переносит спокойно. ✅\n"
                  "• **Гидролизат** — белок уже расщеплён, усваивается легче всего. ✅\n"
                  "• Если молочное совсем не пьёте — **веганский** или **говяжий протеин**.\n\n"
                  "💡 Совет: смешивайте **с водой** (не с молоком), начните с половины мерной ложки. "
                  "Если сыпь, зуд или одышка — это аллергия, тогда whey нельзя совсем.",
                  "**Dairy or lactose upsets you — you can still take protein, just pick the right type.** Bloating and heaviness usually come from **lactose** (milk sugar):\n\n"
                  "• **Whey concentrate** — 1–3 g lactose a serving: may bother sensitive people.\n"
                  "• **Isolate** — under 0.5–1 g lactose, most people tolerate it well. ✅\n"
                  "• **Hydrolysate** — protein already broken down, the easiest to digest. ✅\n"
                  "• No dairy at all — **vegan** or **beef protein**.\n\n"
                  "💡 Tip: mix it **with water** (not milk) and start with half a scoop. "
                  "Rash, itching or shortness of breath means an allergy — then no whey at all.")
        subs = ("isolate", "hydro", "vegan")
    ids: list[str] = []
    for s in subs:
        cat = category_id("protein", s)
        if not cat:
            continue
        from apps.assistant.infrastructure import tools

        for x in tools.search_products({"limit": 2, "in_stock_only": True, "category_id": str(cat)}, loc)["products"]:
            if x["id"] not in ids:
                ids.append(x["id"])
    if ids:
        text += "\n\n" + _l(loc, "Ombordagi mos variantlar:", "Подходящие варианты в наличии:", "Suitable options in stock:")
    return text, ids[:4]
