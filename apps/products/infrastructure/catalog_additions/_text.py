"""
Builds a catalogue product's uz/ru/en texts in the house format of the existing catalogue (intro, "Asosiy afzalliklari",
"Bir porsiyada ...", "Qanday qabul qilinadi", brand line) from short per-language pieces, so a dataset states facts
once. Numbers are written with a dot and localised here (4.5 g -> 4,5 g / 4,5 г).
"""
from __future__ import annotations

import re

LOCALES = ("uz", "ru", "en")

LABELS = {
    "kcal": ("Energiya qiymati", "Энергетическая ценность", "Energy"),
    "protein": ("Oqsil", "Белки", "Protein"),
    "carbs": ("Uglevodlar", "Углеводы", "Carbohydrates"),
    "sugar": ("Shakar", "Сахар", "Sugar"),
    "fat": ("Yog‘lar", "Жиры", "Fat"),
    "fibre": ("Kletchatka", "Клетчатка", "Fibre"),
    "bcaa": ("BCAA", "BCAA", "BCAA"),
    "leucine": ("L-leysin", "L-лейцин", "L-leucine"),
    "isoleucine": ("L-izoleysin", "L-изолейцин", "L-isoleucine"),
    "valine": ("L-valin", "L-валин", "L-valine"),
    "glutamine": ("L-glutamin", "L-глютамин", "L-glutamine"),
    "creatine": ("Kreatin monogidrat", "Креатин моногидрат", "Creatine monohydrate"),
    "creatine_hcl": ("Kreatin gidroxlorid", "Креатина гидрохлорид", "Creatine hydrochloride"),
    "citrulline_dlm": ("L-sitrullin DL-malat", "L-цитруллин DL-малат", "L-citrulline DL-malate"),
    "beta_alanine": ("Beta-alanin", "Бета-аланин", "Beta-alanine"),
    "aakg": ("L-arginin AKG (AAKG)", "L-аргинин AKG (AAKG)", "L-arginine AKG (AAKG)"),
    "glycerol": ("Glitserol", "Глицерол", "Glycerol"),
    "caffeine": ("Kofein", "Кофеин", "Caffeine"),
    "b3": ("Vitamin B3 (niatsinamid)", "Витамин B3 (никотинамид)", "Vitamin B3 (niacinamide)"),
    "piperine": ("Qora qalampir ekstrakti (piperin)", "Экстракт чёрного перца (пиперин)", "Black pepper extract (piperine)"),
    "chlorophyll": ("Xlorofill", "Хлорофилл", "Chlorophyll"),
    "copper": ("Mis", "Медь", "Copper"),
    "omega3": ("Omega-3 yog‘ kislotalari", "Омега-3 жирные кислоты", "Omega-3 fatty acids"),
    "epa": ("EPK (EPA)", "ЭПК (EPA)", "EPA"),
    "dha": ("DGK (DHA)", "ДГК (DHA)", "DHA"),
    "fish_oil": ("Baliq yog‘i", "Рыбий жир", "Fish oil"),
    "q10": ("Koenzim Q10 (ubixinon)", "Коэнзим Q10 (убихинон)", "Coenzyme Q10 (ubiquinone)"),
    "digezyme": ("DigeZyme® ferment kompleksi", "Ферментный комплекс DigeZyme®", "DigeZyme® enzyme complex"),
    "electrolytes": ("Elektrolitlar", "Электролиты", "Electrolytes"),
    "amylase": ("α-amilaza", "α-амилаза", "α-amylase"),
    "protease": ("Proteaza", "Протеаза", "Protease"),
    "lactase": ("Laktaza", "Лактаза", "Lactase"),
    "lipase": ("Lipaza", "Липаза", "Lipase"),
    "cellulase": ("Tsellyulaza", "Целлюлаза", "Cellulase"),
    "zinc": ("Rux (elementar)", "Цинк (элементарный)", "Zinc (elemental)"),
    "vit_a": ("Vitamin A", "Витамин A", "Vitamin A"),
    "vit_c": ("Vitamin C", "Витамин C", "Vitamin C"),
    "vit_d": ("Vitamin D3", "Витамин D3", "Vitamin D3"),
    "vit_e": ("Vitamin E", "Витамин E", "Vitamin E"),
    "vit_k2": ("Vitamin K2", "Витамин K2", "Vitamin K2"),
    "vit_b1": ("Vitamin B1 (tiamin)", "Витамин B1 (тиамин)", "Vitamin B1 (thiamine)"),
    "vit_b2": ("Vitamin B2 (riboflavin)", "Витамин B2 (рибофлавин)", "Vitamin B2 (riboflavin)"),
    "niacin": ("Niatsin", "Ниацин", "Niacin"),
    "vit_b12": ("Vitamin B12", "Витамин B12", "Vitamin B12"),
    "folic": ("Foliy kislotasi", "Фолиевая кислота", "Folic acid"),
    "iron": ("Temir", "Железо", "Iron"),
    "calcium": ("Kalsiy", "Кальций", "Calcium"),
    "magnesium": ("Magniy", "Магний", "Magnesium"),
    "iodine": ("Yod", "Йод", "Iodine"),
    "chromium": ("Xrom (pikolinat)", "Хром (пиколинат)", "Chromium (picolinate)"),
    "yohimbine": ("Yohimbin", "Йохимбин", "Yohimbine"),
    "rauwolscine": ("Rauvolstsin (alfa-yohimbin)", "Раувольсцин (альфа-йохимбин)", "Rauwolscine (alpha-yohimbine)"),
    "tudca": ("TUDCA (taurursodeoksixol kislotasi)", "TUDCA (тауроурсодезоксихолевая кислота)", "TUDCA (tauroursodeoxycholic acid)"),
    "choline": ("Xolin", "Холин", "Choline"),
    "nac": ("N-atsetil-L-sistein (NAC)", "N-ацетил-L-цистеин (NAC)", "N-acetyl-L-cysteine (NAC)"),
    "tribulus": ("Tribulus terrestris ekstrakti (90% saponinlar)", "Экстракт трибулуса (90% сапонинов)", "Tribulus terrestris extract (90% saponins)"),
    "collagen": ("Gidrolizlangan kollagen", "Гидролизованный коллаген", "Hydrolysed collagen"),
    "biotin": ("Biotin", "Биотин", "Biotin"),
    "glutathione": ("L-glutation (qaytarilgan)", "L-глутатион (восстановленный)", "L-glutathione (reduced)"),
    "myo": ("Mio-inozitol", "Мио-инозитол", "Myo-inositol"),
    "dchiro": ("D-xiro-inozitol", "D-хиро-инозитол", "D-chiro-inositol"),
    "curcumin": ("Kurkuma ekstrakti (95% kurkuminoidlar)", "Экстракт куркумы (95% куркуминоидов)", "Turmeric extract (95% curcuminoids)"),
}

