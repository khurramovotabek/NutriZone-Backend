"""
NutriZone Admin "Settings" premium page tests -- closes a real,
confirmed gap: SiteSettings (branding/contact), FeatureFlagModel, and
environment-based integration configuration were three separate,
disconnected surfaces with no single overview.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.platform.infrastructure.models import FeatureFlagModel, SiteSettings
from apps.platform.infrastructure.settings_overview import SettingsOverviewAggregator

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def staff_client():
    AuthUser = get_user_model()
    user = AuthUser.objects.create(username=f"nz_staff_{uuid.uuid4().hex[:8]}", is_staff=True, is_superuser=True)
    user.set_password("pw")
    user.save()
    client = Client()
    client.force_login(user)
    return client


class TestSettingsOverviewAggregator:
    def test_integration_status_never_exposes_the_actual_token_value(self, settings):
        settings.TELEGRAM_BOT_TOKEN = "123456:REAL-SECRET-TOKEN-VALUE"
        status = SettingsOverviewAggregator().integration_status()
        assert status["telegram_bot_token_configured"] is True
        assert "REAL-SECRET-TOKEN-VALUE" not in str(status)

    def test_integration_status_reports_not_configured_when_absent(self, settings):
        settings.TELEGRAM_BOT_TOKEN = None
        status = SettingsOverviewAggregator().integration_status()
        assert status["telegram_bot_token_configured"] is False


class TestSettingsOverviewPage:
    def test_page_renders_without_feature_flags(self, staff_client):
        FeatureFlagModel.objects.create(id=uuid.uuid4(), key="new_checkout_flow", is_globally_enabled=True, rollout_percentage=50)

        response = staff_client.get("/django-admin/settings-overview/")
        assert response.status_code == 200
        assert "new_checkout_flow" not in response.content.decode()

    def test_posting_the_form_really_persists_site_settings(self, staff_client):
        response = staff_client.post("/django-admin/settings-overview/", data={
            "site_name": "NutriZone Premium", "short_name": "NZ", "default_language": "uz",
            "primary_color": "#123456", "secondary_color": "", "accent_color": "",
            "support_phone": "+998712033333", "telegram_username": "nutrizone_support", "telegram_channel_url": "", "instagram_url": "",
        }, follow=True)
        assert response.status_code == 200

        settings_obj = SiteSettings.objects.get(pk=1)
        assert settings_obj.site_name == "NutriZone Premium"
        assert settings_obj.primary_color == "#123456"
        assert settings_obj.support_phone == "+998712033333"

    def test_page_requires_staff_authentication(self):
        response = Client().get("/django-admin/settings-overview/")
        assert response.status_code in (302, 403)

    def test_page_is_linked_from_the_dashboard_home(self, staff_client):
        response = staff_client.get("/django-admin/")
        assert response.status_code == 200
        assert "settings-overview" in response.content.decode()

    def test_invalid_color_is_rejected_and_nothing_is_saved(self, staff_client):
        response = staff_client.post("/django-admin/settings-overview/", data={"site_name": "X", "short_name": "X", "default_language": "uz", "primary_color": "blue;}", "secondary_color": "", "accent_color": ""})
        assert response.status_code == 200
        assert SiteSettings.objects.get(pk=1).site_name != "X"

    def test_sidebar_site_settings_entry_opens_the_settings_page(self, staff_client):
        response = staff_client.get("/django-admin/platform/sitesettings/")
        assert response.status_code == 302
        assert response["Location"].endswith("/django-admin/settings-overview/")

    def test_brand_colour_is_applied_to_the_dashboard(self, staff_client):
        SiteSettings.objects.update_or_create(pk=1, defaults={"primary_color": "#0ea5e9"})
        assert "/django-admin/branding.css?v=" in staff_client.get("/django-admin/").content.decode()
        css = Client().get("/django-admin/branding.css").content.decode()  # public: the login page needs it too
        assert "--nz-primary: #0ea5e9;" in css

    def test_branding_css_never_echoes_an_invalid_colour(self, staff_client):
        SiteSettings.objects.update_or_create(pk=1, defaults={"primary_color": "red;}"})
        css = Client().get("/django-admin/branding.css").content.decode()
        assert "red;}" not in css and "--nz-primary" not in css
