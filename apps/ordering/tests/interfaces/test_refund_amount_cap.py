"""
Phase 03A final closure's refund-amount-cap regression test.
Proves a genuine financial-integrity gap found and fixed this session:
`RefundReturn.execute()` never cross-checked the requested refund
amount against the order's own actual paid total (sum of its
CAPTURED payment references, minus prior refunds already issued for
the same order). A refund exceeding what was ever paid was silently
accepted before this fix.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from types import SimpleNamespace

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from common.permissions import HasPermissionCode

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class _AllowAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return True


def _client_as(monkeypatch, user_id) -> APIClient:
    HasPermissionCode.resolver = _AllowAllResolver()
    fake_user = SimpleNamespace(id=user_id, is_authenticated=True, store_ids=set())
    monkeypatch.setattr(
        "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
        lambda self, request: (fake_user, None),
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
    return client


@pytest.fixture(autouse=True)
def _restore_resolver():
    """Phase 03B: fixes a confirmed resolver-leak bug -- _client_as() previously set HasPermissionCode.resolver with no teardown, polluting global state for tests running afterward in the same session."""
    original = HasPermissionCode.resolver
    yield
    HasPermissionCode.resolver = original


def _sign(body: bytes) -> str:
    return hmac.new(settings.PAYMENT_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


def _paid_order(client, unit_price="100000.00"):
    """Real HTTP flow: create order, attach + capture a real payment reference. Returns (order_number, order_id, line_id)."""
    payload = {
        "currency": "UZS",
        "shipping_address": {"recipient_name": "Jane Doe", "line1": "123 Main St", "city": "Tashkent", "country_code": "UZ"},
        "billing_address": {"recipient_name": "Jane Doe", "line1": "123 Main St", "city": "Tashkent", "country_code": "UZ"},
        "line_items": [{"product_variant_id": str(uuid.uuid4()), "quantity": 1, "unit_price": unit_price}],
    }
    create_response = client.post("/api/v1/orders/", payload, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
    assert create_response.status_code == 201, create_response.json()
    data = create_response.json()["data"]
    order_number, order_id, line_id = data["order_number"], data["id"], data["lines"][0]["id"]

    payment_id = str(uuid.uuid4())
    attach = client.post(f"/api/v1/orders/{order_number}/payment", {"payment_id": payment_id, "amount": unit_price}, format="json")
    assert attach.status_code == 200, attach.json()

    payload = {"provider": "test-provider", "provider_transaction_id": str(uuid.uuid4()), "order_id": order_id, "payment_id": payment_id, "event_type": "captured", "amount": unit_price, "currency": "UZS"}
    body = json.dumps(payload).encode()
    webhook = client.post("/api/v1/orders/payments/webhook", data=body, content_type="application/json", HTTP_X_PAYMENT_SIGNATURE=_sign(body))
    assert webhook.status_code == 200, webhook.json()

    _deliver(client, order_number)
    return order_number, order_id, line_id


def _deliver(client, order_number):
    """Only a delivered order can be returned: walk it through the real lifecycle endpoints."""
    client.post(f"/api/v1/orders/{order_number}/confirm", {}, format="json")  # may already be confirmed by the captured payment
    for step in ("start-processing", "ship", "deliver"):
        resp = client.post(f"/api/v1/orders/{order_number}/{step}", {}, format="json")
        assert resp.status_code == 200, (step, resp.json())


def _create_and_process_return(client, order_number, line_id, quantity=1):
    resp = client.post(f"/api/v1/orders/{order_number}/returns", {"reason": "defective", "lines": [{"order_line_item_id": line_id, "quantity": quantity}]}, format="json")
    assert resp.status_code == 201, resp.json()
    return_id = resp.json()["data"]["id"]
    assert client.post(f"/api/v1/orders/returns/{return_id}/approve", {}, format="json").status_code == 200
    assert client.post(f"/api/v1/orders/returns/{return_id}/receive", {}, format="json").status_code == 200
    return return_id


class TestRefundAmountCap:
    def test_refund_exceeding_paid_total_rejected(self, monkeypatch):
        client = _client_as(monkeypatch, uuid.uuid4())
        order_number, order_id, line_id = _paid_order(client, unit_price="100000.00")
        return_id = _create_and_process_return(client, order_number, line_id)

        response = client.post(f"/api/v1/orders/returns/{return_id}/refund", {"amount": "500000.00", "currency": "UZS"}, format="json")
        assert response.status_code == 422

    def test_refund_up_to_paid_total_succeeds(self, monkeypatch):
        client = _client_as(monkeypatch, uuid.uuid4())
        order_number, order_id, line_id = _paid_order(client, unit_price="100000.00")
        return_id = _create_and_process_return(client, order_number, line_id)

        response = client.post(f"/api/v1/orders/returns/{return_id}/refund", {"amount": "100000.00", "currency": "UZS"}, format="json")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "refunded"

    def _cash_order(self, client):
        payload = {
            "currency": "UZS",
            "shipping_address": {"recipient_name": "Jane Doe", "line1": "123 Main St", "city": "Tashkent", "country_code": "UZ"},
            "billing_address": {"recipient_name": "Jane Doe", "line1": "123 Main St", "city": "Tashkent", "country_code": "UZ"},
            "line_items": [{"product_variant_id": str(uuid.uuid4()), "quantity": 1, "unit_price": "100000.00"}],
        }
        create_response = client.post("/api/v1/orders/", payload, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        return create_response.json()["data"]["order_number"], create_response.json()["data"]["lines"][0]["id"]

    def test_undelivered_order_cannot_be_returned(self, monkeypatch):
        """Nothing was handed over (or paid) yet -- the return request itself is refused."""
        client = _client_as(monkeypatch, uuid.uuid4())
        order_number, line_id = self._cash_order(client)
        resp = client.post(f"/api/v1/orders/{order_number}/returns", {"reason": "defective", "lines": [{"order_line_item_id": line_id, "quantity": 1}]}, format="json")
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "ORDER_NOT_RETURNABLE"

    def test_cash_on_delivery_refund_is_capped_at_what_was_paid(self, monkeypatch):
        """No payment reference (cash collected on delivery): the customer paid the order total, never more."""
        client = _client_as(monkeypatch, uuid.uuid4())
        order_number, line_id = self._cash_order(client)
        _deliver(client, order_number)
        return_id = _create_and_process_return(client, order_number, line_id)
        too_much = client.post(f"/api/v1/orders/returns/{return_id}/refund", {"amount": "100000.01", "currency": "UZS"}, format="json")
        assert too_much.status_code == 422
        ok = client.post(f"/api/v1/orders/returns/{return_id}/refund", {"amount": "100000.00", "currency": "UZS"}, format="json")
        assert ok.status_code == 200
