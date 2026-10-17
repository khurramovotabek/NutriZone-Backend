"""
Root URLConf.

Composes the versioned/internal/public API namespaces (REST API
Blueprint §2/§3) plus infrastructure endpoints (health checks, Django
Admin, OpenAPI schema/Swagger/ReDoc) that live outside any bounded
context's API surface.
"""
from __future__ import annotations

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from apps.platform.infrastructure.admin_i18n import phrases_js_view
from apps.platform.infrastructure.branding_css import branding_css_view

urlpatterns = [
    # --- Infrastructure (outside the /api/ namespace) ---
    path("health/", include("core.health.urls")),
    path("i18n/", include("django.conf.urls.i18n")),  # Phase 08.1: Django's own set_language view, required for the admin dashboard's language switcher
    path("django-admin/branding.css", branding_css_view, name="nz_branding_css"),  # Site Settings colours/logo for the dashboard (must precede admin.site.urls)
    path("django-admin/i18n/phrases.<str:lang>.js", phrases_js_view, name="nz_admin_phrases"),  # dashboard phrase catalog for nutrizone-i18n.js (apps/platform/infrastructure/admin_i18n.py)
    path("django-admin/", admin.site.urls),  # engineering/ops debugging tool only -- Django Implementation Blueprint §13
    # --- API namespaces (REST API Blueprint §2) ---
    path("api/v1/", include("config.urls.v1", namespace="v1")),
    path("api/v2/", include("config.urls.v2", namespace="v2")),
    path("api/internal/", include("config.urls.internal", namespace="internal")),
    path("api/public/", include("config.urls.public", namespace="public")),
]

if settings.API_DOCS_ENABLED:
    # --- OpenAPI / Swagger / ReDoc (REST API Blueprint §17) -- private in production unless API_DOCS_ENABLED=true ---
    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path("api/docs/swagger/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
        path("api/docs/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    ]

if settings.DEBUG:
    # Real, closed gap: MEDIA_ROOT/MEDIA_URL were correctly configured
    # (config/settings/components/storage.py) and uploaded files were
    # genuinely written to disk there -- but no URL pattern ever served
    # them, so every image request 404'd in both the Dashboard and the
    # customer frontend regardless of a correct upload. Production
    # deployments serve MEDIA_URL via a real web server/CDN in front of
    # Django, not this development-only helper -- gated behind DEBUG so
    # it is never mistakenly relied on in production.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