UNITS = {  # unit -> (uz, ru, en)
    "kg": ("kg", "кг", "kg"), "g": ("g", "г", "g"), "mg": ("mg", "мг", "mg"), "µg": ("mkg", "мкг", "µg"),
    "kcal": ("kkal", "ккал", "kcal"), "ml": ("ml", "мл", "ml"), "l": ("l", "л", "l"), "IU": ("XB", "МЕ", "IU"),
    "DU": ("DU", "DU", "DU"), "PC": ("PC", "PC", "PC"), "ALU": ("ALU", "ALU", "ALU"), "FIP": ("FIP", "FIP", "FIP"), "CU": ("CU", "CU", "CU"),
}
_IDX = {"uz": 0, "ru": 1, "en": 2}

HEAD = {"uz": "Asosiy afzalliklari:", "ru": "Ключевые преимущества:", "en": "Key benefits:"}
PER = {"uz": "Bir porsiyada ({s}): {f}.", "ru": "В одной порции ({s}): {f}.", "en": "In one serving ({s}): {f}."}
PACK = {"uz": " Qadoq {n} porsiyaga yetadi.", "ru": " Упаковки хватает на {n} порций.", "en": " The pack provides {n} servings."}
HOW = {"uz": "Qanday qabul qilinadi: ", "ru": "Как принимать: ", "en": "How to take: "}
USE = {"uz": "Qanday foydalaniladi: ", "ru": "Как использовать: ", "en": "How to use: "}
FACTS_HEAD = {"uz": "1 porsiya ({s}) uchun:", "ru": "На 1 порцию ({s}):", "en": "Per serving ({s}):"}
FACTS_PACK = {"uz": "Qadoqdagi porsiyalar soni — {n}", "ru": "Порций в упаковке — {n}", "en": "Servings per container — {n}"}
INGR = {"uz": "Tarkibi: ", "ru": "Состав: ", "en": "Ingredients: "}

