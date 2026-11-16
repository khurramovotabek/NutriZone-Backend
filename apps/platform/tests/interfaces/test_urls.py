"""
URL structure checks -- AST-based, not `django.urls.resolve()` (which
requires a configured Django app registry, unavailable in this
sandbox). Matches every prior module's identical static URL-structure
verification pattern used when runtime resolution isn't available.
"""
from __future__ import annotations

import apps.platform.interfaces.api.v1.urls as platform_urls_module


def test_exactly_6_routes_registered():
    """5 + the public banner click counter (2026-11-16)."""
    assert len(platform_urls_module.urlpatterns) == 6


def test_contact_message_create_route_pattern():
    patterns = [str(p.pattern) for p in platform_urls_module.urlpatterns]
    assert "contact-messages" in patterns


def test_banner_list_route_pattern():
    patterns = [str(p.pattern) for p in platform_urls_module.urlpatterns]
    assert "settings/banners" in patterns


def test_site_settings_public_route_pattern():
    patterns = [str(p.pattern) for p in platform_urls_module.urlpatterns]
    assert "settings/public" in patterns


def test_feature_flag_list_route_pattern():
    patterns = [str(p.pattern) for p in platform_urls_module.urlpatterns]
    assert "settings/feature-flags" in patterns


def test_feature_flag_detail_route_pattern():
    patterns = [str(p.pattern) for p in platform_urls_module.urlpatterns]
    assert any("settings/feature-flags/" in p for p in patterns)


def test_app_name_is_platform():
    assert platform_urls_module.app_name == "platform"
