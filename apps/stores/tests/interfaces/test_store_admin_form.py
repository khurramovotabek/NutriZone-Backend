"""Dashboard → Do'kon qo'shish: phone list, city, weekly hours grid and special days are entered without JSON and validated."""
from __future__ import annotations

import pytest
from django.http import QueryDict

from apps.stores.infrastructure.admin import StoreAdminForm

pytestmark = pytest.mark.django_db


def _data(**extra):
    q = QueryDict(mutable=True)
    base = {"kind": "store", "name": "Test filial", "status": "active", "color": "#22C55E", "city": "Samarqand", "latitude": "39.65", "longitude": "66.96"}
    for k, v in {**base, **extra}.items():
        q[k] = v
    q.setlist("phone_numbers__item", ["90 123 45 67", "+998 (91) 765-43-21", "998901234567", ""])
    for code in ("mon", "tue", "wed", "thu", "fri", "sat"):
        q[f"hours_{code}_open"], q[f"hours_{code}_close"] = "10:00", "20:00"
    q["hours_sun_closed"] = "on"
    q.setlist("special_hours__date", ["2027-03-21", "2027-01-01"])
    q.setlist("special_hours__open", ["", "12:00"])
    q.setlist("special_hours__close", ["", "18:00"])
    q.setlist("special_hours__note", ["Navro'z", "Yangi yil"])
    q.setlist("special_hours__closed", ["0"])
    return q


def test_human_inputs_are_saved_in_the_models_shape():
    form = StoreAdminForm(data=_data())
    assert form.is_valid(), form.errors
    store = form.save()
    assert store.phone_numbers == ["+998901234567", "+998917654321"]  # normalized, de-duplicated, blanks dropped
    assert store.city == "Samarqand"
    assert store.working_hours["mon"] == {"open": "10:00", "close": "20:00", "closed": False}
    assert store.working_hours["sun"]["closed"] is True
    assert store.special_hours == [
        {"date": "2027-01-01", "closed": False, "open": "12:00", "close": "18:00", "note": "Yangi yil"},
        {"date": "2027-03-21", "closed": True, "note": "Navro'z"},
    ]


def test_bad_phone_and_reversed_hours_are_rejected():
    data = _data()
    data.setlist("phone_numbers__item", ["12345"])
    data["hours_mon_open"], data["hours_mon_close"] = "20:00", "10:00"
    form = StoreAdminForm(data=data)
    assert not form.is_valid()
    assert "phone_numbers" in form.errors and "hours_mon_open" in form.errors


def test_city_outside_the_list_can_be_typed():
    data = _data(city="__other")
    data["city__other"] = "Yangiobod"
    form = StoreAdminForm(data=data)
    assert form.is_valid(), form.errors
    assert form.save().city == "Yangiobod"
