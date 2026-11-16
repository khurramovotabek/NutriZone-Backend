"""Kuryerlar: KR-ID, linking a customer account, assignment alerts, stats, cash settlement; delivery price calculator + analysis."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth.models import User as StaffUser
from django.test import Client
from django.utils import timezone

from apps.identity.infrastructure import models as identity_orm
from apps.ordering.infrastructure import admin_delivery, couriers, delivery_insights
from apps.ordering.infrastructure import models as orm
from apps.ordering.tests.interfaces.test_delivery_desk import _order

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_client():
    user = StaffUser.objects.create_superuser(username=f"cr_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
    client = Client()
    client.force_login(user)
    return client


def _user(**kw):
    return identity_orm.User.objects.create(phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", full_name=kw.pop("full_name", "Bekzod Kuryer"),
                                            status="active", telegram_user_id=kw.pop("telegram_user_id", uuid.uuid4().int % 10**9), **kw)


def _deliver(order):
    order.status = "delivered"
    order.save(update_fields=["status"])
    orm.OrderStatusHistoryEntryModel.objects.create(order=order, from_status="shipped", to_status="delivered", changed_at=timezone.now())


def test_courier_gets_a_sequential_id():
    a = orm.Courier.objects.create(name="A")
    b = orm.Courier.objects.create(name="B")
    assert a.code == "KR-001" and b.code == "KR-002"
    assert str(b) == "B (KR-002)"


def test_find_and_link_user_fills_empty_fields():
    u = _user(full_name="Jasur Aliyev", telegram_username="jasur_k")
    found = couriers.find_users(u.phone_number[-7:])
    assert [f["id"] for f in found] == [str(u.id)] and found[0]["telegram"]
    c = orm.Courier(name="")
    assert set(couriers.link_user(c, u)) == {"name", "phone", "telegram_username"}
    assert c.name == "Jasur Aliyev" and c.user == u


def test_assigning_a_linked_courier_notifies_them(django_capture_on_commit_callbacks):
    from apps.notifications.infrastructure.models import NotificationModel

    u = _user()
    courier = orm.Courier.objects.create(name="Bekzod", user=u, default_fee=Decimal("20000"))
    order = _order()
    with django_capture_on_commit_callbacks(execute=True):
        row = admin_delivery.assign(order, {"courier_id": str(courier.id)}, by="staff")
    assert row.courier_notified and row.assigned_at and row.fee == Decimal("20000")
    note = NotificationModel.objects.get(recipient_id=u.id, kind="courier_assigned")
    assert order.order_number in note.body and "300 000" in note.body
    assert note.link.startswith("https://yandex.uz/maps/")
    # saving again with the same courier does not alert twice
    with django_capture_on_commit_callbacks(execute=True):
        again = admin_delivery.assign(order, {"courier_id": str(courier.id), "note": "2-qavat"}, by="staff")
    assert not again.courier_notified
    assert NotificationModel.objects.filter(recipient_id=u.id, kind="courier_assigned").count() == 1


def test_stats_and_cash_settlement():
    courier = orm.Courier.objects.create(name="Bekzod")
    done, road = _order(status="shipped"), _order(status="shipped")
    admin_delivery.assign(done, {"courier_id": str(courier.id), "fee": "25000"}, by="staff")
    admin_delivery.assign(road, {"courier_id": str(courier.id)}, by="staff")
    _deliver(done)
    st = couriers.stats([courier])[courier.id]
    assert st["active"] == 1 and st["road"] == 1 and st["delivered"] == 1 and st["today"] == 1
    assert st["cash"] == Decimal("300000") and st["cash_orders"] == 1 and st["fees"] == Decimal("25000")
    n, amount = couriers.settle_cash(courier, "kassir")
    assert (n, amount) == (1, Decimal("300000"))
    assert couriers.stats([courier])[courier.id]["cash"] == 0


def test_courier_pages_and_settle_endpoint(staff_client):
    u = _user()
    courier = orm.Courier.objects.create(name="Bekzod", user=u)
    order = _order(status="shipped")
    admin_delivery.assign(order, {"courier_id": str(courier.id)}, by="staff")
    _deliver(order)
    page = staff_client.get("/django-admin/ordering/courier/")
    assert page.status_code == 200 and "KR-001" in page.content.decode()
    card = staff_client.get(f"/django-admin/ordering/courier/{courier.pk}/change/").content.decode()
    assert "Qo&#x27;lidagi naqd" in card or "Qo'lidagi naqd" in card
    assert order.order_number in card
    r = staff_client.post(f"/django-admin/ordering/courier/{courier.pk}/settle/")
    assert r.status_code == 302
    assert orm.DeliveryAssignment.objects.get(order=order).cash_settled_at is not None


def test_one_account_one_courier(staff_client):
    u = _user()
    orm.Courier.objects.create(name="Birinchi", user=u)
    r = staff_client.post("/django-admin/ordering/courier/add/", {"user": str(u.id), "name": "", "phone": "", "kind": "staff", "vehicle": "",
                                                                    "telegram_username": "", "default_fee": "", "note": "", "is_active": "on"})
    assert r.status_code == 200 and "allaqachon" in r.content.decode()


def test_delivery_calculator_and_analysis(staff_client):
    r = staff_client.get("/django-admin/ordering/deliverysettings/calc/?region=TGCITYR&km=7&total=100000").json()
    assert r["ok"] and r["zone"] == "tashkent" and r["fee"] > 0 and r["parts"]
    assert staff_client.get("/django-admin/ordering/deliverysettings/calc/").status_code == 400
    _order(status="delivered")
    data = delivery_insights.summary(90)
    assert data["total"] == 1 and sum(z["earned"] for z in data["zones"].values()) == 1
    page = staff_client.get("/django-admin/ordering/deliverysettings/1/change/")
    assert page.status_code == 200 and "nzdp-calc" in page.content.decode()
