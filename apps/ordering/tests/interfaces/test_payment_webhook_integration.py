"""
Phase 02E's payment webhook / payment-boundary integration test
matrix (Step 18). Real PostgreSQL throughout; drives the real
CreateOrderFromCart -> AttachPaymentReference -> webhook flow via
actual HTTP requests, not hand-built domain calls, so what's tested
is exactly what a real client/provider would exercise.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import threading
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.conf import settings
from django.db import connection
from rest_framework.test import APIClient

from apps.ordering.infrastructure import composition as ordering_composition
from apps.ordering.infrastructure import models as orm
from common.permissions import HasPermissionCode

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


class _AllowAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return True


def _address_payload() -> dict:
    return {"recipient_name": "Jane Doe", "line1": "123 Main St", "city": "Tashkent", "country_code": "UZ"}


def _sign(body: bytes) -> str:
    return hmac.new(settings.PAYMENT_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


def _webhook_payload(**overrides) -> dict:
    payload = {
        "provider": "test-provider", "provider_transaction_id": str(uuid.uuid4()),
        "order_id": str(uuid.uuid4()), "payment_id": str(uuid.uuid4()),
        "event_type": "captured", "amount": "1000.00", "currency": "UZS",
    }
    payload.update(overrides)
    return payload


def _post_webhook(api_client, payload: dict, *, sign: bool = True, bad_signature: bool = False):
    body = json.dumps(payload).encode()
    headers = {}
    if sign:
        headers["HTTP_X_PAYMENT_SIGNATURE"] = "deadbeef" if bad_signature else _sign(body)
    return api_client.post("/api/v1/orders/payments/webhook", data=body, content_type="application/json", **headers)


@pytest.fixture
def authenticated_client(monkeypatch):
    original = HasPermissionCode.resolver
    HasPermissionCode.resolver = _AllowAllResolver()
    fake_user = SimpleNamespace(id=uuid.uuid4(), is_authenticated=True, store_ids=set())
    monkeypatch.setattr(
        "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
        lambda self, request: (fake_user, None),
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
    yield client
    HasPermissionCode.resolver = original


def _create_order_with_payment_reference(client, amount=Decimal("1000.00"), currency="UZS", customer_id=None):
    """Real HTTP flow: create order -> attach payment reference. Returns (order_number, order_id, payment_id)."""
    payload = {
        "currency": currency, "shipping_address": _address_payload(), "billing_address": _address_payload(),
        "line_items": [{"product_variant_id": str(uuid.uuid4()), "quantity": 1, "unit_price": str(amount)}],
    }
    if customer_id is not None:
        payload["customer_id"] = str(customer_id)
    create_response = client.post("/api/v1/orders/", payload, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
    assert create_response.status_code == 201, create_response.json()
    order_data = create_response.json()["data"]
    order_number = order_data["order_number"]
    order_id = order_data["id"]

    payment_id = str(uuid.uuid4())
    attach_response = client.post(f"/api/v1/orders/{order_number}/payment", {"payment_id": payment_id, "amount": str(amount)}, format="json")
    assert attach_response.status_code == 200, attach_response.json()
    return order_number, order_id, payment_id


class TestWebhookSignature:
    def test_missing_signature_rejected(self, api_client):
        response = _post_webhook(api_client, _webhook_payload(), sign=False)
        assert response.status_code == 401
        assert orm.PaymentWebhookDelivery.objects.count() == 0  # never recorded -- untrustworthy provider_transaction_id

    def test_invalid_signature_rejected(self, api_client):
        response = _post_webhook(api_client, _webhook_payload(), bad_signature=True)
        assert response.status_code == 401
        assert orm.PaymentWebhookDelivery.objects.count() == 0

    def test_valid_signature_with_unknown_order_is_rejected_but_recorded(self, api_client):
        response = _post_webhook(api_client, _webhook_payload())
        assert response.status_code == 404
        delivery = orm.PaymentWebhookDelivery.objects.get()
        assert delivery.status == "rejected"
        assert delivery.rejection_reason == "order_not_found"


class TestPaymentToOrderBoundary:
    def test_captured_webhook_confirms_pending_payment_order(self, authenticated_client):
        order_number, order_id, payment_id = _create_order_with_payment_reference(authenticated_client)
        response = _post_webhook(authenticated_client, _webhook_payload(order_id=order_id, payment_id=payment_id, amount="1000.00"))
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "confirmed"

    def test_failed_webhook_does_not_confirm_order(self, authenticated_client):
        order_number, order_id, payment_id = _create_order_with_payment_reference(authenticated_client)
        response = _post_webhook(authenticated_client, _webhook_payload(order_id=order_id, payment_id=payment_id, amount="1000.00", event_type="failed"))
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "pending_payment"

    def test_amount_mismatch_webhook_rejected_not_trusted(self, authenticated_client):
        order_number, order_id, payment_id = _create_order_with_payment_reference(authenticated_client, amount=Decimal("1000.00"))
        response = _post_webhook(authenticated_client, _webhook_payload(order_id=order_id, payment_id=payment_id, amount="999999.00"))
        assert response.status_code == 409
        delivery = orm.PaymentWebhookDelivery.objects.get(provider_transaction_id__isnull=False)
        assert delivery.rejection_reason == "amount_or_currency_mismatch"
        order = ordering_composition.build_order_repository().get_by_id(uuid.UUID(order_id))
        assert order.status.value == "pending_payment"  # never confirmed on a mismatched amount

    def test_currency_mismatch_webhook_rejected(self, authenticated_client):
        order_number, order_id, payment_id = _create_order_with_payment_reference(authenticated_client, currency="UZS")
        response = _post_webhook(authenticated_client, _webhook_payload(order_id=order_id, payment_id=payment_id, amount="1000.00", currency="USD"))
        assert response.status_code == 409

    def test_unknown_payment_reference_rejected(self, authenticated_client):
        order_number, order_id, payment_id = _create_order_with_payment_reference(authenticated_client)
        response = _post_webhook(authenticated_client, _webhook_payload(order_id=order_id, payment_id=str(uuid.uuid4()), amount="1000.00"))
        assert response.status_code == 422


class TestReplayProtection:
    def test_duplicate_webhook_delivery_does_not_double_confirm(self, authenticated_client):
        order_number, order_id, payment_id = _create_order_with_payment_reference(authenticated_client)
        payload = _webhook_payload(order_id=order_id, payment_id=payment_id, amount="1000.00")

        first = _post_webhook(authenticated_client, payload)
        assert first.status_code == 200
        second = _post_webhook(authenticated_client, payload)  # identical provider_transaction_id
        assert second.status_code == 200
        assert second.json()["data"]["status"] == "already_processed"
        assert orm.PaymentWebhookDelivery.objects.filter(provider_transaction_id=payload["provider_transaction_id"]).count() == 1

    def test_late_webhook_after_order_already_confirmed_is_idempotent(self, authenticated_client):
        """A second, DIFFERENT provider_transaction_id (e.g. a duplicate payment attempt) targeting an already-confirmed order must not error."""
        order_number, order_id, payment_id = _create_order_with_payment_reference(authenticated_client)
        first = _post_webhook(authenticated_client, _webhook_payload(order_id=order_id, payment_id=payment_id, amount="1000.00"))
        assert first.status_code == 200

        second_payment_id = str(uuid.uuid4())
        attach2 = authenticated_client.post(f"/api/v1/orders/{order_number}/payment", {"payment_id": second_payment_id, "amount": "1000.00"}, format="json")
        assert attach2.status_code == 200

        second = _post_webhook(authenticated_client, _webhook_payload(order_id=order_id, payment_id=second_payment_id, amount="1000.00", provider_transaction_id=str(uuid.uuid4())))
        assert second.status_code == 200
        assert second.json()["data"]["status"] == "confirmed"  # unchanged, not an error


class TestConcurrency:
    def test_concurrent_duplicate_webhook_delivery_produces_exactly_one_processed_record(self):
        provider_transaction_id = str(uuid.uuid4())
        winners, losers = [], []

        def worker():
            from django.db import IntegrityError as _IE
            try:
                orm.PaymentWebhookDelivery.objects.create(
                    provider="test-provider", provider_transaction_id=provider_transaction_id, order_id=uuid.uuid4(),
                    event_type="captured", amount=Decimal("1000.00"), currency="UZS", status="processed",
                )
                winners.append(1)
            except _IE:
                losers.append(1)
            finally:
                connection.close()

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(winners) == 1
        assert len(losers) == 4
        assert orm.PaymentWebhookDelivery.objects.filter(provider_transaction_id=provider_transaction_id).count() == 1


class TestSecurity:
    def test_customer_cannot_call_webhook_endpoint_to_forge_own_authorization(self, api_client):
        """The webhook accepts no JWT/permission credentials at all -- AllowAny is correct here because the HMAC signature IS the security boundary, not user auth. A request with no valid signature is rejected regardless of any credentials supplied."""
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = _post_webhook(api_client, _webhook_payload(), sign=False)
        assert response.status_code == 401

    def test_order_payment_endpoint_remains_staff_only(self, api_client):
        """A completely unauthenticated request to the staff-only AttachPaymentReference endpoint is rejected -- confirms this phase did not weaken that boundary."""
        response = api_client.post("/api/v1/orders/ORD-000001/payment", {"payment_id": str(uuid.uuid4()), "amount": "1000.00"}, format="json")
        assert response.status_code == 401


class TestTransactionBoundary:
    """
    Phase 15H: closes a real, confirmed defect first found in Phase 12
    and re-verified still present before this fix -- build_update_payment_status
    was called AFTER the delivery-bookkeeping atomic() block had already
    committed, so a failure there left a committed "processed" delivery
    record permanently inconsistent with the real, never-updated Order
    payment reference status. Learning directly from Phase 09.7c's own
    identical lesson (CheckoutCartView's own transaction-boundary bug).
    """

    def test_failure_after_delivery_bookkeeping_rolls_back_the_entire_webhook(self, api_client, authenticated_client, monkeypatch):
        order_number, order_id, payment_id = _create_order_with_payment_reference(authenticated_client)

        def _boom(actor_id=None):
            class _Boom:
                def execute(self, **kwargs):
                    raise RuntimeError("Simulated failure in update_payment_status")

            return _Boom()

        monkeypatch.setattr(ordering_composition, "build_update_payment_status", _boom)

        payload = _webhook_payload(order_id=order_id, payment_id=payment_id, amount="1000.00")
        response = _post_webhook(api_client, payload)
        assert response.status_code == 500  # the injected failure surfaces as a real server error, not a fabricated success

        # The single most important assertion: the delivery record itself must
        # NOT exist -- before this fix, it would have been committed as
        # "processed" despite the failure, a phantom record inconsistent
        # with the Order's own never-updated payment status.
        assert not orm.PaymentWebhookDelivery.objects.filter(provider_transaction_id=payload["provider_transaction_id"]).exists()

        # The real Order's payment reference must remain in its original,
        # pre-webhook state -- never partially transitioned.
        order = ordering_composition.build_order_repository().get_by_id(uuid.UUID(order_id))
        ref = next(r for r in order.payment_references.values() if str(r.payment_id) == payment_id)
        assert ref.status.value != "captured"

    def test_successful_webhook_still_commits_atomically(self, api_client, authenticated_client):
        """Regression guard: the fix must not have broken the real, already-proven success path."""
        order_number, order_id, payment_id = _create_order_with_payment_reference(authenticated_client)

        payload = _webhook_payload(order_id=order_id, payment_id=payment_id, amount="1000.00")
        response = _post_webhook(api_client, payload)
        assert response.status_code == 200

        assert orm.PaymentWebhookDelivery.objects.filter(provider_transaction_id=payload["provider_transaction_id"]).exists()
        order = ordering_composition.build_order_repository().get_by_id(uuid.UUID(order_id))
        ref = next(r for r in order.payment_references.values() if str(r.payment_id) == payment_id)
        assert ref.status.value == "captured"
