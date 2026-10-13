"""
Phase 16.2: SiteSettings tests.

Every scenario here was first verified live via a real HTTP request/
shell session before being formalized, matching the discipline
established throughout this project's own recent phases.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import Client

from apps.platform.infrastructure import models as orm
from apps.platform.infrastructure.admin import get_site_settings

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def staff_client():
    User = get_user_model()
    user = User.objects.create(username=f"nz_staff_{uuid.uuid4().hex[:8]}", is_staff=True, is_superuser=True)
    user.set_password("pw")
    user.save()
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def non_staff_client():
    User = get_user_model()
    user = User.objects.create(username=f"nz_customer_{uuid.uuid4().hex[:8]}", is_staff=False)
    user.set_password("pw")
    user.save()
    client = Client()
    client.force_login(user)
    return client


class TestSiteSettingsSingleton:
    def test_get_site_settings_creates_exactly_one_row(self):
        assert orm.SiteSettings.objects.count() == 0
        settings_obj = get_site_settings()
        assert settings_obj.pk == 1
        assert orm.SiteSettings.objects.count() == 1

    def test_repeated_calls_return_the_same_row(self):
        first = get_site_settings()
        second = get_site_settings()
        assert first.pk == second.pk == 1
        assert orm.SiteSettings.objects.count() == 1

    def test_default_values(self):
        settings_obj = get_site_settings()
        assert settings_obj.site_name == "NutriZone"
        assert settings_obj.default_language == "uz"

    def test_updating_the_row_never_creates_a_second_one(self):
        settings_obj = get_site_settings()
        settings_obj.site_name = "Updated Name"
        settings_obj.save()
        assert orm.SiteSettings.objects.count() == 1
        assert orm.SiteSettings.objects.get(pk=1).site_name == "Updated Name"

    def test_save_forces_pk_to_one_even_if_constructed_with_another_pk(self):
        from django.db import transaction

        get_site_settings()
        rogue = orm.SiteSettings(pk=2, site_name="Rogue Settings")
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                rogue.save()
        assert not orm.SiteSettings.objects.filter(pk=2).exists()


class TestSiteSettingsBrandingRendering:
    def test_dynamic_site_name_appears_in_real_admin_page(self, staff_client):
        settings_obj = get_site_settings()
        settings_obj.site_name = "NutriZone Premium Test"
        settings_obj.save()

        response = staff_client.get("/django-admin/")
        assert response.status_code == 200
        assert "NutriZone Premium Test" in response.content.decode()

    def test_non_admin_pages_are_unaffected_by_the_context_processor(self, staff_client):
        response = staff_client.get("/health/live")
        assert response.status_code == 200


class TestSiteSettingsAccessControl:
    def test_non_staff_cannot_access_site_settings_admin(self, non_staff_client):
        response = non_staff_client.get("/django-admin/platform/sitesettings/1/change/")
        assert response.status_code in (302, 403)

    def test_staff_can_access_site_settings_admin(self, staff_client):
        """The admin change form hands over to the single premium settings page."""
        get_site_settings()
        response = staff_client.get("/django-admin/platform/sitesettings/1/change/", follow=True)
        assert response.status_code == 200
        assert response.redirect_chain[-1][0].endswith("/django-admin/settings-overview/")

    def test_delete_permission_is_always_denied(self, staff_client):
        get_site_settings()
        response = staff_client.get("/django-admin/platform/sitesettings/1/delete/")
        assert response.status_code == 403
