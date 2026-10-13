"""
Coupon rules end to end: limits, one use per customer, minimum order, checkout records the use (so limits really
apply), and the premium coupon admin (create with validation, card, pause / activate / revoke, code generator).
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User as StaffUser
from django.test import Client
from django.utils import timezone

from apps.cart.tests.interfaces.test_checkout_order_creation import (
    _client_as,
    _make_active_price_list_entry,
    _make_address,
    _make_geo,
    _make_user,
    _priced_cart,
)
from apps.pricing.infrastructure import coupon_rules
from apps.pricing.infrastructure.models import CouponModel, CouponRedemptionModel

pytestmark = pytest.mark.django_db


def _coupon(code=None, **kw):
    data = {"code": code or f"T{uuid.uuid4().hex[:7].upper()}", "coupon_type": "coupon", "discount_value_type": "percentage", "discount_percentage": Decimal("10"), "status": "active"}
    data.update(kw)
    return CouponModel.objects.create(**data)


def _checkout(client, cart, address):
    return client.post(f"/api/v1/cart/{cart['code']}/checkout", {"shipping_address_id": str(address.id)}, format="json",
                       HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))


def _apply(client, cart, code):
    return client.post(f"/api/v1/cart/{cart['code']}/checkout-coupon", {"coupon_code": code}, format="json", HTTP_X_CART_TOKEN=cart["token"])


class TestRules:
    def test_problem_codes(self):
        now = timezone.now()
        assert coupon_rules.problem(_coupon(status="draft"))[0] == "COUPON_NOT_ACTIVE"
        assert coupon_rules.problem(_coupon(validity_starts_at=now - timedelta(days=5), validity_ends_at=now - timedelta(days=1)))[0] == "COUPON_EXPIRED"
        assert coupon_rules.problem(_coupon(min_order_amount=Decimal("300000")), subtotal=Decimal("100000"))[0] == "COUPON_MIN_ORDER"
        c = _coupon(max_redemptions=1, max_per_customer=1)
        user = uuid.uuid4()
        CouponRedemptionModel.objects.create(coupon=c, redeemed_by=user, order_reference="ORD-1", redeemed_at=now)
        assert coupon_rules.problem(c)[0] == "COUPON_EXHAUSTED"
        c2 = _coupon(max_per_customer=1)
        CouponRedemptionModel.objects.create(coupon=c2, redeemed_by=user, order_reference="ORD-2", redeemed_at=now)
        assert coupon_rules.problem(c2, customer_id=user)[0] == "COUPON_ALREADY_USED" and coupon_rules.problem(c2, customer_id=uuid.uuid4()) is None
        assert coupon_rules.discount_amount(_coupon(discount_value_type="fixed_amount", discount_percentage=None, discount_fixed_amount=Decimal("50000")), Decimal("30000")) == Decimal("30000")


class TestCheckout:
    def test_checkout_records_the_use_and_the_second_order_is_refused(self, monkeypatch):
        country, city = _make_geo(city_code="CPNCITY1")
        user_id = uuid.uuid4()
        _make_user(user_id, 71)
        address = _make_address(user_id, country, city)
        variant_id = _make_active_price_list_entry(Decimal("100000.00"))
        coupon = _coupon(code="ONCEONLY", max_per_customer=1)
        client = _client_as(monkeypatch, user_id)

        cart, _i, _s = _priced_cart(client, variant_id)
        assert _apply(client, cart, "onceonly").status_code == 200
        r = _checkout(client, cart, address)
        assert r.status_code == 201, r.json()
        assert CouponRedemptionModel.objects.filter(coupon=coupon, redeemed_by=user_id, order_reference=r.json()["data"]["order_number"]).exists()
        from apps.ordering.infrastructure.models import OrderLineItemModel

        assert sum(OrderLineItemModel.objects.filter(order_id=r.json()["data"]["id"]).values_list("discount_amount", flat=True)) == Decimal("10000.00")

        cart2, _i, _s = _priced_cart(client, variant_id)
        refused = _apply(client, cart2, "ONCEONLY")
        assert refused.status_code == 409 and "already used" in refused.json()["error"]["message"]

    def test_min_order_is_checked_when_applying(self, monkeypatch):
        user_id = uuid.uuid4()
        _make_user(user_id, 72)
        variant_id = _make_active_price_list_entry(Decimal("40000.00"))
        _coupon(code="BIGBASKET", min_order_amount=Decimal("300000"))
        client = _client_as(monkeypatch, user_id)
        cart, _i, _s = _priced_cart(client, variant_id)
        r = _apply(client, cart, "BIGBASKET")
        assert r.status_code == 409 and "at least" in r.json()["error"]["message"]


@pytest.fixture
def boss():
    client = Client()
    client.force_login(StaffUser.objects.create_superuser(username=f"cpn_{uuid.uuid4().hex[:6]}", password="x-pass-12345"))
    return client


class TestAdmin:
    def test_create_validate_and_card(self, boss):
        assert boss.get("/django-admin/pricing/couponmodel/add/").status_code == 200
        bad = boss.post("/django-admin/pricing/couponmodel/add/", {"code": "a b", "discount_kind": "percentage", "value": "150", "stacking_mode": "exclusive"})
        assert bad.status_code == 200 and not CouponModel.objects.filter(code="AB").exists()
        r = boss.post("/django-admin/pricing/couponmodel/add/", {"code": "tgoct", "title": "Telegram", "discount_kind": "fixed_amount", "value": "20000", "min_order_amount": "200000",
                                                                  "max_redemptions": "50", "max_per_customer": "1", "stacking_mode": "exclusive", "activate": "on",
                                                                  "ends": (timezone.localtime() + timedelta(days=10)).strftime("%Y-%m-%dT%H:%M")})
        c = CouponModel.objects.get(code="TGOCT")
        assert r.status_code == 302 and c.status == "active" and c.discount_fixed_amount == Decimal("20000") and c.validity_starts_at and c.max_per_customer == 1
        for url in (f"/django-admin/pricing/couponmodel/{c.pk}/change/", f"/django-admin/pricing/couponmodel/{c.pk}/edit/", "/django-admin/pricing/couponmodel/?state=active",
                    "/django-admin/pricing/couponmodel/?state=expired"):
            assert boss.get(url).status_code == 200, url
        assert boss.get("/django-admin/pricing/couponmodel/generate-code/?prefix=TG").json()["code"].startswith("TG")

    def test_pause_activate_revoke(self, boss):
        c = _coupon()
        boss.post(f"/django-admin/pricing/couponmodel/{c.pk}/status/", {"to": "draft"})
        assert CouponModel.objects.get(pk=c.pk).status == "draft"
        boss.post(f"/django-admin/pricing/couponmodel/{c.pk}/status/", {"to": "active"})
        assert CouponModel.objects.get(pk=c.pk).status == "active"
        boss.post(f"/django-admin/pricing/couponmodel/{c.pk}/status/", {"to": "revoke"})
        assert CouponModel.objects.get(pk=c.pk).status == "revoked"
