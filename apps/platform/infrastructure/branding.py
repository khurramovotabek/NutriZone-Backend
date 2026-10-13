"""
The project's brand (name, short name, logo, colours) comes from SiteSettings -- change it once in
Dashboard → Sozlamalar and every surface follows: the admin (header, sidebar, footer, login), the
storefront (via GET /settings/public), receipts, documents, Excel exports, SMS and the Telegram bot.

Code keeps writing the default name ("NutriZone"); `rebrand()` swaps it for the configured one at the
edge. Values live in the shared cache (all web/bot/worker processes see a rename at once), with a
2-second in-process memo on top; saving SiteSettings drops both.
"""
from __future__ import annotations

import time

DEFAULT_NAME = "NutriZone"
_TTL = 2.0
_SHARED_KEY = "nz:brand:v1"
_cache: dict = {"at": 0.0, "value": None}


def brand() -> dict:
    now = time.monotonic()
    if _cache["value"] is not None and now - _cache["at"] < _TTL:
        return _cache["value"]
    from django.core.cache import cache

    try:
        shared = cache.get(_SHARED_KEY)
    except Exception:  # noqa: BLE001 - cache backend down: read the database
        shared = None
    if shared:
        _cache.update(at=now, value=shared)
        return shared
    try:
        from apps.platform.infrastructure.admin import get_site_settings

        s = get_site_settings()
        name = (s.site_name or DEFAULT_NAME).strip() or DEFAULT_NAME
        short = (getattr(s, "short_name", "") or "").strip()
        if not short or (short == DEFAULT_NAME and name != DEFAULT_NAME):
            short = name  # the untouched default short name follows a rename
        value = {
            "name": name,
            "short_name": short,
            "logo_url": s.logo.url if s.logo else None,
            "primary_color": s.primary_color or None,
            "secondary_color": getattr(s, "secondary_color", None) or None,
            "accent_color": getattr(s, "accent_color", None) or None,
        }
    except Exception:  # noqa: BLE001 - database not ready (migrations, first boot): fall back to the default
        value = {"name": DEFAULT_NAME, "short_name": "", "logo_url": None, "primary_color": None, "secondary_color": None, "accent_color": None}
    else:
        try:
            cache.set(_SHARED_KEY, value, 300)
        except Exception:  # noqa: BLE001
            pass
    _cache.update(at=now, value=value)
    return value


def brand_name() -> str:
    return brand()["name"]


def invalidate(*_args, **_kwargs) -> None:
    _cache.update(at=0.0, value=None)
    try:
        from django.core.cache import cache

        cache.delete(_SHARED_KEY)
    except Exception:  # noqa: BLE001
        pass


def rebrand(text):
    """Replace the default brand in a user-facing string with the configured one (no-op when unchanged)."""
    if not isinstance(text, str):
        return text
    name = brand_name()
    if name == DEFAULT_NAME or DEFAULT_NAME.lower() not in text.lower():
        return text
    return text.replace(DEFAULT_NAME, name).replace(DEFAULT_NAME.upper(), name.upper())


def file_slug() -> str:
    import re

    return re.sub(r"[^A-Za-z0-9]+", "_", brand_name()).strip("_") or DEFAULT_NAME


class AdminBrandingMiddleware:
    """Keeps Jazzmin's header / sidebar / footer / login texts on the configured brand (Jazzmin re-reads JAZZMIN_SETTINGS per request)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/django-admin"):
            from django.conf import settings

            name = brand_name()
            js = settings.JAZZMIN_SETTINGS
            if js.get("site_brand") != name:
                js.update(site_title=name, site_header=name, site_brand=name, copyright=name, welcome_sign=f"{name} — Internal Operations")
        return self.get_response(request)
