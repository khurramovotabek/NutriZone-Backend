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
