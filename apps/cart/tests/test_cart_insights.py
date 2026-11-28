"""Savatlar → Tahlil: funnel from cart events + the order link, abandoned age buckets, reminders won back, remind-all."""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User as StaffUser
from django.test import Client
from django.utils import timezone

from apps.cart.infrastructure import cart_analytics
from apps.cart.infrastructure import models as orm

pytestmark = pytest.mark.django_db


def _cart(customer=None, days_ago=0, items=1):
    c = orm.CartModel.objects.create(code=f"C{uuid.uuid4().hex[:10].upper()}", customer_id=customer)
    at = timezone.now() - timedelta(days=days_ago)
    for _ in range(items):
        orm.CartItemModel.objects.create(cart=c, product_variant_id=uuid.uuid4(), quantity=1, status="active", added_at=at)
    orm.CartAuditEntryModel.objects.create(cart=c, action="item_added", occurred_at=at, details={})
    orm.CartModel.objects.filter(pk=c.pk).update(updated_at=at)
    return c


def _order_from(cart, status="delivered"):
    from apps.ordering.infrastructure.models import OrderLineItemModel, OrderModel

    o = OrderModel.objects.create(order_number=f"ORD-{uuid.uuid4().hex[:8].upper()}", status=status, currency="UZS", cart_id=cart.id, placed_at=timezone.now(),
                                  shipping_recipient_name="A", shipping_line1="x", shipping_city="Toshkent", shipping_country_code="UZ",
                                  billing_recipient_name="A", billing_line1="x", billing_city="Toshkent", billing_country_code="UZ")
    OrderLineItemModel.objects.create(order=o, product_variant_id=uuid.uuid4(), quantity=1, unit_price_amount=Decimal("100000"))
    return o


def test_funnel_and_abandoned_buckets():
    ordered = _cart(customer=uuid.uuid4(), days_ago=2)
    _order_from(ordered)
    _cart(customer=uuid.uuid4(), days_ago=2)  # abandoned, reachable
    _cart(days_ago=10)                         # abandoned guest
    data = cart_analytics.build(30)
    f = {x["key"]: x["n"] for x in data["funnel"]}
    assert f == {"started": 3, "signed": 2, "ordered": 1, "delivered": 1}
    assert data["kpi"]["revenue"] == Decimal("100000")
    ages = {a["label"]: (a["carts"], a["reachable"]) for a in data["abandoned"]["age"]}
    assert ages["1–3 kun"] == (1, 1) and ages["7–30 kun"] == (1, 0)
    assert data["abandoned"]["remindable"] == 1
    assert len(data["series"]["bars"]) == 30


def test_reminder_counts_as_won_back():
    c = _cart(customer=uuid.uuid4(), days_ago=3)
    orm.CartAuditEntryModel.objects.create(cart=c, action="reminder_sent", occurred_at=timezone.now() - timedelta(days=1), details={})
    _order_from(c, status="confirmed")
    r = cart_analytics.build(30)["reminders"]
    assert (r["sent"], r["won"]) == (1, 1) and r["value"] == Decimal("100000")


