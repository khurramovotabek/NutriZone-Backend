"""
Numbers a product card states only in words -- serving size, servings per container, protein per serving -- read
from its own text when the number fields are empty (most cards: "Porsiya — 30 g", "Qadoqdagi porsiyalar soni — 23",
"~80% oqsil"), and the facts the product page shows from them (price per serving, price of 25 g protein, who it
suits). Shared by the product page (`card_facts`), the AI advisor and the replenishment forecast.
"""
from __future__ import annotations

import re

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


# category (English name, any level) -> what it suits; shown on the product page as plain chips
SUITS = {
    "Whey Isolate": ("low_lactose", "lean"), "Hydrolyzed Whey": ("low_lactose", "fast"), "Casein": ("night",),
    "Vegan Protein": ("vegan", "dairy_free"), "Beef Protein": ("dairy_free",), "Proteins": ("muscle", "recovery"),
    "Creatine": ("strength",), "Gainers": ("mass",), "Fat Burners": ("fat_loss",), "Pre-Workout": ("energy",),
    "Amino Acids": ("recovery",), "Hydration": ("endurance",), "Joint Support": ("joints",), "Sleep Support": ("sleep",),
}
PROTEIN_SECTION = "Proteins"


def card_facts(*, texts: list[str], nutrition: dict, price, category_path: list[str], size: str = "") -> dict:
    """{servings, serving_g, protein, per_serving, per_25g_protein, size, suits} -- only what the card supports."""
    guess = text_numbers(*texts)
    servings = nutrition.get("servings_per_container") or guess.get("servings")
    serving_g = nutrition.get("serving_size_grams") or guess.get("serving_g")
    protein = guess.get("protein")
    try:
        price = float(price or 0)
    except (TypeError, ValueError):
        price = 0
    out: dict = {"servings": int(servings) if servings else None, "serving_g": float(serving_g) if serving_g else None, "protein": protein, "size": size}
    out["per_serving"] = round(price / float(servings)) if price and servings else None
    is_protein = PROTEIN_SECTION in category_path
    out["per_25g_protein"] = round(price / float(servings) / protein * 25) if (is_protein and price and servings and protein) else None
    suits: list[str] = []
    for name in reversed(category_path):  # the most specific section first
        for tag in SUITS.get(name, ()):
            if tag not in suits:
                suits.append(tag)
    out["suits"] = suits[:4]
    return out
