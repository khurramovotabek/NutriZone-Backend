"""Dashboard → Do'konlar: the chain's standard week and the bulk "special day" action."""
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.stores.infrastructure.models import STANDARD_WORKING_HOURS, Store

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client():
    user = get_user_model().objects.create_superuser(f"boss{uuid.uuid4().hex[:6]}", "b@example.com", "x")
    c = Client()
    c.force_login(user)
    return c


def _store(kind="store", **kw):
    return Store.objects.create(id=uuid.uuid4(), name=f"S {kind}", slug=f"s-{uuid.uuid4().hex[:6]}", kind=kind, status="active", **kw)


def test_standard_week_is_the_owners_schedule():
    assert {d: (v["open"], v["close"]) for d, v in STANDARD_WORKING_HOURS.items()} == {
        "mon": ("10:00", "20:00"), "tue": ("10:00", "20:00"), "wed": ("10:00", "20:00"), "thu": ("10:00", "20:00"), "fri": ("10:00", "20:00"),
        "sat": ("10:00", "19:00"), "sun": ("10:00", "17:00")}
    assert not any(v["closed"] for v in STANDARD_WORKING_HOURS.values())


def test_apply_standard_hours_skips_warehouses(admin_client):
    shop, wh = _store(), _store("warehouse")
    admin_client.post("/django-admin/stores/store/", {"action": "apply_standard_hours", "_selected_action": [str(shop.pk), str(wh.pk)]})
    shop.refresh_from_db()
    wh.refresh_from_db()
    assert shop.working_hours == STANDARD_WORKING_HOURS
    assert wh.working_hours == {}


def test_special_day_is_added_once_and_replaced_on_repeat(admin_client):
    shop = _store(special_hours=[{"date": "2027-01-01", "closed": True, "open": "", "close": "", "note": ""}])
    url, sel = "/django-admin/stores/store/", [str(shop.pk)]
    admin_client.post(url, {"action": "add_special_day", "_selected_action": sel, "day": "2027-03-21", "day_closed": "on", "day_note": "Navro'z"})
    admin_client.post(url, {"action": "add_special_day", "_selected_action": sel, "day": "2027-03-21", "day_open": "10:00", "day_close": "15:00", "day_note": "Navro'z"})
    shop.refresh_from_db()
    assert shop.special_hours == [{"date": "2027-01-01", "closed": True, "open": "", "close": "", "note": ""},
                                  {"date": "2027-03-21", "closed": False, "open": "10:00", "close": "15:00", "note": "Navro'z"}]


def test_special_day_needs_a_date_and_valid_hours(admin_client):
    shop = _store()
    url, sel = "/django-admin/stores/store/", [str(shop.pk)]
    r = admin_client.post(url, {"action": "add_special_day", "_selected_action": sel}, follow=True)
    assert "Avval sanani tanlang" in r.content.decode()
    r = admin_client.post(url, {"action": "add_special_day", "_selected_action": sel, "day": "2027-03-21", "day_open": "18:00", "day_close": "10:00"}, follow=True)
    assert "ochilishdan keyin" in r.content.decode()
    shop.refresh_from_db()
    assert shop.special_hours == []


def test_list_shows_until_when_open(admin_client):
    _store(working_hours={d: {"open": "00:00", "close": "23:59", "closed": False} for d in STANDARD_WORKING_HOURS})
    html = admin_client.get("/django-admin/stores/store/").content.decode()
    assert "23:59 gacha" in html
