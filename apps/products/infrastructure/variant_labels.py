"""
One way to name a purchasable variant everywhere it is shown (POS, receipts, stock, transfers, price list, Telegram,
cart / order screens): "2.27 kg · Chocolate" -- size, then flavour, then (optionally) the package.

Each variant of a product family is one size x one flavour (ProductVariant.flavour), so a line that says only
"2.27 kg" can no longer tell a cashier or a picker which tub to take.
"""
from __future__ import annotations


def size_text(value, unit) -> str | None:
    if not value:
        return None
    number = int(value) if float(value).is_integer() else round(float(value), 3)
    return f"{number} {unit}"


def translated_name(obj, locale: str | None = "uz") -> str:
    """The name of a Flavour / Package in `locale` (then uz, en, anything) -- uses prefetched translations."""
    if obj is None:
        return ""
    rows = {t.locale_code: t.name for t in obj.translations.all()}
    return rows.get((locale or "uz")[:2]) or rows.get("uz") or rows.get("en") or next(iter(rows.values()), "")


def variant_label(variant, locale: str | None = "uz", *, package: bool = True) -> str | None:
    parts = [size_text(variant.weight_value, variant.weight_unit)]
    if getattr(variant, "flavour_id", None) and getattr(variant, "flavour", None) is not None:
        parts.append(translated_name(variant.flavour, locale))
    if package and getattr(variant, "package_id", None) and getattr(variant, "package", None) is not None:
        parts.append(translated_name(variant.package, locale))
    return " · ".join(p for p in parts if p) or None
