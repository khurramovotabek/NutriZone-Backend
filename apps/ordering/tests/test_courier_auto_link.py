"""Couriers entered before they have an account: phone normalisation, link on save, link on later sign-up."""
import uuid

import pytest
from django.test import Client

from django.contrib.auth.models import User as StaffUser

from apps.identity.infrastructure.models import User
from apps.ordering.infrastructure import couriers
from apps.ordering.infrastructure import models as orm

pytestmark = pytest.mark.django_db


@pytest.fixture
def boss():
    c = Client()
    c.force_login(StaffUser.objects.create_superuser(username=f"kr_{uuid.uuid4().hex[:6]}", password="x-pass-12345"))
    return c


def _user(phone, name="Ali Valiyev"):
    return User.objects.create(phone_number=phone, full_name=name)


def test_normalize_phone():
    assert couriers.normalize_phone("90 123 45 67") == "+998901234567"
    assert couriers.normalize_phone("8 90 123 45 67") == "+998901234567"
    assert couriers.normalize_phone("+998 (90) 123-45-67") == "+998901234567"
    assert couriers.normalize_phone("12345") == ""


def _post(boss, **data):
    base = {"name": "Kuryer", "phone": "", "kind": "staff", "vehicle": "", "telegram_username": "", "default_fee": "", "note": "", "is_active": "on", "user": ""}
    return boss.post("/django-admin/ordering/courier/add/", {**base, **data})


def test_admin_add_links_existing_account_by_phone(boss):
    u = _user("+998901112233")
    r = _post(boss, name="", phone="90 111 22 33", default_fee="25000", telegram_username="@ali")
    assert r.status_code == 302, r.content[:500]
    c = orm.Courier.objects.get(phone="+998901112233")
    assert c.user_id == u.id and c.name == "Ali Valiyev" and c.telegram_username == "ali" and c.default_fee == 25000


def test_admin_add_rejects_bad_and_duplicate_phone(boss):
    assert _post(boss, phone="123").status_code == 200
    assert _post(boss, phone="+998907778899").status_code == 302
    r = _post(boss, name="Boshqa", phone="90 777 88 99")
    assert r.status_code == 200 and "allaqachon" in r.content.decode()


def test_account_created_later_links_itself(boss):
    assert _post(boss, name="Sardor", phone="+998935554433").status_code == 302
    c = orm.Courier.objects.get(phone="+998935554433")
    assert c.user_id is None
    u = _user("+998935554433", "Sardor Karimov")
    c.refresh_from_db()
    assert c.user_id == u.id and c.name == "Sardor"


def test_change_page_shows_connect_hint(boss, settings):
    settings.TELEGRAM_BOT_USERNAME = "NutriZoneBot"
    _post(boss, name="Jasur", phone="+998912223344")
    c = orm.Courier.objects.get(phone="+998912223344")
    page = boss.get(f"/django-admin/ordering/courier/{c.pk}/change/").content.decode()
    assert "https://t.me/NutriZoneBot" in page and "+998912223344" in page
