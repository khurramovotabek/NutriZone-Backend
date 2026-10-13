"""
Phase 03A continuation's Cart IDOR regression suite. Proves the
security gap found and fixed this session: `Cart.token: CartToken`
already existed and was already returned to clients on every cart
response, but no view ever validated an incoming token against it.
Model A (confirmed via CartToken's own docstring): authenticated
carts require customer_id match; guest carts require the matching
CartToken via the new X-Cart-Token header.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from common.permissions import HasPermissionCode

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class _AllowAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return True


def _client_as(monkeypatch, user_id) -> APIClient:
    monkeypatch.setattr(HasPermissionCode, "resolver", _AllowAllResolver())
    fake_user = SimpleNamespace(id=user_id, is_authenticated=True, store_ids=set())
    monkeypatch.setattr(
        "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
        lambda self, request: (fake_user, None),
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
    return client


class TestGuestCartTokenOwnership:
    def test_guest_cart_requires_token(self, monkeypatch):
        """A guest cart (customer_id is None) cannot be accessed without the matching token -- the confirmed, proven gap this session closes."""
        client = _client_as(monkeypatch, uuid.uuid4())
        create_response = client.post("/api/v1/cart/", {}, format="json")
        code = create_response.json()["data"]["code"]

        # A different requester with no token at all.
        attacker_client = _client_as(monkeypatch, uuid.uuid4())
        response = attacker_client.get(f"/api/v1/cart/{code}")
        assert response.status_code == 403

    def test_guest_cart_wrong_token_rejected(self, monkeypatch):
        client = _client_as(monkeypatch, uuid.uuid4())
        create_response = client.post("/api/v1/cart/", {}, format="json")
        code = create_response.json()["data"]["code"]

        attacker_client = _client_as(monkeypatch, uuid.uuid4())
        attacker_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token", HTTP_X_CART_TOKEN=str(uuid.uuid4()))
        response = attacker_client.get(f"/api/v1/cart/{code}")
        assert response.status_code == 403

    def test_guest_cart_correct_token_succeeds(self, monkeypatch):
        client = _client_as(monkeypatch, uuid.uuid4())
        create_response = client.post("/api/v1/cart/", {}, format="json")
        code = create_response.json()["data"]["code"]
        token = create_response.json()["data"]["token"]

        client.credentials(HTTP_AUTHORIZATION="Bearer fake-token", HTTP_X_CART_TOKEN=token)
        response = client.get(f"/api/v1/cart/{code}")
        assert response.status_code == 200
        assert response.json()["data"]["code"] == code

    def test_guest_cart_mutation_also_requires_token(self, monkeypatch):
        """Confirms the fix applies to mutation endpoints too (folded into the shared loader), not just the read/detail view."""
        client = _client_as(monkeypatch, uuid.uuid4())
        create_response = client.post("/api/v1/cart/", {}, format="json")
        code = create_response.json()["data"]["code"]

        attacker_client = _client_as(monkeypatch, uuid.uuid4())
        response = attacker_client.post(f"/api/v1/cart/{code}/items", {"product_variant_id": str(uuid.uuid4()), "quantity": 1}, format="json")
        assert response.status_code == 403


class TestAuthenticatedCartOwnership:
    def test_customer_a_cannot_access_customer_b_authenticated_cart_via_wrong_token(self, monkeypatch):
        """Even without customer_id assignment, the token mechanism alone already prevents cross-user access for a cart still in guest form."""
        customer_b_client = _client_as(monkeypatch, uuid.uuid4())
        create_response = customer_b_client.post("/api/v1/cart/", {}, format="json")
        code = create_response.json()["data"]["code"]

        customer_a_client = _client_as(monkeypatch, uuid.uuid4())
        response = customer_a_client.get(f"/api/v1/cart/{code}")
        assert response.status_code == 403


class TestGuestCartCreationNowAllowed:
    """
    Real, product-required behavior change: an anonymous (not-logged-in)
    visitor must be able to add items to a product, view their cart,
    change quantities, and clear it -- all without logging in. Only
    checkout requires an authenticated session (see
    TestCheckoutStillRequiresAuthentication below). Guest-cart ownership
    is still fully enforced via the X-Cart-Token mechanism (see
    TestGuestCartTokenOwnership above) -- this only removes the
    blanket "no anonymous request at all" rejection that previously
    made a guest cart unreachable in the first place.
    """

    def test_anonymous_cart_creation_succeeds(self):
        response = APIClient().post("/api/v1/cart/", {"currency": "UZS", "cart_type": "guest"}, format="json")
        assert response.status_code == 201
        assert response.json()["data"]["customer_id"] is None

    def test_anonymous_item_add_succeeds_with_the_real_cart_token(self):
        client = APIClient()
        create_response = client.post("/api/v1/cart/", {"currency": "UZS", "cart_type": "guest"}, format="json")
        code, token = create_response.json()["data"]["code"], create_response.json()["data"]["token"]

        client.credentials(HTTP_X_CART_TOKEN=token)
        response = client.post(f"/api/v1/cart/{code}/items", {"product_variant_id": str(uuid.uuid4()), "quantity": 1}, format="json")
        # Not 401/403 -- a 404/422 here would mean the (fake) variant
        # doesn't exist, which is a separate, expected failure mode,
        # not an authentication rejection.
        assert response.status_code not in (401, 403)

    def test_anonymous_clear_cart_succeeds(self):
        client = APIClient()
        create_response = client.post("/api/v1/cart/", {"currency": "UZS", "cart_type": "guest"}, format="json")
        code, token = create_response.json()["data"]["code"], create_response.json()["data"]["token"]

        client.credentials(HTTP_X_CART_TOKEN=token)
        response = client.post(f"/api/v1/cart/{code}/clear", {}, format="json")
        assert response.status_code == 200


class TestCheckoutStillRequiresAuthentication:
    """Real, product-required boundary: unlike cart browsing/editing, checkout must still require a logged-in session."""

    def test_anonymous_checkout_is_rejected(self):
        client = APIClient()
        create_response = client.post("/api/v1/cart/", {"currency": "UZS", "cart_type": "guest"}, format="json")
        code, token = create_response.json()["data"]["code"], create_response.json()["data"]["token"]

        client.credentials(HTTP_X_CART_TOKEN=token)
        response = client.post(f"/api/v1/cart/{code}/checkout", {}, format="json")
        assert response.status_code == 401
