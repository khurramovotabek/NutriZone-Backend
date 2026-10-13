"""Replenishment: when a customer's purchase runs out, and the daily "running low" reminder."""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.ordering.infrastructure import replenishment as rp
from apps.products.infrastructure.models import Product, ProductTranslation

pytestmark = pytest.mark.django_db
NOW = timezone.now()


def _buy(customer, product, days_ago, qty=1, ref=None):
    return rp.Purchase(customer, product, None, qty, NOW - timedelta(days=days_ago), ref or f"order:{uuid.uuid4()}")


def _forecast(monkeypatch, purchases):
    monkeypatch.setattr(rp, "purchases", lambda customer_ids=None, since=None: purchases)
    return {f.product_id: f for f in rp.forecasts()}


def test_servings_default_and_clamping(monkeypatch):
    customer = uuid.uuid4()
    whey = Product.objects.create(id=uuid.uuid4(), status="published", nutrition_servings_per_container=74)
    unknown = Product.objects.create(id=uuid.uuid4(), status="published")
    bulk = Product.objects.create(id=uuid.uuid4(), status="published")
    f = _forecast(monkeypatch, [_buy(customer, whey.id, 10, qty=2), _buy(customer, unknown.id, 5), _buy(customer, bulk.id, 1, qty=12)])

    assert (f[whey.id].basis, f[whey.id].supply_days) == ("servings", 148)  # 2 tubs x 74 servings, 1 a day
    assert (f[unknown.id].basis, f[unknown.id].supply_days) == ("default", 30)
    assert f[bulk.id].supply_days == rp.MAX_DAYS  # 12 x 30 days is clamped


def test_their_own_rhythm_beats_the_label(monkeypatch):
    customer = uuid.uuid4()
    whey = Product.objects.create(id=uuid.uuid4(), status="published", nutrition_servings_per_container=74)
    # bought one tub every ~40 days (two servings a day, not one), then two tubs at once
    f = _forecast(monkeypatch, [_buy(customer, whey.id, 120), _buy(customer, whey.id, 80), _buy(customer, whey.id, 40, qty=2)])[whey.id]
    assert (f.basis, f.supply_days) == ("history", 80)
    assert f.days_left(NOW) == 40  # 80 days of supply, bought 40 days ago


def test_two_lines_of_one_order_are_one_purchase(monkeypatch):
    customer, ref = uuid.uuid4(), "order:same"
    product = Product.objects.create(id=uuid.uuid4(), status="published", nutrition_servings_per_container=30)
    f = _forecast(monkeypatch, [_buy(customer, product.id, 2, ref=ref), _buy(customer, product.id, 2, ref=ref)])[product.id]
    assert (f.basis, f.supply_days) == ("servings", 60)


def test_due_needs_the_window_a_published_product_and_stock(monkeypatch):
    from apps.stores.tests.interfaces.test_wms_planning import _put, _store, _variant

    customer = uuid.uuid4()
    in_stock = _variant().product
    Product.objects.filter(pk=in_stock.pk).update(status="published", nutrition_servings_per_container=30)
    _put(_store(), in_stock.variants.first(), 5)
    no_stock = Product.objects.create(id=uuid.uuid4(), status="published", nutrition_servings_per_container=30)
    far = Product.objects.create(id=uuid.uuid4(), status="published", nutrition_servings_per_container=300)
    monkeypatch.setattr(rp, "purchases", lambda customer_ids=None, since=None: [
        _buy(customer, in_stock.id, 27), _buy(customer, no_stock.id, 27), _buy(customer, far.id, 27)])

    assert [f.product_id for f in rp.due(NOW)] == [in_stock.id]


def test_daily_task_reminds_once_per_purchase_in_each_language(monkeypatch, django_capture_on_commit_callbacks):
    from apps.identity.infrastructure.models import User
    from apps.notifications.infrastructure.models import NotificationModel
    from apps.ordering.infrastructure.tasks import replenish_reminders

    user = User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10**7:07d}", status="active", full_name="Rep Test")
    product = Product.objects.create(id=uuid.uuid4(), status="published")
    for loc, name in (("uz", "Oltin Whey"), ("ru", "Золотой Whey"), ("en", "Gold Whey")):
        ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code=loc, name=name, slug=f"gold-{loc}-{uuid.uuid4().hex[:4]}")
    forecast = rp.Forecast(user.id, product.id, None, NOW - timedelta(days=27), 30, "default", "order:x1")
    monkeypatch.setattr(rp, "due", lambda now=None, customer_ids=None: [forecast])

    with django_capture_on_commit_callbacks(execute=True):
        replenish_reminders()
    with django_capture_on_commit_callbacks(execute=True):
        replenish_reminders()  # the same purchase again -> no second reminder

    rows = NotificationModel.objects.filter(recipient_id=user.id, kind="replenish_reminder")
    assert rows.count() == 1
    i18n = rows.get().i18n
    assert "Oltin Whey" in i18n["uz"]["title"] and "Золотой Whey" in i18n["ru"]["title"] and "Gold Whey" in i18n["en"]["title"]
    assert "kundan keyin tugaydi" in i18n["uz"]["body"]
    assert rows.get().link.startswith("/products/gold-uz-")


def test_my_replenishment_endpoint_lists_soonest_first(monkeypatch):
    from apps.identity.infrastructure.composition import _assign_default_customer_role
    from apps.identity.infrastructure.models import User
    from apps.stores.tests.interfaces.test_my_store_products import _authenticate_as

    user = User.objects.create(id=uuid.uuid4(), phone_number=f"+99891{uuid.uuid4().int % 10**7:07d}", status="active", full_name="Rep Api")
    _assign_default_customer_role(user.id)
    soon = Product.objects.create(id=uuid.uuid4(), status="published", nutrition_servings_per_container=30)
    later = Product.objects.create(id=uuid.uuid4(), status="published", nutrition_servings_per_container=30)
    gone = Product.objects.create(id=uuid.uuid4(), status="draft", nutrition_servings_per_container=30)
    for p in (soon, later, gone):
        ProductTranslation.objects.create(id=uuid.uuid4(), product=p, locale_code="uz", name=f"P {p.id.hex[:4]}", slug=f"p-{p.id.hex[:8]}")
    monkeypatch.setattr(rp, "purchases", lambda customer_ids=None, since=None: [
        _buy(user.id, later.id, 10), _buy(user.id, soon.id, 28), _buy(user.id, gone.id, 28)])
    _authenticate_as(monkeypatch, user)

    body = APIClient().get("/api/v1/orders/replenishment").json()
    assert [row["product"]["id"] for row in body["data"]] == [str(soon.id), str(later.id)]
    assert body["data"][0]["days_left"] <= 2
