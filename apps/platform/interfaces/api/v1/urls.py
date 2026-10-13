"""
Platform `/api/v1/settings/...` URL routing. Included from
`config/urls/v1.py` with no path prefix (matches REST API Blueprint
§13.18's exact confirmed paths -- `/settings/feature-flags`, not
`/platform/settings/feature-flags` -- the identical "no prefix"
pattern Products'/Store's own urlpatterns already use).
"""
from __future__ import annotations

from django.urls import path

from apps.platform.interfaces.api.v1 import views

app_name = "platform"

urlpatterns = [
    path("settings/public", views.SiteSettingsPublicView.as_view(), name="site-settings-public"),
    path("settings/banners", views.BannerListView.as_view(), name="banner-list"),
    path("settings/feature-flags", views.FeatureFlagListView.as_view(), name="feature-flag-list"),
    path("settings/feature-flags/<str:flag_id>", views.FeatureFlagDetailView.as_view(), name="feature-flag-detail"),
    path("contact-messages", views.ContactMessageCreateView.as_view(), name="contact-message-create"),
]
