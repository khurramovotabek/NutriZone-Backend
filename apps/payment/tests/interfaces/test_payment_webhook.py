"""
Phase 10b: Payment webhook tests.
"""
from __future__ import annotations

import threading
import unittest.mock as mock
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone as django_timezone
from rest_framework.test import APIClient

from apps.payment.domain.aggregates import Payment
from apps.payment.domain.value_objects import PaymentAmount
from apps.payment.infrastructure.gateways import FakeWebhookAuthenticator
from apps.payment.infrastructure.repositories import DjangoPaymentRepository
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


def _make_geo(city_code="WEBCITY1"):
    from apps.geo.infrastructure import models as geo_orm

    country, _ = geo_orm.Country.objects.get_or_create(code="UZ", defaults={"status": "active"})
    region, _ = geo_orm.Region.objects.get_or_create(country=country, code=f"{city_code}R", defaults={"status": "active"})
    city, _ = geo_orm.City.objects.get_or_create(region=region, code=city_code, defaults={"status": "active"})
    geo_orm.CityTranslation.objects.get_or_create(city=city, locale_code="en", defaults={"name": "Webhook City", "slug": "webhook-test-city"})
    return country, city


def _real_pending_payment(monkeypatch, phone_suffix, unit_amount=Decimal("45000.00")):
    from apps.identity.infrastructure import models as identity_orm
    from apps.geo.infrastructure import models as geo_orm
    from apps.pricing.infrastructure import models as pricing_orm
    from apps.ordering.infrastructure import composition as ordering_composition

    country, city = _make_geo()
    user_id = uuid.uuid4()
    identity_orm.User.objects.create(id=user_id, phone_number=f"+99892{phone_suffix:07d}", full_name="Webhook Customer", status="active")
    address = geo_orm.Address.objects.create(id=uuid.uuid4(), owner_type="user", owner_id=user_id, address_type="residential", country=country, city=city, line1=f"{phone_suffix} Webhook St")

    price_list, _ = pricing_orm.PriceListModel.objects.get_or_create(code="DEFAULT-UZS", defaults={"name": "Default", "currency": "UZS", "status": "active"})
    variant_id = uuid.uuid4()
    pricing_orm.PriceListEntryModel.objects.create(price_list=price_list, product_variant_id=variant_id, base_price_amount=unit_amount)

    client = _client_as(monkeypatch, user_id)
    r = client.post("/api/v1/cart/", {"cart_type": "authenticated"}, format="json")
    cart = r.json()["data"]
    r = client.post(f"/api/v1/cart/{cart['code']}/items", {"product_variant_id": str(variant_id), "quantity": 1}, format="json", HTTP_X_CART_TOKEN=cart["token"])
    item_id = r.json()["data"]["items"][0]["id"]
    client.post(f"/api/v1/cart/{cart['code']}/items/{item_id}/price", {}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
    r = client.post(f"/api/v1/cart/{cart['code']}/checkout", {"shipping_address_id": str(address.id)}, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
    order_id = r.json()["data"]["id"]

    provider_reference = f"provider-ref-{uuid.uuid4().hex[:12]}"
    payment, _ = Payment.create(uuid.uuid4(), order_id, user_id, PaymentAmount(unit_amount, "UZS"), "fake", django_timezone.now())
    payment.mark_pending(provider_reference, django_timezone.now())
    DjangoPaymentRepository().save(payment)
    ordering_composition.build_attach_payment_reference(user_id).execute(order_id=order_id, payment_id=payment.id, amount=unit_amount)

    return order_id, payment.id, provider_reference, unit_amount


def _webhook_client() -> APIClient:
    return APIClient()


def _call_webhook(provider_reference, status, amount, currency="UZS", idempotency_key=None, secret=FakeWebhookAuthenticator.TEST_SECRET):
    headers = {"HTTP_IDEMPOTENCY_KEY": idempotency_key or str(uuid.uuid4())}
    if secret is not None:
        headers["HTTP_X_FAKE_WEBHOOK_SECRET"] = secret
    return _webhook_client().post("/api/v1/payments/webhook", {"provider_reference": provider_reference, "status": status, "amount": str(amount), "currency": currency}, format="json", **headers)


def _use_fake_authenticator(monkeypatch):
    from apps.payment.infrastructure import composition as payment_composition

    monkeypatch.setattr(payment_composition, "build_webhook_authenticator", lambda: FakeWebhookAuthenticator())


class TestWebhookAuthentication:
    def test_missing_signature_rejected(self, monkeypatch):
        order_id, payment_id, provider_reference, amount = _real_pending_payment(monkeypatch, 1)
        r = _call_webhook(provider_reference, "succeeded", amount, secret=None)
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "INVALID_SIGNATURE"

    def test_wrong_signature_rejected(self, monkeypatch):
        _use_fake_authenticator(monkeypatch)
        order_id, payment_id, provider_reference, amount = _real_pending_payment(monkeypatch, 2)
        r = _call_webhook(provider_reference, "succeeded", amount, secret="wrong-secret")
        assert r.status_code == 401

    def test_valid_signature_accepted(self, monkeypatch):
        _use_fake_authenticator(monkeypatch)
        order_id, payment_id, provider_reference, amount = _real_pending_payment(monkeypatch, 3)
        r = _call_webhook(provider_reference, "succeeded", amount)
        assert r.status_code == 200


class TestWebhookProviderReference:
    def test_unknown_provider_reference_rejected(self, monkeypatch):
        _use_fake_authenticator(monkeypatch)
        r = _call_webhook("does-not-exist-anywhere", "succeeded", "1.00")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "PAYMENT_NOT_FOUND"

    def test_provider_reference_attack_does_not_affect_other_payment(self, monkeypatch):
        order_a, payment_a_id, ref_a, amount_a = _real_pending_payment(monkeypatch, 4)
        order_b, payment_b_id, ref_b, amount_b = _real_pending_payment(monkeypatch, 5)
        _use_fake_authenticator(monkeypatch)

        r = _call_webhook(ref_a, "succeeded", amount_a)
        assert r.status_code == 200
        assert r.json()["data"]["id"] == str(payment_a_id)

        payment_b = DjangoPaymentRepository().get_by_id(payment_b_id)
        assert payment_b.status.value == "pending"


class TestWebhookAmountCurrencyVerification:
    def test_amount_mismatch_rejected(self, monkeypatch):
        _use_fake_authenticator(monkeypatch)
        order_id, payment_id, provider_reference, amount = _real_pending_payment(monkeypatch, 6, Decimal("60000.00"))
        r = _call_webhook(provider_reference, "succeeded", "1.00")
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "PAYMENT_AMOUNT_MISMATCH"

        payment = DjangoPaymentRepository().get_by_id(payment_id)
        assert payment.status.value == "pending"

    def test_currency_mismatch_rejected(self, monkeypatch):
        _use_fake_authenticator(monkeypatch)
        order_id, payment_id, provider_reference, amount = _real_pending_payment(monkeypatch, 7)
        r = _call_webhook(provider_reference, "succeeded", amount, currency="USD")
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "PAYMENT_AMOUNT_MISMATCH"

    def test_financial_tampering_fields_ignored(self, monkeypatch):
        _use_fake_authenticator(monkeypatch)
        order_id, payment_id, provider_reference, amount = _real_pending_payment(monkeypatch, 8)
        r = _webhook_client().post(
            "/api/v1/payments/webhook",
            {"provider_reference": provider_reference, "status": "succeeded", "amount": str(amount), "currency": "UZS", "total": "1.00", "subtotal": "1.00", "order_total": "1.00"},
            format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()), HTTP_X_FAKE_WEBHOOK_SECRET=FakeWebhookAuthenticator.TEST_SECRET,
        )
        assert r.status_code == 200
        assert Decimal(r.json()["data"]["amount"]) == amount


class TestWebhookSuccessAndFailure:
    def test_successful_webhook_confirms_order(self, monkeypatch):
        from apps.ordering.infrastructure import models as ordering_orm

        _use_fake_authenticator(monkeypatch)
        order_id, payment_id, provider_reference, amount = _real_pending_payment(monkeypatch, 9)
        r = _call_webhook(provider_reference, "succeeded", amount)
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "succeeded"

        order_row = ordering_orm.OrderModel.objects.get(id=order_id)
        assert order_row.status == "confirmed"

    def test_failed_webhook_does_not_confirm_order(self, monkeypatch):
        from apps.ordering.infrastructure import models as ordering_orm

        _use_fake_authenticator(monkeypatch)
        order_id, payment_id, provider_reference, amount = _real_pending_payment(monkeypatch, 10)
        r = _call_webhook(provider_reference, "failed", amount)
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "failed"

        order_row = ordering_orm.OrderModel.objects.get(id=order_id)
        assert order_row.status == "pending_payment"


class TestWebhookTerminalStates:
    def test_duplicate_success_webhook_is_harmless_replay(self, monkeypatch):
        _use_fake_authenticator(monkeypatch)
        order_id, payment_id, provider_reference, amount = _real_pending_payment(monkeypatch, 11)
        r1 = _call_webhook(provider_reference, "succeeded", amount)
        r2 = _call_webhook(provider_reference, "succeeded", amount)
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r2.json()["data"]["status"] == "succeeded"

    def test_failure_webhook_after_success_is_rejected_not_applied(self, monkeypatch):
        _use_fake_authenticator(monkeypatch)
        order_id, payment_id, provider_reference, amount = _real_pending_payment(monkeypatch, 12)
        _call_webhook(provider_reference, "succeeded", amount)

        r = _call_webhook(provider_reference, "failed", amount)
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "succeeded"

        payment = DjangoPaymentRepository().get_by_id(payment_id)
        assert payment.status.value == "succeeded"


class TestWebhookIdempotency:
    def test_missing_idempotency_key_rejected(self, monkeypatch):
        _use_fake_authenticator(monkeypatch)
        order_id, payment_id, provider_reference, amount = _real_pending_payment(monkeypatch, 13)
        r = _webhook_client().post(
            "/api/v1/payments/webhook", {"provider_reference": provider_reference, "status": "succeeded", "amount": str(amount), "currency": "UZS"},
            format="json", HTTP_X_FAKE_WEBHOOK_SECRET=FakeWebhookAuthenticator.TEST_SECRET,
        )
        assert r.status_code == 422

    def test_same_key_different_payload_conflicts(self, monkeypatch):
        _use_fake_authenticator(monkeypatch)
        order_id, payment_id, provider_reference, amount = _real_pending_payment(monkeypatch, 14)
        key = str(uuid.uuid4())
        r1 = _call_webhook(provider_reference, "succeeded", amount, idempotency_key=key)
        assert r1.status_code == 200
        r2 = _call_webhook(provider_reference, "failed", amount, idempotency_key=key)
        assert r2.status_code == 409
        assert r2.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"


class TestWebhookRollback:
    def test_forced_failure_after_payment_mutation_rolls_back_everything(self, monkeypatch):
        from apps.ordering.infrastructure import composition as ordering_composition
        from apps.ordering.infrastructure import models as ordering_orm
        from apps.payment.infrastructure import models as payment_orm

        _use_fake_authenticator(monkeypatch)
        order_id, payment_id, provider_reference, amount = _real_pending_payment(monkeypatch, 15)

        def _boom(customer_id):
            class _Boom:
                def execute(self, **kwargs):
                    raise RuntimeError("Simulated failure: Ordering notification unavailable.")

            return _Boom()

        monkeypatch.setattr(ordering_composition, "build_update_payment_status", _boom)

        r = _call_webhook(provider_reference, "succeeded", amount)
        assert r.status_code == 500  # the injected failure surfaces as a real server error, not a fabricated success

        payment = DjangoPaymentRepository().get_by_id(payment_id)
        assert payment.status.value == "pending"

        order_row = ordering_orm.OrderModel.objects.get(id=order_id)
        assert order_row.status == "pending_payment"

        events_after = payment_orm.PaymentOutboxEvent.objects.filter(event_type="PaymentSucceeded").count()
        assert events_after == 0


class TestWebhookConcurrency:
    @pytest.mark.django_db(transaction=True)
    def test_concurrent_identical_webhooks_produce_exactly_one_transition(self, monkeypatch):
        from django.db import connections
        from apps.payment.infrastructure import composition as payment_composition
        from apps.ordering.infrastructure import composition as ordering_composition
        from apps.geo.infrastructure import models as geo_orm
        from apps.identity.infrastructure import models as identity_orm
        from apps.pricing.infrastructure import models as pricing_orm

        # monkeypatch restores both after the test -- raw assignments leaked an allow-all resolver and the fake webhook authenticator into every later test.
        monkeypatch.setattr(HasPermissionCode, "resolver", _AllowAllResolver())
        monkeypatch.setattr(payment_composition, "build_webhook_authenticator", lambda: FakeWebhookAuthenticator())

        country, _ = geo_orm.Country.objects.get_or_create(code="UZ", defaults={"status": "active"})
        region, _ = geo_orm.Region.objects.get_or_create(country=country, code="WHCONCR", defaults={"status": "active"})
        city, _ = geo_orm.City.objects.get_or_create(region=region, code="WHCONC1", defaults={"status": "active"})
        geo_orm.CityTranslation.objects.get_or_create(city=city, locale_code="en", defaults={"name": "Concurrency City", "slug": "wh-concurrency-city"})

        user_id = uuid.uuid4()
        identity_orm.User.objects.create(id=user_id, phone_number="+998930000099", full_name="Concurrency Customer", status="active")
        address = geo_orm.Address.objects.create(id=uuid.uuid4(), owner_type="user", owner_id=user_id, address_type="residential", country=country, city=city, line1="Concurrency St")

        price_list, _ = pricing_orm.PriceListModel.objects.get_or_create(code="DEFAULT-UZS", defaults={"name": "Default", "currency": "UZS", "status": "active"})
        variant_id = uuid.uuid4()
        pricing_orm.PriceListEntryModel.objects.create(price_list=price_list, product_variant_id=variant_id, base_price_amount=Decimal("30000.00"))

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

        provider_reference = f"provider-ref-concurrency-{uuid.uuid4().hex[:8]}"
        payment, _ = Payment.create(uuid.uuid4(), order_id, user_id, PaymentAmount(Decimal("30000.00"), "UZS"), "fake", django_timezone.now())
        payment.mark_pending(provider_reference, django_timezone.now())
        DjangoPaymentRepository().save(payment)
        ordering_composition.build_attach_payment_reference(user_id).execute(order_id=order_id, payment_id=payment.id, amount=Decimal("30000.00"))

        same_key = str(uuid.uuid4())
        results = []

        def worker():
            connections.close_all()
            r = APIClient().post(
                "/api/v1/payments/webhook",
                {"provider_reference": provider_reference, "status": "succeeded", "amount": "30000.00", "currency": "UZS"},
                format="json", HTTP_IDEMPOTENCY_KEY=same_key, HTTP_X_FAKE_WEBHOOK_SECRET=FakeWebhookAuthenticator.TEST_SECRET,
            )
            results.append(r.status_code)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sorted(results) == [200, 409]
        final_payment = DjangoPaymentRepository().get_by_id(payment.id)
        assert final_payment.status.value == "succeeded"
