"""
Locale resolution.

One resolution function, used both for Django's own i18n machinery
(system-authored strings, `.po` files under `locale/`) and for resolving
which `*_translations` row to read from the database (Enterprise
Database Blueprint §4.2 pattern) -- Django Implementation Blueprint §5
specifically calls out that a locale must never be resolved two
different ways in two different code paths.
"""
from __future__ import annotations

from django.http import HttpRequest

SUPPORTED_LOCALES = ("uz", "ru", "en")
DEFAULT_LOCALE = "uz"

# Real, product-required capability: every "*_translations" model
# across the project had a bare CharField for locale_code -- an admin
# had to type "uz"/"ru"/"en" correctly by hand, with no guardrail
# against a typo silently creating an orphaned, invisible translation
# row. Used as Django's own `choices=` on each such field, this turns
# every one of them into a real dropdown -- human-readable labels,
# not a code the admin has to remember.
LOCALE_CHOICES = (
    ("uz", "O'zbekcha"),
    ("ru", "Русский"),
    ("en", "English"),
)


def resolve_locale(request: HttpRequest | None, explicit: str | None = None) -> str:
    """
    Resolution order: explicit `?filter[locale]=` query param (REST API
    Blueprint §10) > `Accept-Language` header > platform default.
    """
    if explicit and explicit in SUPPORTED_LOCALES:
        return explicit

    if request is not None:
        accept_language = request.headers.get("Accept-Language", "")
        for part in accept_language.split(","):
            code = part.split(";")[0].strip().split("-")[0].lower()
            if code in SUPPORTED_LOCALES:
                return code

    return DEFAULT_LOCALE
