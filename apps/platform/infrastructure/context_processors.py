"""
Phase 16.2: injects real SiteSettings values into every admin template
context, so base_site.html can render the dynamic site_name/logo/
favicon instead of a hardcoded value.
"""
from __future__ import annotations

import re

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def _valid_color(value: str | None) -> str | None:
    """Only a strict #rrggbb value ever reaches the inline <style> -- anything else falls back to the stylesheet's own blue."""
    return value if value and _HEX_COLOR.match(value) else None


def site_branding(request):
    if not request.path.startswith("/django-admin/"):
        return {}

    from django.conf import settings

    from apps.platform.infrastructure.admin import get_site_settings

    site_settings = get_site_settings()
    return {
        "site_settings": site_settings,
        "brand_name": (site_settings.site_name or "NutriZone").strip() or "NutriZone",
        "nz_brand_primary": _valid_color(site_settings.primary_color),
        "nz_brand_accent": _valid_color(site_settings.accent_color),
        # The storefront, for the login page's "back to the store" link (unset in some environments).
        "nz_frontend_url": (getattr(settings, "FRONTEND_URL", None) or "").rstrip("/"),
    }
