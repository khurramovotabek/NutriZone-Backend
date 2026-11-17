"""
Uzbek phone numbers typed by people, in whatever shape they type them:

    942052040 · 94 205 20 40 · 94-205-20-40 · (94) 205-20-40 · +998942052040 · 998 94 205 20 40 · 8 94 205 20 40

→ "+998942052040" (E.164). Anything that isn't a phone-like string (letters, too few / too many digits, a landline
prefix 0/1) gives "" -- so a product search like "whey 5lb" is never mistaken for a number.
"""
from __future__ import annotations

import re

_ALLOWED = re.compile(r"^[\s\d+\-().]+$")


def parse_uz_phone(raw: str | None) -> str:
    text = (raw or "").strip()
    if not text or not _ALLOWED.match(text):
        return ""
    digits = re.sub(r"\D", "", text)
    if len(digits) == 9:
        digits = "998" + digits
    elif len(digits) == 10 and digits.startswith("8"):
        digits = "998" + digits[1:]
    elif len(digits) == 13 and digits.startswith("9980"):  # "+998 0 94 ..." typed with a trunk zero
        digits = "998" + digits[4:]
    if not re.fullmatch(r"998[2-9]\d{8}", digits):
        return ""
    return "+" + digits


def pretty_uz_phone(e164: str) -> str:
    """'+998942052040' → '+998 94 205 20 40'."""
    d = re.sub(r"\D", "", e164 or "")
    if len(d) != 12:
        return e164 or ""
    return f"+{d[:3]} {d[3:5]} {d[5:8]} {d[8:10]} {d[10:]}"
