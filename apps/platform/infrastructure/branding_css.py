"""
`GET /branding.css` -- the dashboard's brand colour tokens and uploaded
logo as a tiny stylesheet generated from Site Settings. A stylesheet
(not an inline <style>) keeps pages free of inline CSS and lets the
browser cache it: the link carries Site Settings' updated_at, so a save
changes the URL. Public on purpose -- the login page needs it, and it
exposes nothing beyond a colour and the public logo URL.
"""
from __future__ import annotations

from urllib.parse import quote

from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET

from apps.platform.infrastructure.context_processors import _valid_color


@require_GET
def branding_css_view(request):
    from apps.platform.infrastructure.admin import get_site_settings

    site_settings = get_site_settings()
    css = render_to_string("admin/nz_branding.css", {
        "primary": _valid_color(site_settings.primary_color),
        # quote() keeps the url() token intact whatever the stored file name is
        "logo_url": quote(site_settings.logo.url, safe="/:.-_~") if site_settings.logo else None,
    })
    response = HttpResponse(css, content_type="text/css; charset=utf-8")
    response["Cache-Control"] = "public, max-age=31536000, immutable" if request.GET.get("v") else "no-cache"
    return response
