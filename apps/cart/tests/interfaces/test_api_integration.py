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


class TestAnonymousCartCreation:
    """Real, product-required behavior: an anonymous (not-logged-in) visitor must be able to create their own guest cart -- see apps/cart/tests/interfaces/test_cart_idor_regression.py's own TestGuestCartCreationNowAllowed for the full rationale and ownership-enforcement tests."""

    def test_create_cart_succeeds_without_auth(self, api_client):
        response = api_client.post("/api/v1/cart/", {"currency": "UZS", "cart_type": "guest"}, format="json")
        assert response.status_code == 201
        assert response.json()["data"]["customer_id"] is None


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

    def test_create_cart_denied(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post("/api/v1/cart/", {}, format="json")
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

    def test_create_cart(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post("/api/v1/cart/", {}, format="json")
        assert response.status_code == 201
        assert response.json()["data"]["status"] == "active"

    def test_list_create_merged_endpoint_both_methods_reachable(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        create_response = api_client.post("/api/v1/cart/", {}, format="json")
        assert create_response.status_code == 201

        list_response = api_client.get("/api/v1/cart/")
        assert list_response.status_code == 200

    def test_get_cart_by_code(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        create_response = api_client.post("/api/v1/cart/", {}, format="json")
        code = create_response.json()["data"]["code"]
        token = create_response.json()["data"]["token"]
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token", HTTP_X_CART_TOKEN=token)

        response = api_client.get(f"/api/v1/cart/{code}")
        assert response.status_code == 200
        assert response.json()["data"]["code"] == code

    def test_response_envelope_has_request_id(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post("/api/v1/cart/", {}, format="json")
        assert "request_id" in response.json()["meta"]

    def test_lock_and_unlock_flow(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        create_response = api_client.post("/api/v1/cart/", {}, format="json")
        code = create_response.json()["data"]["code"]
        token = create_response.json()["data"]["token"]
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token", HTTP_X_CART_TOKEN=token)

        lock_response = api_client.post(f"/api/v1/cart/{code}/lock", {"reason": "admin_hold"}, format="json")
        assert lock_response.status_code == 200
        assert lock_response.json()["data"]["is_locked"] is True

        unlock_response = api_client.post(f"/api/v1/cart/{code}/unlock", {}, format="json")
        assert unlock_response.status_code == 200
        assert unlock_response.json()["data"]["is_locked"] is False

    def test_convert_placeholder_endpoint_locks_cart(self, api_client):
        """The `convert` endpoint is a documented placeholder (see Phase 3 certification report) -- verifies it performs the one legitimate action it currently claims to (locking), not a real status conversion."""
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        create_response = api_client.post("/api/v1/cart/", {}, format="json")
        code = create_response.json()["data"]["code"]
        token = create_response.json()["data"]["token"]
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token", HTTP_X_CART_TOKEN=token)

        response = api_client.post(f"/api/v1/cart/{code}/convert", {}, format="json")
        assert response.status_code == 200
        assert response.json()["data"]["is_locked"] is True
        assert response.json()["data"]["status"] == "active"  # NOT "converted" -- confirms the placeholder does not fake a real conversion

    def test_delete_non_archived_cart_returns_409(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        create_response = api_client.post("/api/v1/cart/", {}, format="json")
        code = create_response.json()["data"]["code"]
        token = create_response.json()["data"]["token"]
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token", HTTP_X_CART_TOKEN=token)

        response = api_client.delete(f"/api/v1/cart/{code}")
        assert response.status_code == 409

    def test_full_end_to_end_cart_workflow(self, api_client):
        """
        The explicitly-required complete workflow: Create Cart -> Add
        Items -> Apply Coupon -> Attach Reservation -> Attach Snapshot
        -> Validate -> Lock -> Unlock -> Remove Item -> Clear Cart ->
        Audit Trail -> Search.
        """
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")

        # 1. Create Cart
        create_response = api_client.post("/api/v1/cart/", {}, format="json")
        assert create_response.status_code == 201
        code = create_response.json()["data"]["code"]
        token = create_response.json()["data"]["token"]
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token", HTTP_X_CART_TOKEN=token)

        # 2. Add Items
        variant_id = str(uuid.uuid4())
        add_response = api_client.post(f"/api/v1/cart/{code}/items", {"product_variant_id": variant_id, "quantity": 2}, format="json")
        assert add_response.status_code == 201
        line_id = add_response.json()["data"]["items"][0]["id"]

        # 3. Apply Coupon
        coupon_id = str(uuid.uuid4())
        coupon_response = api_client.post(f"/api/v1/cart/{code}/coupon", {"coupon_id": coupon_id}, format="json")
        assert coupon_response.status_code == 200
        assert coupon_id in coupon_response.json()["data"]["coupon_ids"]

        # 4. Attach Reservation
        reservation_response = api_client.post(f"/api/v1/cart/{code}/reservation", {"item_id": line_id, "reservation_id": str(uuid.uuid4())}, format="json")
        assert reservation_response.status_code == 200

        # 5. Attach Price Snapshot
        snapshot_response = api_client.post(f"/api/v1/cart/{code}/snapshot", {"item_id": line_id, "price_snapshot_id": str(uuid.uuid4()), "unit_amount": "25.00", "currency": "UZS"}, format="json")
        assert snapshot_response.status_code == 200
        assert snapshot_response.json()["data"]["items"][0]["price_reference"] is not None

        # 6. Validate
        validate_response = api_client.post(f"/api/v1/cart/{code}/validate", {}, format="json")
        assert validate_response.status_code == 200
        assert validate_response.json()["data"]["is_valid"] is True

        # 7. Lock
        lock_response = api_client.post(f"/api/v1/cart/{code}/lock", {"reason": "checkout_in_progress"}, format="json")
        assert lock_response.status_code == 200

        # 8. Unlock
        unlock_response = api_client.post(f"/api/v1/cart/{code}/unlock", {}, format="json")
        assert unlock_response.status_code == 200

        # 9. Remove Item
        remove_response = api_client.delete(f"/api/v1/cart/{code}/items/{line_id}")
        assert remove_response.status_code == 204

        # Add a fresh item back so Clear Cart (step 10) has something real to clear.
        api_client.post(f"/api/v1/cart/{code}/items", {"product_variant_id": str(uuid.uuid4()), "quantity": 1}, format="json")

        # 10. Clear Cart
        clear_response = api_client.post(f"/api/v1/cart/{code}/clear", {}, format="json")
        assert clear_response.status_code == 200
        assert clear_response.json()["data"]["items"] == []

        # 11. Audit Trail
        audit_response = api_client.get(f"/api/v1/cart/{code}/audit")
        assert audit_response.status_code == 200
        assert audit_response.json()["pagination"]["total_count"] > 0

        # 12. Search
        search_response = api_client.get(f"/api/v1/cart/search?q={code}")
        assert search_response.status_code == 200

    def test_merge_guest_cart_flow(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")

        guest_response = api_client.post("/api/v1/cart/", {"cart_type": "guest"}, format="json")
        guest_code = guest_response.json()["data"]["code"]
        guest_id = guest_response.json()["data"]["id"]
        guest_token = guest_response.json()["data"]["token"]
        variant_id = str(uuid.uuid4())
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token", HTTP_X_CART_TOKEN=guest_token)
        api_client.post(f"/api/v1/cart/{guest_code}/items", {"product_variant_id": variant_id, "quantity": 2}, format="json")

        auth_response = api_client.post("/api/v1/cart/", {"cart_type": "authenticated"}, format="json")
        auth_code = auth_response.json()["data"]["code"]
        auth_token = auth_response.json()["data"]["token"]
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token", HTTP_X_CART_TOKEN=auth_token)

        merge_response = api_client.post(f"/api/v1/cart/{auth_code}/merge", {"guest_cart_id": guest_id, "strategy": "sum_quantities"}, format="json")
        assert merge_response.status_code == 200
        merged_item = next(i for i in merge_response.json()["data"]["items"] if i["product_variant_id"] == variant_id)
        assert merged_item["quantity"] == 2

    def test_snapshot_history_endpoint(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        create_response = api_client.post("/api/v1/cart/", {}, format="json")
        code = create_response.json()["data"]["code"]
        token = create_response.json()["data"]["token"]
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token", HTTP_X_CART_TOKEN=token)

        response = api_client.get(f"/api/v1/cart/{code}/snapshots")
        assert response.status_code == 200
        assert response.json()["data"] == []
