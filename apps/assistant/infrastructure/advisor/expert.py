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


_SERVINGS = re.compile(r"(?:porsiyalar soni|porsiya soni|porsiyaga yetadi|servings per container|servings|порций в упаковке|количество порций|порций)\D{0,8}?(\d{1,3})\b"
                       r"|\b(\d{1,3})\s*(?:porsiya(?:ga|dan)?\b(?!\s*\())(?=[^.\n]{0,25}(?:yetadi|qadoq|bor))|qadoq\w*\s+(\d{1,3})\s*porsiya|\b(\d{1,3})\s*(?:servings|порций)\b", re.I)
_SERVING_G = re.compile(r"(?:1\s*porsiya|porsiya|serving size|1 serving|порция|1 порция)\s*(?:\(|[—–:-]\s*|\s)(\d{1,3}(?:[.,]\d)?)\s*(?:g|г|gr)\b", re.I)
_PROTEIN_G = re.compile(r"(?:oqsil|protein|белок|белка)\s*(?:[—–:-]\s*|\s)(\d{1,2}(?:[.,]\d)?)\s*(?:g|г)\b|(\d{1,2}(?:[.,]\d)?)\s*(?:g|г)\s*(?:oqsil|protein|белка|белок)", re.I)
_PROTEIN_PCT = re.compile(r"(\d{2})\s*%\s*(?:oqsil|protein|белка|белок)|(?:oqsil|protein|белок)\w*\s*[—–:-]?\s*~?(\d{2})\s*%", re.I)


def text_numbers(*texts: str) -> dict:
    """Serving size, servings and protein per serving read from the card's own text when the number fields are empty
    ("Porsiya — 30 g", "Qadoqdagi porsiyalar soni — 23", "~80% oqsil")."""
    t = "\n".join(x for x in texts if x)
    out: dict = {}
    if m := _SERVING_G.search(t):
        out["serving_g"] = float(m.group(1).replace(",", "."))
    if m := _SERVINGS.search(t):
        v = next(g for g in m.groups() if g)
        if 5 <= int(v) <= 400:
            out["servings"] = float(v)
    if m := _PROTEIN_G.search(t):
        v = float(next(g for g in m.groups() if g).replace(",", "."))
        if 5 <= v <= 60 and v <= (out.get("serving_g") or 999):
            out["protein"] = v
    if "protein" not in out and out.get("serving_g") and (m := _PROTEIN_PCT.search(t)):
        pct = int(next(g for g in m.groups() if g))
        if 40 <= pct <= 95:
            out["protein"] = round(out["serving_g"] * pct / 100, 1)
    return out


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
        guess = text_numbers(facts, d.get("description") or "", d.get("directions") or "")
        servings = _f(nutrition.get("servings_per_container")) or guess.get("servings")
        servings = round(servings * scale) if servings and scale else None
        r = Row(id=str(pid), name=name, brand=d.get("brand") or "", price=price, old_price=old if old > price else 0,
                discount=int(round((old - price) / old * 100)) if old > price else 0, rating=float(d.get("rating") or 0), reviews=int(d.get("reviews") or 0),
                in_stock=any(v.get("in_stock") for v in variants) if variants else True, protein=catalog._protein_grams(facts) or guess.get("protein"),
                servings=servings, serving_g=_f(nutrition.get("serving_size_grams")) or guess.get("serving_g"), kilos=_kilos(sold.get("size") or ""))
        r.tier = brand_tier(r.brand, r.name)
        out.append(r)
    return out


