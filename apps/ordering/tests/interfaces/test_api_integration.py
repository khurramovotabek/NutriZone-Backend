"""
Full-stack API integration tests -- real URL routing, serializers,
views, application services, and repository layer together against a
real database. Matches every prior module's
`tests/interfaces/test_api_integration.py` pattern.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from common.permissions import HasPermissionCode

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


class _AllowAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return True


class _DenyAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return False


def _address_payload() -> dict:
    return {"recipient_name": "Jane Doe", "line1": "123 Main St", "city": "Tashkent", "country_code": "UZ"}


def _create_order_payload(**overrides) -> dict:
    payload = {
        "currency": "UZS", "shipping_address": _address_payload(), "billing_address": _address_payload(),
        "line_items": [{"product_variant_id": str(uuid.uuid4()), "quantity": 2, "unit_price": "50.00"}],
    }
    payload.update(overrides)
    return payload


class TestUnauthenticatedAccess:
    def test_create_order_requires_auth(self, api_client):
        response = api_client.post("/api/v1/orders/", _create_order_payload(), format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        assert response.status_code == 401


class TestPermissionDenial:
    @pytest.fixture(autouse=True)
    def _authenticated_but_unauthorized(self, monkeypatch):
        original = HasPermissionCode.resolver
        HasPermissionCode.resolver = _DenyAllResolver()
        fake_user = SimpleNamespace(id=uuid.uuid4(), is_authenticated=True, store_ids=set())
        monkeypatch.setattr(
            "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
            lambda self, request: (fake_user, None),
        )
        yield
        HasPermissionCode.resolver = original

    def test_create_order_denied(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post("/api/v1/orders/", _create_order_payload(), format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        assert response.status_code == 403


class TestAuthorizedFlows:
    @pytest.fixture(autouse=True)
    def _authenticated_and_authorized(self, monkeypatch):
        original = HasPermissionCode.resolver
        HasPermissionCode.resolver = _AllowAllResolver()
        fake_user = SimpleNamespace(id=uuid.uuid4(), is_authenticated=True, store_ids=set())
        monkeypatch.setattr(
            "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
            lambda self, request: (fake_user, None),
        )
        yield
        HasPermissionCode.resolver = original

    def test_create_order(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post("/api/v1/orders/", _create_order_payload(), format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        assert response.status_code == 201
        assert response.json()["data"]["status"] == "pending_payment"

    def test_list_orders(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        api_client.post("/api/v1/orders/", _create_order_payload(), format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        response = api_client.get("/api/v1/orders/")
        assert response.status_code == 200

    def test_get_order_by_number(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        create_response = api_client.post("/api/v1/orders/", _create_order_payload(), format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        number = create_response.json()["data"]["order_number"]
        response = api_client.get(f"/api/v1/orders/{number}")
        assert response.status_code == 200
        assert response.json()["data"]["order_number"] == number

    def test_order_summary(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        create_response = api_client.post("/api/v1/orders/", _create_order_payload(), format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        number = create_response.json()["data"]["order_number"]
        response = api_client.get(f"/api/v1/orders/{number}/summary")
        assert response.status_code == 200

    def test_response_envelope_has_request_id(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post("/api/v1/orders/", _create_order_payload(), format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        assert "request_id" in response.json()["meta"]

    def test_lock_and_unlock_flow(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        create_response = api_client.post("/api/v1/orders/", _create_order_payload(), format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        number = create_response.json()["data"]["order_number"]

        lock_response = api_client.post(f"/api/v1/orders/{number}/lock", {"reason": "fraud_review"}, format="json")
        assert lock_response.status_code == 200
        assert lock_response.json()["data"]["is_locked"] is True

        unlock_response = api_client.post(f"/api/v1/orders/{number}/unlock", {}, format="json")
        assert unlock_response.status_code == 200
        assert unlock_response.json()["data"]["is_locked"] is False

    def test_archive_and_restore_flow(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        create_response = api_client.post("/api/v1/orders/", _create_order_payload(), format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        number = create_response.json()["data"]["order_number"]

        archive_response = api_client.post(f"/api/v1/orders/{number}/archive", {}, format="json")
        assert archive_response.status_code == 200
        assert archive_response.json()["data"]["is_archived"] is True

        restore_response = api_client.post(f"/api/v1/orders/{number}/restore", {}, format="json")
        assert restore_response.status_code == 200
        assert restore_response.json()["data"]["is_archived"] is False

    def test_cancel_order(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        create_response = api_client.post("/api/v1/orders/", _create_order_payload(), format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        number = create_response.json()["data"]["order_number"]

        response = api_client.post(f"/api/v1/orders/{number}/cancel", {"reason": "changed my mind"}, format="json")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "cancelled"

    def test_expire_order(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        create_response = api_client.post("/api/v1/orders/", _create_order_payload(), format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        number = create_response.json()["data"]["order_number"]

        response = api_client.post(f"/api/v1/orders/{number}/expire", {}, format="json")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "failed"

    def test_attach_shipment_payment_coupon_address_reservation_snapshot(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        create_response = api_client.post("/api/v1/orders/", _create_order_payload(), format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        order_data = create_response.json()["data"]
        number = order_data["order_number"]
        line_id = order_data["lines"][0]["id"]

        shipment_response = api_client.post(f"/api/v1/orders/{number}/shipment", {"fulfillment_id": str(uuid.uuid4())}, format="json")
        assert shipment_response.status_code == 200

        payment_response = api_client.post(f"/api/v1/orders/{number}/payment", {"payment_id": str(uuid.uuid4()), "amount": "100.00"}, format="json")
        assert payment_response.status_code == 200

        coupon_response = api_client.post(f"/api/v1/orders/{number}/coupon", {"coupon_id": str(uuid.uuid4())}, format="json")
        assert coupon_response.status_code == 200
        assert len(coupon_response.json()["data"]["coupon_ids"]) == 1

        address_response = api_client.post(f"/api/v1/orders/{number}/address", {"shipping_address": {**_address_payload(), "city": "Samarkand"}}, format="json")
        assert address_response.status_code == 200
        assert address_response.json()["data"]["shipping_address"]["city"] == "Samarkand"

        reservation_response = api_client.post(f"/api/v1/orders/{number}/reservation", {"line_item_id": line_id, "reservation_id": str(uuid.uuid4())}, format="json")
        assert reservation_response.status_code == 200

        snapshot_response = api_client.post(f"/api/v1/orders/{number}/price-snapshot", {"line_item_id": line_id, "price_snapshot_id": str(uuid.uuid4())}, format="json")
        assert snapshot_response.status_code == 200

    def test_issue_and_retrieve_invoice(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        create_response = api_client.post("/api/v1/orders/", _create_order_payload(), format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        number = create_response.json()["data"]["order_number"]

        issue_response = api_client.post(f"/api/v1/orders/{number}/invoice/issue", {"sequence": 1}, format="json")
        assert issue_response.status_code == 200
        assert issue_response.json()["data"]["invoice"]["status"] == "issued"

        get_response = api_client.get(f"/api/v1/orders/{number}/invoice")
        assert get_response.status_code == 200

    def test_returns_flow(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        create_response = api_client.post("/api/v1/orders/", _create_order_payload(), format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        order_data = create_response.json()["data"]
        number = order_data["order_number"]
        order_id = order_data["id"]
        line_id = order_data["lines"][0]["id"]

        # A refund must not exceed what was actually paid -- attach and confirm a real payment reference first, matching production's own actual flow.
        payment_id = str(uuid.uuid4())
        attach_response = api_client.post(f"/api/v1/orders/{number}/payment", {"payment_id": payment_id, "amount": "25.00"}, format="json")
        assert attach_response.status_code == 200, attach_response.json()

        import hashlib
        import hmac
        import json as _json
        from django.conf import settings

        webhook_payload = {
            "provider": "test-provider", "provider_transaction_id": str(uuid.uuid4()),
            "order_id": order_id, "payment_id": payment_id,
            "event_type": "captured", "amount": "25.00", "currency": "UZS",
        }
        body = _json.dumps(webhook_payload).encode()
        signature = hmac.new(settings.PAYMENT_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
        webhook_response = api_client.post("/api/v1/orders/payments/webhook", data=body, content_type="application/json", HTTP_X_PAYMENT_SIGNATURE=signature)
        assert webhook_response.status_code == 200, webhook_response.json()

        # Only a delivered order can be returned.
        api_client.post(f"/api/v1/orders/{number}/confirm", {}, format="json")
        for step in ("start-processing", "ship", "deliver"):
            assert api_client.post(f"/api/v1/orders/{number}/{step}", {}, format="json").status_code == 200, step

        create_return_response = api_client.post(f"/api/v1/orders/{number}/returns", {"reason": "defective", "lines": [{"order_line_item_id": line_id, "quantity": 1}]}, format="json")
        assert create_return_response.status_code == 201
        return_id = create_return_response.json()["data"]["id"]

        list_response = api_client.get(f"/api/v1/orders/{number}/returns")
        assert list_response.status_code == 200

        detail_response = api_client.get(f"/api/v1/orders/returns/{return_id}")
        assert detail_response.status_code == 200

        approve_response = api_client.post(f"/api/v1/orders/returns/{return_id}/approve", {}, format="json")
        assert approve_response.status_code == 200

        receive_response = api_client.post(f"/api/v1/orders/returns/{return_id}/receive", {}, format="json")
        assert receive_response.status_code == 200

        refund_response = api_client.post(f"/api/v1/orders/returns/{return_id}/refund", {"amount": "25.00", "currency": "UZS"}, format="json")
        assert refund_response.status_code == 200
        assert refund_response.json()["data"]["status"] == "refunded"

    def test_cancellations_flow(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        create_response = api_client.post("/api/v1/orders/", _create_order_payload(), format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        order_data = create_response.json()["data"]
        number = order_data["order_number"]
        line_id = order_data["lines"][0]["id"]

        create_cancellation_response = api_client.post(f"/api/v1/orders/{number}/cancellations", {"reason": "customer_request", "lines": [{"order_line_item_id": line_id, "quantity": 1}]}, format="json")
        assert create_cancellation_response.status_code == 201
        cancellation_id = create_cancellation_response.json()["data"]["id"]

        approve_response = api_client.post(f"/api/v1/orders/cancellations/{cancellation_id}/approve", {}, format="json")
        assert approve_response.status_code == 200

        complete_response = api_client.post(f"/api/v1/orders/cancellations/{cancellation_id}/complete", {}, format="json")
        assert complete_response.status_code == 200
        assert complete_response.json()["data"]["status"] == "completed"

    def test_search_and_statistics(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        api_client.post("/api/v1/orders/", _create_order_payload(), format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))

        search_response = api_client.get("/api/v1/orders/search?q=ORD")
        assert search_response.status_code == 200

        stats_response = api_client.get("/api/v1/orders/statistics")
        assert stats_response.status_code == 200

    def test_customer_orders(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        customer_id = str(uuid.uuid4())
        api_client.post("/api/v1/orders/", _create_order_payload(customer_id=customer_id), format="json")

        response = api_client.get(f"/api/v1/orders/customers/{customer_id}")
        assert response.status_code == 200

    def test_full_end_to_end_order_workflow(self, api_client):
        """
        The explicitly-required complete workflow: Create Order ->
        Confirm -> Start Processing -> Ship -> Deliver -> Complete ->
        Issue Invoice -> Create Return -> Approve -> Receive -> Refund.
        Verifies state after every step.
        """
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")

        # 1. Create Order
        create_response = api_client.post("/api/v1/orders/", _create_order_payload(), format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        assert create_response.status_code == 201
        order_data = create_response.json()["data"]
        number = order_data["order_number"]
        order_id = order_data["id"]
        line_id = order_data["lines"][0]["id"]
        assert order_data["status"] == "pending_payment"

        # 2. Confirm
        confirm_response = api_client.post(f"/api/v1/orders/{number}/confirm", {}, format="json")
        assert confirm_response.status_code == 200
        assert confirm_response.json()["data"]["status"] == "confirmed"

        # 2.5. Attach and capture a real payment reference -- a refund must not exceed what was actually paid (Phase 03A final closure fix). Posted after confirm since UpdatePaymentStatus's own idempotent-skip logic correctly leaves an already-confirmed order alone rather than erroring.
        payment_id = str(uuid.uuid4())
        attach_response = api_client.post(f"/api/v1/orders/{number}/payment", {"payment_id": payment_id, "amount": "50.00"}, format="json")
        assert attach_response.status_code == 200, attach_response.json()

        import hashlib
        import hmac
        import json as _json
        from django.conf import settings

        webhook_payload = {
            "provider": "test-provider", "provider_transaction_id": str(uuid.uuid4()),
            "order_id": order_id, "payment_id": payment_id,
            "event_type": "captured", "amount": "50.00", "currency": "UZS",
        }
        body = _json.dumps(webhook_payload).encode()
        signature = hmac.new(settings.PAYMENT_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
        webhook_response = api_client.post("/api/v1/orders/payments/webhook", data=body, content_type="application/json", HTTP_X_PAYMENT_SIGNATURE=signature)
        assert webhook_response.status_code == 200, webhook_response.json()

        # 3. Start Processing
        processing_response = api_client.post(f"/api/v1/orders/{number}/start-processing", {}, format="json")
        assert processing_response.status_code == 200
        assert processing_response.json()["data"]["status"] == "processing"

        # 4. Ship
        ship_response = api_client.post(f"/api/v1/orders/{number}/ship", {}, format="json")
        assert ship_response.status_code == 200
        assert ship_response.json()["data"]["status"] == "shipped"

        # 5. Deliver
        deliver_response = api_client.post(f"/api/v1/orders/{number}/deliver", {}, format="json")
        assert deliver_response.status_code == 200
        assert deliver_response.json()["data"]["status"] == "delivered"

        # 6. Complete
        complete_response = api_client.post(f"/api/v1/orders/{number}/complete", {}, format="json")
        assert complete_response.status_code == 200
        assert complete_response.json()["data"]["status"] == "completed"

        # 7. Issue Invoice
        invoice_response = api_client.post(f"/api/v1/orders/{number}/invoice/issue", {"sequence": 42}, format="json")
        assert invoice_response.status_code == 200
        assert invoice_response.json()["data"]["invoice"]["status"] == "issued"

        # 8. Create Return
        return_response = api_client.post(f"/api/v1/orders/{number}/returns", {"reason": "defective", "lines": [{"order_line_item_id": line_id, "quantity": 1}]}, format="json")
        assert return_response.status_code == 201
        return_id = return_response.json()["data"]["id"]
        assert return_response.json()["data"]["status"] == "requested"

        # 9. Approve
        approve_response = api_client.post(f"/api/v1/orders/returns/{return_id}/approve", {}, format="json")
        assert approve_response.status_code == 200
        assert approve_response.json()["data"]["status"] == "approved"

        # 10. Receive
        receive_response = api_client.post(f"/api/v1/orders/returns/{return_id}/receive", {}, format="json")
        assert receive_response.status_code == 200
        assert receive_response.json()["data"]["status"] == "received"

        # 11. Refund
        refund_response = api_client.post(f"/api/v1/orders/returns/{return_id}/refund", {"amount": "50.00", "currency": "UZS"}, format="json")
        assert refund_response.status_code == 200
        assert refund_response.json()["data"]["status"] == "refunded"
        assert refund_response.json()["data"]["refund_amount"]["amount"] == "50.00"

        # Final state verification: the order itself remains COMPLETED throughout the return workflow --
        # returns are an independent lifecycle, per this module's own aggregate design.
        final_order_response = api_client.get(f"/api/v1/orders/{number}")
        assert final_order_response.json()["data"]["status"] == "completed"
