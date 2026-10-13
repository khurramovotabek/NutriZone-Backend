"""
Real, live-verified regression test for Phase F: SiteSettings'
default primary_color. The brand moved from green to the storefront's
own blue (#1d4ed8, the real --nz-primary token) by product decision.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.platform.infrastructure.models import SiteSettings

pytestmark = pytest.mark.django_db


class TestSiteSettingsDefaultColor:
    def test_new_settings_row_uses_the_brand_blue(self):
        settings_obj, created = SiteSettings.objects.get_or_create(pk=1)
        assert created is True
        assert settings_obj.primary_color == "#1d4ed8"


class TestSiteSettingsAdminPreview:
    def test_color_swatch_renders_real_value(self):
        SiteSettings.objects.filter(pk=1).delete()
        admin_user = User.objects.create_superuser(username=f"admin_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
        client = Client()
        client.force_login(admin_user)
        settings_obj, _ = SiteSettings.objects.get_or_create(pk=1)

        response = client.get("/django-admin/settings-overview/")
        assert response.status_code == 200
        body = response.content.decode()
        assert 'value="#1d4ed8"' in body

    def test_singleton_add_permission_denied_when_row_exists(self):
        admin_user = User.objects.create_superuser(username=f"admin_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
        client = Client()
        client.force_login(admin_user)
        SiteSettings.objects.get_or_create(pk=1)

        response = client.get("/django-admin/platform/sitesettings/add/")
        assert response.status_code in (302, 403)