COUNTRY = {  # brand line country, per language
    "RU": ("Rossiya", "Россия", "Russia"), "PL": ("Polsha", "Польша", "Poland"), "CA": ("Kanada", "Канада", "Canada"),
    "GB": ("Buyuk Britaniya", "Великобритания", "United Kingdom"), "US": ("AQSH", "США", "USA"), "IT": ("Italiya", "Италия", "Italy"),
}
BRAND_LINE = {"uz": "Brend — {b} ({c}). Mahsulot original, rasmiy yetkazib beruvchidan.",
              "ru": "Бренд — {b} ({c}). Оригинальная продукция от официального поставщика.",
              "en": "Brand — {b} ({c}). Original product from an official supplier."}
BRAND_LINE_NC = {"uz": "Brend — {b}. Mahsulot original, rasmiy yetkazib beruvchidan.",
                 "ru": "Бренд — {b}. Оригинальная продукция от официального поставщика.",
                 "en": "Brand — {b}. Original product from an official supplier."}


def amount(value: str, lang: str) -> str:
    """'4.5 g' -> '4,5 g' (uz) / '4,5 г' (ru); '3600 DU' kept; a value without a known unit is returned as is."""
    m = re.fullmatch(r"([\d.,–\-\s]+)\s*([^\d\s].*)?", value.strip())
    if not m:
        return value
    num, unit = m.group(1).strip(), (m.group(2) or "").strip()
    if lang in ("uz", "ru"):
        num = num.replace(".", ",")
    if unit in UNITS:
        unit = UNITS[unit][_IDX[lang]]
    return f"{num} {unit}".strip()


def _fact(key, value, lang):
    label = LABELS[key][_IDX[lang]] if key in LABELS else key
    return f"{label} — {amount(value, lang)}"


def describe(lang, *, intro, benefits=(), serving=None, facts=(), servings=None, how=None, use=None, brand=None, country=None, extra=None):
    parts = [intro[lang]]
    if benefits:
        parts.append(HEAD[lang] + "\n" + "\n".join(f"• {b}" for b in benefits[lang]))
    if serving and facts:
        line = PER[lang].format(s=serving[lang], f="; ".join(_fact(k, v, lang) for k, v in facts))
        parts.append(line + (PACK[lang].format(n=servings) if servings else ""))
    if extra:
        parts.append(extra[lang])
    if how:
        parts.append(HOW[lang] + how[lang])
    if use:
        parts.append(USE[lang] + use[lang])
    if brand:
        c = COUNTRY.get(country or "")
        parts.append((BRAND_LINE if c else BRAND_LINE_NC)[lang].format(b=brand, c=c[_IDX[lang]] if c else ""))
    return "\n\n".join(parts)


def facts_text(lang, *, serving, facts, servings=None, ingredients=None):
    lines = [FACTS_HEAD[lang].format(s=serving[lang])] + [_fact(k, v, lang) for k, v in facts]
    if servings:
        lines.append(FACTS_PACK[lang].format(n=servings))
    if ingredients:
        lines.append(INGR[lang] + ingredients[lang])
    return "\n\n".join(lines)


def product(*, barcode, sku, price, brand, category, package, size, names, intro, brand_name=None, country=None, flavour=None,
            benefits=(), serving=None, facts=(), servings=None, how=None, use=None, ingredients=None, extra=None,
            goals=(), warnings_from=None, warnings=None, serving_g=None, kcal=None, manufacturer=None):
    """One dataset item in the shape import_catalog_additions reads."""
    item = {
        "barcode": barcode, "sku": sku, "price": price, "brand": brand, "category": category, "package": package, "size": size,
        "flavour": flavour, "names": names, "goals": list(goals), "warnings_from": warnings_from, "warnings": warnings,
        "serving_g": serving_g, "servings": servings, "kcal": kcal, "manufacturer": manufacturer or brand,
        "descriptions": {lang: describe(lang, intro=intro, benefits=benefits, serving=serving, facts=facts, servings=servings,
                                        how=how, use=use, brand=brand_name or brand, country=country, extra=extra) for lang in LOCALES},
        "directions": {lang: (how or use)[lang] for lang in LOCALES} if (how or use) else None,
        "facts": {lang: facts_text(lang, serving=serving, facts=facts, servings=servings, ingredients=ingredients) for lang in LOCALES}
        if serving and facts else None,
    }
    return item


def L(uz, ru, en):
    return {"uz": uz, "ru": ru, "en": en}