def _f(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x > 0 else None


SIDE_PROTEIN = re.compile(r"casein|kazein|казеин|quench|hydration|water|suv\b|bar\b|baton|батон|cookie|chips|pancake|crisp", re.I)
TYPICAL_PROTEIN_SHARE = 0.75  # a whey concentrate / blend scoop is ~75 % protein -- used only when the card has no numbers


def _protein_cost(r: Row) -> float | None:
    """So'm per 25 g protein: from the card's numbers, else estimated from the price per kilo."""
    if r.per_25g:
        return r.per_25g
    return r.per_kg / 1000 / TYPICAL_PROTEIN_SHARE * 25 if r.per_kg else None


def rank(rows: list[Row], concept: str | None, sub: str | None = None) -> list[Row]:
    """Value (cheapest 25 g protein / serving / kilo of the group = 1.0) 50 %, brand standing 35 %, buyers' rating 10 %,
    a live discount 5 %. Out-of-stock rows go last."""
    if not rows:
        return rows
    metric = _protein_cost if concept in PROTEIN_KINDS else (lambda r: r.per_serving)
    vals = [metric(r) for r in rows]
    if sum(1 for v in vals if v) < 2:  # the cards lack nutrition numbers: compare price per kilo, else plain price
        metric = (lambda r: r.per_kg) if sum(1 for r in rows if r.per_kg) >= 2 else (lambda r: r.price)
        vals = [metric(r) for r in rows]
    best = min((v for v in vals if v), default=None)
    for r, v in zip(rows, vals, strict=True):
        value = best / v if best and v else 0.5
        rating = (r.rating / 5) if r.reviews else 0.6
        r.score = 0.5 * value + 0.35 * (r.tier / 3) + 0.1 * rating + 0.05 * min(r.discount, 30) / 30
        if concept == "protein" and sub is None and SIDE_PROTEIN.search(r.name):
            r.score -= 0.25  # a general "protein" request means an everyday whey / blend / isolate, not casein or protein water
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
    if r.protein and r.serving_g and not r.servings:
        bits.insert(0, _l(loc, f"porsiyada {r.protein:g} g oqsil", f"{r.protein:g} г белка в порции", f"{r.protein:g} g protein a scoop"))
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
    rows = rank(rows_for([x["id"] for x in found], loc, None if over else budget), concept, sub)
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


def compare_shown(ids: list[str], concept: str | None, loc: str, sub: str | None = None, budget: int | None = None) -> tuple[str, list[str]] | None:
    """"Qaysi biri yaxshi?" after a list: the same products (at the sizes shown within the budget), scored, with the reasons."""
    rows = rank(rows_for(ids[:6], loc, budget), concept, sub)
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


# ---------------------------------------------------------------------------------------------------- personal dosing

FOOD_PROTEIN_G_PER_KG = 1.0  # what an ordinary Uzbek diet already gives -- the shake covers the rest


def personal_usage(concept: str, profile: dict, loc: str) -> str | None:
    """How *this* shopper takes the product: dose from body weight and goal, timing on training and rest days, cautions.
    None when the kind has no personal rule (the generic usage text answers it)."""
    w = float(profile.get("weight") or 0)
    goal = profile.get("goal")
    age = int(profile.get("age") or 0)
    if not w:
        return None
    from apps.assistant.infrastructure.advisor import needs

    lo, hi = needs.PROTEIN_G_PER_KG.get(goal or "health", (1.4, 1.8))
    you = _l(loc, f"Sizga ({w:g} kg", f"Вам ({w:g} кг", f"For you ({w:g} kg") + (
        f", {_l(loc, {'muscle': 'massa', 'weight_loss': 'ozish', 'endurance': 'chidamlilik', 'health': 'salomatlik'}.get(goal, ''), {'muscle': 'набор массы', 'weight_loss': 'похудение', 'endurance': 'выносливость', 'health': 'здоровье'}.get(goal, ''), {'muscle': 'muscle gain', 'weight_loss': 'fat loss', 'endurance': 'endurance', 'health': 'health'}.get(goal, ''))}" if goal else "") + ")"
    if concept == "protein":
        need_lo, need_hi = round(w * lo), round(w * hi)
        gap = max(need_hi - round(w * FOOD_PROTEIN_G_PER_KG), 20)
        scoops = max(1, min(3, round(gap / 25)))
        when = {
            "muscle": _l(loc, "1-porsiya — mashg'ulotdan keyin 30–60 daqiqa ichida; 2-si — nonushta yoki ovqatlar orasida; kechga kazein yoki sut bilan.",
                         "1-я порция — в течение 30–60 мин после тренировки; 2-я — на завтрак или между едой; на ночь — казеин или с молоком.",
                         "1st scoop within 30–60 min after training; 2nd at breakfast or between meals; casein or milk-based at night."),
            "weight_loss": _l(loc, "1 porsiya nonushta o'rniga yoki kechki ovqatdan oldin — to'qlik beradi; suv bilan, shakarsiz. Mashg'ulot kuni — yana 1 porsiya keyin.",
                              "1 порция вместо перекуса или перед ужином — даёт сытость; на воде, без сахара. В день тренировки — ещё 1 порция после.",
                              "1 scoop as a snack or before dinner — keeps you full; with water, no sugar. On training days one more after the session."),
        }.get(goal, _l(loc, "Mashg'ulotdan keyin 1 porsiya; dam olish kunlari — oqsil kam bo'lgan ovqat o'rniga.",
                       "1 порция после тренировки; в дни отдыха — вместо бедного белком приёма пищи.", "1 scoop after training; on rest days — instead of a low-protein meal."))
        return _l(loc,
                  f"🥤 **Protein — shaxsiy tartib.** {you} kuniga **{need_lo}–{need_hi} g oqsil** kerak. Oddiy ovqatdan ~{round(w * FOOD_PROTEIN_G_PER_KG)} g keladi, qolganini kuniga **{scoops} porsiya** (~{scoops * 25} g) protein yopadi.\n"
                  f"⏰ {when}\n💧 250–300 ml suv bilan (massa uchun sut ham bo'ladi). Bir martada 40 g dan ortiq oqsil shart emas.",
                  f"🥤 **Протеин — личная схема.** {you} нужно **{need_lo}–{need_hi} г белка** в день. Из обычной еды ~{round(w * FOOD_PROTEIN_G_PER_KG)} г, остальное закроют **{scoops} порции** (~{scoops * 25} г) протеина.\n"
                  f"⏰ {when}\n💧 На 250–300 мл воды (для массы можно молоко). Больше 40 г белка за раз не нужно.",
                  f"🥤 **Protein — your plan.** {you} you need **{need_lo}–{need_hi} g protein** a day. Ordinary food gives ~{round(w * FOOD_PROTEIN_G_PER_KG)} g; **{scoops} scoop(s)** (~{scoops * 25} g) cover the rest.\n"
                  f"⏰ {when}\n💧 Mix with 250–300 ml water (milk for mass). No need for more than 40 g protein at once.")
    if concept == "creatine":
        if age and age < 18:
            return _l(loc, "⚠️ 18 yoshgacha kreatin tavsiya etilmaydi — avval ovqat, uyqu va protein.", "⚠️ До 18 лет креатин не рекомендуется — сначала питание, сон и белок.",
                      "⚠️ Creatine isn't recommended under 18 — food, sleep and protein first.")
        g = 5 if w >= 80 else 3 if w < 60 else 4
        return _l(loc,
                  f"⚡ **Kreatin — shaxsiy tartib.** {you} — kuniga **{g} g** (≈1 choy qoshiq), **har kuni**, dam olish kunlari ham.\n"
                  f"⏰ Mashg'ulot kuni — mashg'ulotdan keyin protein yoki sharbat bilan; dam olish kuni — nonushta bilan. Vaqtdan ko'ra muntazamlik muhim.\n"
                  f"🚀 Tez natija xohlasangiz: 5–7 kun kuniga {round(w * 0.3)} g (4 marta bo'lib) «yuklama», keyin {g} g. Shart emas — 3–4 haftada natija bir xil.\n"
                  f"💧 Kuniga ~{round(w * 0.04, 1):g} l suv. Tarozida +1–2 kg — mushak ichidagi suv, yog' emas. Buyrak kasalligi bo'lsa — shifokor bilan.",
                  f"⚡ **Креатин — личная схема.** {you} — **{g} г в день** (≈1 чайная ложка), **ежедневно**, и в дни отдыха.\n"
                  f"⏰ В день тренировки — после неё, с протеином или соком; в день отдыха — с завтраком. Регулярность важнее времени.\n"
                  f"🚀 Если хотите быстрее: 5–7 дней по {round(w * 0.3)} г (в 4 приёма) «загрузка», потом {g} г. Не обязательно — через 3–4 недели результат тот же.\n"
                  f"💧 ~{round(w * 0.04, 1):g} л воды в день. +1–2 кг на весах — вода в мышцах, не жир. При болезнях почек — к врачу.",
                  f"⚡ **Creatine — your plan.** {you} — **{g} g a day** (≈1 teaspoon), **every day**, rest days too.\n"
                  f"⏰ Training days — after the session with protein or juice; rest days — with breakfast. Consistency beats timing.\n"
                  f"🚀 Faster saturation: 5–7 days of {round(w * 0.3)} g (split in 4) loading, then {g} g. Optional — same result after 3–4 weeks.\n"
                  f"💧 ~{round(w * 0.04, 1):g} l of water a day. +1–2 kg on the scale is water in muscle, not fat. Kidney disease — ask a doctor.")
    if concept == "gainer":
        half = goal != "muscle" or (profile.get("height") and w / (float(profile["height"]) / 100) ** 2 >= 23)
        return _l(loc,
                  f"🍫 **Geyner — shaxsiy tartib.** {you}: " + ("**½ porsiyadan** boshlang (yog' to'planmasligi uchun), " if half else "kuniga **1 porsiya**, ") +
                  "2 hafta tarozini kuzating: haftasiga +0,25–0,5 kg — ideal; tezroq bo'lsa porsiyani kamaytiring, o'zgarmasa — 2-porsiya qo'shing.\n"
                  "⏰ Mashg'ulotdan keyin yoki ovqatlar orasida (nonushta va tushlik orasi). Ovqat o'rnini bosmaydi.\n💧 300–500 ml suv yoki sut bilan.",
                  f"🍫 **Гейнер — личная схема.** {you}: " + ("начните с **½ порции** (чтобы не набирать жир), " if half else "**1 порция** в день, ") +
                  "2 недели следите за весом: +0,25–0,5 кг в неделю — идеально; быстрее — уменьшите порцию, стоит — добавьте вторую.\n"
                  "⏰ После тренировки или между едой. Еду не заменяет.\n💧 На 300–500 мл воды или молока.",
                  f"🍫 **Gainer — your plan.** {you}: " + ("start with **half a serving** (so you don't gain fat), " if half else "**1 serving** a day, ") +
                  "watch the scale for 2 weeks: +0.25–0.5 kg a week is ideal; faster — cut the serving, no change — add a second.\n"
                  "⏰ After training or between meals. It doesn't replace food.\n💧 With 300–500 ml water or milk.")
    if concept == "preworkout":
        return _l(loc,
                  f"🔥 **Pre-workout — shaxsiy tartib.** {you}: birinchi marta **½ qoshiq** — ko'tarishingizni tekshiring, keyin 1 qoshiq. Mashg'ulotdan **20–30 daqiqa oldin**.\n"
                  "☕ Kofein kuniga 400 mg dan oshmasin (kofe, energetik ham hisob). Soat 16:00 dan keyin ichmang — uyqu buziladi. Haftada 1–2 kun dam bering.\n⚠️ Yurak, bosim muammosi, homiladorlikda — mumkin emas.",
                  f"🔥 **Предтрен — личная схема.** {you}: первый раз **½ мерной ложки** — проверьте переносимость, потом 1. За **20–30 минут до тренировки**.\n"
                  "☕ Кофеина не больше 400 мг в день (учитывайте кофе и энергетики). Не позже 16:00 — испортит сон. 1–2 дня в неделю без него.\n⚠️ При проблемах с сердцем, давлением, беременности — нельзя.",
                  f"🔥 **Pre-workout — your plan.** {you}: first time **half a scoop** to test tolerance, then 1. **20–30 min before** training.\n"
                  "☕ Max 400 mg caffeine a day (count coffee and energy drinks). Not after 4 pm — it ruins sleep. Take 1–2 days a week off.\n⚠️ Not with heart or blood-pressure issues or in pregnancy.")
    if concept == "carnitine":
        return _l(loc, f"🔥 **L-karnitin — shaxsiy tartib.** {you}: kuniga **1–2 g**, kardio yoki mashg'ulotdan **30 daqiqa oldin**. Faqat harakat bilan ishlaydi — o'zi yog' yoqmaydi; kaloriya defitsiti asosiy.",
                  f"🔥 **L-карнитин — личная схема.** {you}: **1–2 г** в день, за **30 минут до** кардио или тренировки. Работает только с нагрузкой — сам жир не сжигает; главное — дефицит калорий.",
                  f"🔥 **L-carnitine — your plan.** {you}: **1–2 g** a day, **30 min before** cardio or training. Works only with exercise — it doesn't burn fat alone; a calorie deficit is what counts.")
    if concept == "bcaa":
        return _l(loc, f"💧 **BCAA/EAA — shaxsiy tartib.** {you}: **5–10 g** mashg'ulot paytida suvga aralashtirib. Kunlik oqsil ({round(w * lo)}+ g) yetarli bo'lsa, BCAA shart emas — protein afzal; och qoringa ertalabki kardioda foydali.",
                  f"💧 **BCAA/EAA — личная схема.** {you}: **5–10 г** во время тренировки в воде. Если белка за день ({round(w * lo)}+ г) хватает, BCAA не обязательны — протеин лучше; полезны на утреннем кардио натощак.",
                  f"💧 **BCAA/EAA — your plan.** {you}: **5–10 g** during training, in water. If daily protein ({round(w * lo)}+ g) is covered, BCAA aren't needed — protein is better; useful for fasted morning cardio.")
    return None


SCHEDULE_SLOT = {  # kind -> (slot, uz, ru, en)
    "vitamin": ("morning", "multivitamin (ovqat bilan)", "мультивитамины (с едой)", "multivitamin (with food)"),
    "omega": ("morning", "Omega-3 1–2 kapsula (ovqat bilan)", "Омега-3 1–2 капсулы (с едой)", "Omega-3, 1–2 capsules (with food)"),
    "vitamin_d": ("morning", "D3 (yog'li ovqat bilan)", "D3 (с жирной едой)", "D3 (with a fatty meal)"),
    "preworkout": ("pre", "pre-workout (20–30 daqiqa oldin)", "предтрен (за 20–30 мин)", "pre-workout (20–30 min before)"),
    "carnitine": ("pre", "L-karnitin 1–2 g (30 daqiqa oldin)", "L-карнитин 1–2 г (за 30 мин)", "L-carnitine 1–2 g (30 min before)"),
    "bcaa": ("during", "BCAA/EAA 5–10 g suvda", "BCAA/EAA 5–10 г в воде", "BCAA/EAA 5–10 g in water"),
    "electrolytes": ("during", "elektrolitlar", "электролиты", "electrolytes"),
    "protein": ("post", "protein 1 porsiya", "протеин 1 порция", "protein, 1 scoop"),
    "creatine": ("post", "kreatin 3–5 g (protein bilan birga)", "креатин 3–5 г (вместе с протеином)", "creatine 3–5 g (with the protein)"),
    "gainer": ("snack", "geyner (ovqatlar orasida)", "гейнер (между едой)", "gainer (between meals)"),
    "collagen": ("evening", "kollagen 10 g (C vitamini bilan)", "коллаген 10 г (с витамином C)", "collagen 10 g (with vitamin C)"),
    "magnesium": ("evening", "magniy (uxlashdan oldin)", "магний (перед сном)", "magnesium (before bed)"),
    "zma": ("evening", "ZMA (uxlashdan 30 daqiqa oldin, och qoringa)", "ZMA (за 30 мин до сна, натощак)", "ZMA (30 min before bed, empty stomach)"),
}
SLOTS = (("morning", "🌅 Ertalab", "🌅 Утро", "🌅 Morning"), ("pre", "🏋️ Mashg'ulotdan oldin", "🏋️ До тренировки", "🏋️ Before training"),
         ("during", "💧 Mashg'ulot paytida", "💧 Во время", "💧 During"), ("post", "✅ Mashg'ulotdan keyin", "✅ После тренировки", "✅ After training"),
         ("snack", "🍽 Ovqatlar orasida", "🍽 Между едой", "🍽 Between meals"), ("evening", "🌙 Kechqurun", "🌙 Вечер", "🌙 Evening"))


def day_schedule(kinds: list[str], loc: str) -> str:
    """📅 one day of the stack: what goes in the morning, around training and at night (rest days: same, minus the pre/during)."""
    idx = {"uz": 1, "ru": 2, "en": 3}[loc]
    by_slot: dict[str, list[str]] = {}
    for k in kinds:
        if k in SCHEDULE_SLOT:
            row = SCHEDULE_SLOT[k]
            by_slot.setdefault(row[0], []).append(row[idx])
    if not by_slot:
        return ""
    lines = [_l(loc, "📅 **Kun tartibi:**", "📅 **Схема дня:**", "📅 **Daily schedule:**")]
    for slot in SLOTS:
        if slot[0] in by_slot:
            lines.append(f"{slot[idx]}: " + ", ".join(by_slot[slot[0]]))
    lines.append(_l(loc, "_Dam olish kunlari: kreatin va vitaminlar — har kuni, protein — ovqat o'rniga; pre-workout kerak emas._",
                    "_В дни отдыха: креатин и витамины — каждый день, протеин — вместо перекуса; предтрен не нужен._",
                    "_Rest days: creatine and vitamins every day, protein as a snack; no pre-workout._"))
    return "\n".join(lines)