def test_insights_tab_and_remind_all(django_capture_on_commit_callbacks):
    staff = StaffUser.objects.create_superuser(username=f"ci_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
    client = Client()
    client.force_login(staff)
    c = _cart(customer=uuid.uuid4(), days_ago=2)
    page = client.get("/django-admin/cart/cartmodel/?view=insights&days=90")
    assert page.status_code == 200 and "Savat voronkasi" in page.content.decode()
    assert client.get("/django-admin/cart/cartmodel/").status_code == 200
    with django_capture_on_commit_callbacks(execute=True):
        r = client.post("/django-admin/cart/cartmodel/remind-all/")
    assert r.status_code == 302
    assert orm.CartAuditEntryModel.objects.filter(cart=c, action="reminder_sent").count() == 1
    client.post("/django-admin/cart/cartmodel/remind-all/")  # 24 h guard
    assert orm.CartAuditEntryModel.objects.filter(cart=c, action="reminder_sent").count() == 1
    assert client.get("/django-admin/cart/cartmodel/history/change/").status_code == 404


# ---- automatic reminders (cart_reminders.py) + the period loss number


def _sent(cart):
    return list(orm.CartAuditEntryModel.objects.filter(cart=cart, action="reminder_sent").order_by("occurred_at"))


def _age(cart, hours):
    orm.CartModel.objects.filter(pk=cart.pk).update(updated_at=timezone.now() - timedelta(hours=hours))


def test_auto_reminder_steps_follow_idle_time(monkeypatch):
    from apps.cart.infrastructure import cart_reminders

    calls = []
    monkeypatch.setattr("apps.notifications.infrastructure.notify.notify", lambda uid, kind, ctx=None, **kw: calls.append((uid, kind, ctx)))
    c = _cart(customer=uuid.uuid4())
    _age(c, 1)
    assert cart_reminders.run_auto()["sent"] == 0  # under 2 h: too early
    _age(c, 3)
    assert cart_reminders.run_auto()["step1"] == 1
    assert calls[-1][1] == "cart_reminder" and "total" in calls[-1][2]
    assert cart_reminders.run_auto()["sent"] == 0  # 20 h gap
    orm.CartAuditEntryModel.objects.filter(cart=c).update(occurred_at=timezone.now() - timedelta(hours=21))
    _age(c, 30)
    orm.CartAuditEntryModel.objects.filter(cart=c, action="reminder_sent").update(occurred_at=timezone.now() - timedelta(hours=21))
    assert cart_reminders.run_auto()["step2"] == 1
    orm.CartAuditEntryModel.objects.filter(cart=c, action="reminder_sent").update(occurred_at=timezone.now() - timedelta(hours=21))
    _age(c, 80)
    assert cart_reminders.run_auto()["step3"] == 1
    orm.CartAuditEntryModel.objects.filter(cart=c, action="reminder_sent").update(occurred_at=timezone.now() - timedelta(hours=21))
    _age(c, 100)
    assert cart_reminders.run_auto()["sent"] == 0  # three is the limit
    assert [e.details["step"] for e in _sent(c)] == [1, 2, 3]
    assert all(e.details["by"] == cart_reminders.AUTO_BY for e in _sent(c))


def test_auto_reminder_skips_guests_old_and_ordered(monkeypatch):
    from apps.cart.infrastructure import cart_reminders

    monkeypatch.setattr("apps.notifications.infrastructure.notify.notify", lambda *a, **kw: None)
    guest = _cart()
    _age(guest, 5)
    old = _cart(customer=uuid.uuid4())
    _age(old, 24 * 8)
    ordered = _cart(customer=uuid.uuid4())
    _age(ordered, 5)
    _order_from(ordered, status="confirmed")
    # ordered elsewhere (bot / another cart) after this cart's last change
    other = _cart(customer=uuid.uuid4())
    _age(other, 5)
    from apps.ordering.infrastructure.models import OrderModel
    o = _order_from(_cart(customer=other.customer_id), status="confirmed")
    OrderModel.objects.filter(pk=o.pk).update(customer_id=other.customer_id)
    assert cart_reminders.run_auto()["sent"] == 0


def test_late_cart_gets_the_current_step_only(monkeypatch):
    from apps.cart.infrastructure import cart_reminders

    c = _cart(customer=uuid.uuid4())
    now = timezone.now()
    c.refresh_from_db()
    orm.CartModel.objects.filter(pk=c.pk).update(updated_at=now - timedelta(hours=30))
    c.refresh_from_db()
    assert cart_reminders.due_step(c, [], now) == (2, "cart_reminder_2")


def test_period_loss_counts_only_this_periods_carts():
    _cart(customer=uuid.uuid4(), days_ago=2)
    _cart(days_ago=3, items=2)
    old = _cart(days_ago=60)
    orm.CartAuditEntryModel.objects.filter(cart=old).update(occurred_at=timezone.now() - timedelta(days=60))
    d = cart_analytics.build(30)
    assert d["lost"]["carts"] == 2
    assert d["lost"]["guest_carts"] == 1 and d["lost"]["signed_carts"] == 1
    assert d["lost"]["single"] == 1
    assert d["abandoned"]["carts"] == 3  # the all-time view still shows the old one
