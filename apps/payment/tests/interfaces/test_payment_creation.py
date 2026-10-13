"""
Phase 10: Payment application/interface tests.

Builds a real Order via the actual, already-verified checkout chain
(Cart -> Pricing -> CheckoutCartView) rather than fabricating Order
rows directly, so these tests exercise the real integration boundary,
not a shortcut around it.
"""
from __future__ import annotations

import threading
import unittest.mock as mock
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.payment.infrastructure.gateways import FakePaymentGateway
from common.permissions import HasPermissionCode

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class _AllowAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return True


def _client_as(monkeypatch, user_id) -> APIClient:
    monkeypatch.setattr(HasPermissionCode, "resolver", _AllowAllResolver())
    fake_user = SimpleNamespace(id=user_id, is_authenticated=True, store_ids=set())
    monkeypatch.setattr("apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate", lambda self, request: (fake_user, None))
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer fake")
    return client


def _make_geo(country_code="UZ", city_code="PAYCITY1"):
    from apps.geo.infrastructure import models as geo_orm

    country, _ = geo_orm.Country.objects.get_or_create(code=country_code, defaults={"status": "active"})
    region, _ = geo_orm.Region.objects.get_or_create(country=country, code=f"{city_code}R", defaults={"status": "active"})
    city, _ = geo_orm.City.objects.get_or_create(region=region, code=city_code, defaults={"status": "active"})
    geo_orm.CityTranslation.objects.get_or_create(city=city, locale_code="en", defaults={"name": "Test City", "slug": "test-city-pay"})
    return country, city


def _make_user(user_id, phone_suffix):
    from apps.identity.infrastructure import models as identity_orm

    return identity_orm.User.objects.create(id=user_id, phone_number=f"+99891{phone_suffix:07d}", full_name="Test Customer", status="active")


def _make_address(user_id, country, city, line1="1 Pay Street"):
    from apps.geo.infrastructure import models as geo_orm

    return geo_orm.Address.objects.create(id=uuid.uuid4(), owner_type="user", owner_id=user_id, address_type="residential", country=country, city=city, line1=line1)


def _make_active_price_list_entry(unit_amount=Decimal("50000.00")):
    from apps.pricing.infrastructure import models as pricing_orm

    price_list, _ = pricing_orm.PriceListModel.objects.get_or_create(code="DEFAULT-UZS", defaults={"name": "Default", "currency": "UZS", "status": "active"})
    variant_id = uuid.uuid4()
    pricing_orm.PriceListEntryModel.objects.create(price_list=price_list, product_variant_id=variant_id, base_price_amount=unit_amount)
    return variant_id


