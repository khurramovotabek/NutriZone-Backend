"""The dashboard opens in Uzbek whatever the browser asks for; only its own switcher changes it, per session."""
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def staff_client():
    user = get_user_model().objects.create(username=f"nz_lang_{uuid.uuid4().hex[:8]}", is_staff=True, is_superuser=True)
    client = Client()
    client.force_login(user)
    return client


@override_settings(ADMIN_FORCE_DEFAULT_LANGUAGE=True, ADMIN_DEFAULT_LANGUAGE="uz")
def test_browser_language_and_old_cookie_do_not_change_the_dashboard(staff_client):
    staff_client.cookies["django_language"] = "en"
    resp = staff_client.get("/django-admin/", HTTP_ACCEPT_LANGUAGE="en-US,en;q=0.9")
    assert resp.headers.get("Content-Language") == "uz"


@override_settings(ADMIN_FORCE_DEFAULT_LANGUAGE=True, ADMIN_DEFAULT_LANGUAGE="uz")
def test_switcher_choice_holds_for_the_session_only(staff_client):
    staff_client.post("/i18n/setlang/", {"language": "ru", "next": "/django-admin/"})
    assert staff_client.get("/django-admin/").headers.get("Content-Language") == "ru"
    staff_client.logout()
    staff_client.cookies["django_language"] = "ru"
    assert Client().get("/django-admin/login/", HTTP_ACCEPT_LANGUAGE="ru").headers.get("Content-Language") == "uz"
