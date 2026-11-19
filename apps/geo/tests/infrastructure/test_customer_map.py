"""Geo → Mijozlar xaritasi: segments, region attribution, staff-only access."""
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User as AuthUser
from django.test import Client
from django.utils import timezone

from apps.geo.infrastructure import customer_map as cm
from apps.geo.infrastructure import models as orm
from apps.geo.tests.interfaces.test_location_detection import _admin, _place
from apps.identity.infrastructure.models import User

pytestmark = pytest.mark.django_db


def _customer(name, region, city, lat, lng):
    u = User.objects.create(phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", full_name=name, status="active")
    orm.Address.objects.create(owner_type="user", owner_id=u.id, address_type="residential", country=region.country, region=region, city=city, line1="Uy",
                               coordinate_latitude=lat, coordinate_longitude=lng, normalized_signature=uuid.uuid4().hex)
    return u


def test_segments_and_regions():
    _country, region, city, _d = _place()
    vip, regular, once, lead = (_customer(n, region, city, 41.30, 69.24) for n in ("Vip", "Doimiy", "Yangi", "Lead"))
    now = timezone.now()
    orders = [{"customer_id": vip.id, "status": "delivered", "amount": Decimal("5000000"), "at": now},
              {"customer_id": regular.id, "status": "delivered", "amount": Decimal("100000"), "at": now - timedelta(days=3)},
              {"customer_id": regular.id, "status": "confirmed", "amount": Decimal("90000"), "at": now},
              {"customer_id": once.id, "status": "completed", "amount": Decimal("80000"), "at": now},
              {"customer_id": lead.id, "status": "cancelled", "amount": Decimal("70000"), "at": now}]
    with mock.patch("apps.platform.infrastructure.business_analytics._online_orders", return_value=orders):
        d = cm.build("90d")
    seg = {c["name"]: c["seg"] for c in d["customers"]}
    assert seg == {"Vip": "vip", "Doimiy": "loyal", "Yangi": "new", "Lead": "lead"}
    by = {c["name"]: c for c in d["customers"]}
    assert by["Doimiy"]["orders"] == 2 and by["Doimiy"]["spent"] == 100000  # only delivered / completed count as spent
    row = next(r for r in d["regions"] if r["id"] == str(region.id))
    assert row["customers"] == 4 and row["revenue"] == 5180000 and row["leads"] == 1 and row["vip"] == 1
    assert d["totals"]["no_branch"] == ["Toshkent shahri"]  # customers there, no branch yet


def test_staff_only_and_page_renders():
    staff = AuthUser.objects.create_user("plain", password="x", is_staff=True)
    c = Client()
    c.force_login(staff)
    assert c.get("/django-admin/geo/customers.json").status_code == 403
    staff.user_permissions.add(Permission.objects.get(codename="view_user", content_type__app_label="identity"))
    c.force_login(AuthUser.objects.get(pk=staff.pk))
    assert c.get("/django-admin/geo/customers.json?p=30d").json()["period"] == "30d"
    page = _admin().get("/django-admin/geo/customers/")
    assert page.status_code == 200 and b"data-nzcm" in page.content