def _real_order(monkeypatch, phone_suffix, unit_amount=Decimal("50000.00"), quantity=1):
    country, city = _make_geo()
    user_id = uuid.uuid4()
    _make_user(user_id, phone_suffix)
    address = _make_address(user_id, country, city)
    variant_id = _make_active_price_list_entry(unit_amount)

    client = _client_as(monkeypatch, user_id)
    r = client.post("/api/v1/cart/", {"cart_type": "authenticated"}, format="json")
    cart = r.json()["data"]
    r = client.post(f"/api/v1/cart/{cart['code']}/items", {"product_variant_id": str(variant_id), "quantity": quantity}, format="json", HTTP_X_CART_TOKEN=cart["token"])
    item_id = r.json()["data"]["items"][0]["id"]
    client.post(f"/api/v1/cart/{cart['code']}/items/{item_id}/price", {}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
    r = client.post(f"/api/v1/cart/{cart['code']}/checkout", {"shipping_address_id": str(address.id)}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
    assert r.status_code == 201, r.json()
    order_id = r.json()["data"]["id"]
    return client, user_id, order_id, unit_amount * quantity


def _use_fake_gateway(monkeypatch):
    from apps.payment.infrastructure import composition as payment_composition

    monkeypatch.setattr(payment_composition, "build_payment_gateway", lambda: FakePaymentGateway())


class TestPaymentHappyPath:
    def test_payment_creation_succeeds_with_authoritative_amount(self, monkeypatch):
        _use_fake_gateway(monkeypatch)
        client, user_id, order_id, expected_amount = _real_order(monkeypatch, 1, Decimal("50000.00"), quantity=2)

        r = client.post("/api/v1/payments/", {"order_id": order_id, "provider": "fake"}, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        assert r.status_code == 201, r.json()
        data = r.json()["data"]
        assert data["status"] == "succeeded"
        assert Decimal(data["amount"]) == expected_amount
        assert data["currency"] == "UZS"

    def test_successful_payment_confirms_order(self, monkeypatch):
        from apps.ordering.infrastructure import models as ordering_orm

        _use_fake_gateway(monkeypatch)
        client, user_id, order_id, _ = _real_order(monkeypatch, 2)

        r = client.post("/api/v1/payments/", {"order_id": order_id, "provider": "fake"}, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        assert r.status_code == 201

        order_row = ordering_orm.OrderModel.objects.get(id=order_id)
        assert order_row.status == "confirmed"


class TestPaymentFinancialIntegrity:
    def test_client_supplied_amount_fields_are_ignored(self, monkeypatch):
        _use_fake_gateway(monkeypatch)
        client, user_id, order_id, expected_amount = _real_order(monkeypatch, 3, Decimal("60000.00"))

        malicious_body = {"order_id": order_id, "provider": "fake", "amount": "1.00", "currency": "USD", "total": "1.00"}
        r = client.post("/api/v1/payments/", malicious_body, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        assert r.status_code == 201
        data = r.json()["data"]
        assert Decimal(data["amount"]) == expected_amount
        assert data["currency"] == "UZS"

    def test_cannot_pay_for_other_customers_order(self, monkeypatch):
        _use_fake_gateway(monkeypatch)
        _, user_a, order_id, _ = _real_order(monkeypatch, 4)

        client_b = _client_as(monkeypatch, uuid.uuid4())
        r = client_b.post("/api/v1/payments/", {"order_id": order_id, "provider": "fake"}, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        assert r.status_code == 403


class TestPaymentIdempotency:
    def test_same_key_replays_payment(self, monkeypatch):
        from apps.payment.infrastructure import models as payment_orm

        _use_fake_gateway(monkeypatch)
        client, user_id, order_id, _ = _real_order(monkeypatch, 5)
        key = str(uuid.uuid4())

        before = payment_orm.PaymentModel.objects.count()
        r1 = client.post("/api/v1/payments/", {"order_id": order_id, "provider": "fake"}, format="json", HTTP_IDEMPOTENCY_KEY=key)
        r2 = client.post("/api/v1/payments/", {"order_id": order_id, "provider": "fake"}, format="json", HTTP_IDEMPOTENCY_KEY=key)
        after = payment_orm.PaymentModel.objects.count()

        assert r1.status_code == 201
        assert r2.json()["data"]["id"] == r1.json()["data"]["id"]
        assert after == before + 1

    def test_same_key_different_order_conflicts(self, monkeypatch):
        _use_fake_gateway(monkeypatch)
        client, user_id, order_id_1, _ = _real_order(monkeypatch, 6)
        country, city = _make_geo()
        address = _make_address(user_id, country, city, "Second address")
        variant_id = _make_active_price_list_entry(Decimal("10000.00"))
        r = client.post("/api/v1/cart/", {"cart_type": "authenticated"}, format="json")
        cart = r.json()["data"]
        r = client.post(f"/api/v1/cart/{cart['code']}/items", {"product_variant_id": str(variant_id), "quantity": 1}, format="json", HTTP_X_CART_TOKEN=cart["token"])
        item_id = r.json()["data"]["items"][0]["id"]
        client.post(f"/api/v1/cart/{cart['code']}/items/{item_id}/price", {}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        r = client.post(f"/api/v1/cart/{cart['code']}/checkout", {"shipping_address_id": str(address.id)}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        order_id_2 = r.json()["data"]["id"]

        key = str(uuid.uuid4())
        r1 = client.post("/api/v1/payments/", {"order_id": order_id_1, "provider": "fake"}, format="json", HTTP_IDEMPOTENCY_KEY=key)
        assert r1.status_code == 201
        r2 = client.post("/api/v1/payments/", {"order_id": order_id_2, "provider": "fake"}, format="json", HTTP_IDEMPOTENCY_KEY=key)
        assert r2.status_code == 409
        assert r2.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"

    def test_missing_idempotency_key_rejected(self, monkeypatch):
        _use_fake_gateway(monkeypatch)
        client, user_id, order_id, _ = _real_order(monkeypatch, 7)
        r = client.post("/api/v1/payments/", {"order_id": order_id, "provider": "fake"}, format="json")
        assert r.status_code == 422

    def test_cross_customer_key_isolation(self, monkeypatch):
        """
        Uses properly-scoped mock.patch (re-applied immediately before
        each request) rather than monkeypatch.setattr, which is a
        global last-writer-wins patch and cannot represent two
        simultaneously-relevant identities across two separate
        _client_as() calls in one test function -- the same known
        limitation already documented and fixed this way in Phase
        09.6/09.7c.
        """
        _use_fake_gateway(monkeypatch)
        monkeypatch.setattr(HasPermissionCode, "resolver", _AllowAllResolver())

        def _order_as(user_id, phone_suffix):
            fake_user = SimpleNamespace(id=user_id, is_authenticated=True, store_ids=set())
            with mock.patch("apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate", lambda self, request: (fake_user, None)):
                country, city = _make_geo()
                _make_user(user_id, phone_suffix)
                address = _make_address(user_id, country, city)
                variant_id = _make_active_price_list_entry()
                client = APIClient()
                client.credentials(HTTP_AUTHORIZATION="Bearer fake")
                r = client.post("/api/v1/cart/", {"cart_type": "authenticated"}, format="json")
                cart = r.json()["data"]
                r = client.post(f"/api/v1/cart/{cart['code']}/items", {"product_variant_id": str(variant_id), "quantity": 1}, format="json", HTTP_X_CART_TOKEN=cart["token"])
                item_id = r.json()["data"]["items"][0]["id"]
                client.post(f"/api/v1/cart/{cart['code']}/items/{item_id}/price", {}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
                r = client.post(f"/api/v1/cart/{cart['code']}/checkout", {"shipping_address_id": str(address.id)}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
                return r.json()["data"]["id"]

        user_a, user_b = uuid.uuid4(), uuid.uuid4()
        order_a = _order_as(user_a, 8)
        order_b = _order_as(user_b, 9)
        key = str(uuid.uuid4())

        def _pay_as(user_id, order_id):
            fake_user = SimpleNamespace(id=user_id, is_authenticated=True, store_ids=set())
            with mock.patch("apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate", lambda self, request: (fake_user, None)):
                client = APIClient()
                client.credentials(HTTP_AUTHORIZATION="Bearer fake")
                return client.post("/api/v1/payments/", {"order_id": order_id, "provider": "fake"}, format="json", HTTP_IDEMPOTENCY_KEY=key)

        r_a = _pay_as(user_a, order_a)
        r_b = _pay_as(user_b, order_b)
        assert r_a.status_code == 201
        assert r_b.status_code == 201
        assert r_a.json()["data"]["id"] != r_b.json()["data"]["id"]


class TestPaymentFailure:
    def test_gateway_failure_marks_payment_and_order_correctly(self, monkeypatch):
        from apps.payment.infrastructure import composition as payment_composition
        from apps.ordering.infrastructure import models as ordering_orm

        client, user_id, order_id, _ = _real_order(monkeypatch, 10)

        class _AlwaysFailGateway(FakePaymentGateway):
            def create_charge(self, amount, currency, order_reference, idempotency_key):
                from apps.payment.application.gateway import GatewayChargeResult

                return GatewayChargeResult(provider_reference=f"fake-fail-{uuid.uuid4().hex[:8]}", status="failed")

        monkeypatch.setattr(payment_composition, "build_payment_gateway", lambda: _AlwaysFailGateway())

        r = client.post("/api/v1/payments/", {"order_id": order_id, "provider": "fake"}, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        assert r.status_code == 201
        assert r.json()["data"]["status"] == "failed"

        order_row = ordering_orm.OrderModel.objects.get(id=order_id)
        assert order_row.status != "confirmed"

    def test_cannot_pay_already_confirmed_order(self, monkeypatch):
        _use_fake_gateway(monkeypatch)
        client, user_id, order_id, _ = _real_order(monkeypatch, 11)
        client.post("/api/v1/payments/", {"order_id": order_id, "provider": "fake"}, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))

        r = client.post("/api/v1/payments/", {"order_id": order_id, "provider": "fake"}, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "ORDER_NOT_PAYABLE"


class TestPaymentConcurrency:
    @pytest.mark.django_db(transaction=True)
    def test_concurrent_same_key_payment_creates_exactly_one_payment(self, monkeypatch):
        from django.db import connections
        from apps.payment.infrastructure import composition as payment_composition
        from apps.payment.infrastructure import models as payment_orm

        monkeypatch.setattr(HasPermissionCode, "resolver", _AllowAllResolver())  # restored after the test (a raw assignment leaked into every later test)
        country, city = _make_geo()
        user_id = uuid.uuid4()
        _make_user(user_id, 12)
        address = _make_address(user_id, country, city)
        variant_id = _make_active_price_list_entry()

        fake_user = SimpleNamespace(id=user_id, is_authenticated=True, store_ids=set())
        with mock.patch("apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate", lambda self, request: (fake_user, None)):
            setup_client = APIClient()
            setup_client.credentials(HTTP_AUTHORIZATION="Bearer fake")
            r = setup_client.post("/api/v1/cart/", {"cart_type": "authenticated"}, format="json")
            cart = r.json()["data"]
            r = setup_client.post(f"/api/v1/cart/{cart['code']}/items", {"product_variant_id": str(variant_id), "quantity": 1}, format="json", HTTP_X_CART_TOKEN=cart["token"])
            item_id = r.json()["data"]["items"][0]["id"]
            setup_client.post(f"/api/v1/cart/{cart['code']}/items/{item_id}/price", {}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
            r = setup_client.post(f"/api/v1/cart/{cart['code']}/checkout", {"shipping_address_id": str(address.id)}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
            order_id = r.json()["data"]["id"]

        monkeypatch.setattr(payment_composition, "build_payment_gateway", lambda: FakePaymentGateway())
        same_key = str(uuid.uuid4())
        results = []

        def worker():
            connections.close_all()
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION="Bearer fake")
            r = client.post("/api/v1/payments/", {"order_id": order_id, "provider": "fake"}, format="json", HTTP_IDEMPOTENCY_KEY=same_key)
            results.append(r.status_code)

        # One patch around both threads: mock.patch is not thread-safe -- threads patching the same attribute
        # can restore each other's fake, leaking a fake login into every later test.
        with mock.patch("apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate", lambda self, request: (fake_user, None)):
            threads = [threading.Thread(target=worker) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert sorted(results) == [201, 409]
        assert payment_orm.PaymentModel.objects.filter(order_id=order_id).count() == 1
