"""
Full-stack API tests for the Store Rating capability -- a customer can
rate a store 1-5 stars (upsert, one row per store/customer), and the
store's public list/detail responses expose the resulting
rating_average/rating_count aggregate. Real URL routing, serializers,
views, and the real Postgres database together (Django Implementation
Blueprint §11's "API tests" tier).

Auth is simulated the same way apps/reviews's own interface tests do
(monkeypatching JWTIdentityAuthentication.authenticate to return a
fake-but-real-id user) rather than exercising the full OTP login flow,
which is already covered exhaustively elsewhere.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.identity.infrastructure import models as identity_orm
from apps.stores.infrastructure.models import Store, StoreRating

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


def _make_customer(**overrides) -> identity_orm.User:
    defaults = {
        "id": uuid.uuid4(),
        "phone_number": f"+99890{uuid.uuid4().int % 10000000:07d}",
        "full_name": "Test Customer",
        "status": "active",
        "language": "uz",
    }
    defaults.update(overrides)
    return identity_orm.User.objects.create(**defaults)


def _make_store(owner: identity_orm.User, **overrides) -> Store:
    defaults = {"id": uuid.uuid4(), "owner": owner, "name": f"Store {uuid.uuid4().hex[:8]}"}
    defaults.update(overrides)
    return Store.objects.create(**defaults)


def _authenticate_as(monkeypatch, user: identity_orm.User) -> None:
    fake_user = SimpleNamespace(id=user.id, is_authenticated=True, store_ids=set())
    monkeypatch.setattr(
        "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
        lambda self, request: (fake_user, None),
    )


class TestStoreRatingRequiresAuth:
    def test_get_requires_auth(self, api_client):
        store = _make_store(_make_customer())
        response = api_client.get(f"/api/v1/stores/{store.slug}/rating")
        assert response.status_code == 401

    def test_post_requires_auth(self, api_client):
        store = _make_store(_make_customer())
        response = api_client.post(f"/api/v1/stores/{store.slug}/rating", {"rating": 5}, format="json")
        assert response.status_code == 401


class TestStoreRatingSubmission:
    def test_no_rating_yet_returns_null(self, api_client, monkeypatch):
        store = _make_store(_make_customer())
        customer = _make_customer()
        _authenticate_as(monkeypatch, customer)
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")

        response = api_client.get(f"/api/v1/stores/{store.slug}/rating")
        assert response.status_code == 200
        assert response.json()["data"]["rating"] is None

    def test_valid_rating_is_saved_and_reflected_in_aggregate(self, api_client, monkeypatch):
        store = _make_store(_make_customer())
        customer = _make_customer()
        _authenticate_as(monkeypatch, customer)
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")

        response = api_client.post(f"/api/v1/stores/{store.slug}/rating", {"rating": 4}, format="json")
        assert response.status_code == 200
        body = response.json()["data"]
        assert body["rating"] == 4
        assert body["rating_average"] == 4.0
        assert body["rating_count"] == 1

        detail = api_client.get(f"/api/v1/stores/{store.slug}")
        detail_data = detail.json()["data"]
        assert detail_data["rating_average"] == 4.0
        assert detail_data["rating_count"] == 1

        me = api_client.get(f"/api/v1/stores/{store.slug}/rating")
        assert me.json()["data"]["rating"] == 4

    def test_rating_again_updates_rather_than_duplicates(self, api_client, monkeypatch):
        store = _make_store(_make_customer())
        customer = _make_customer()
        _authenticate_as(monkeypatch, customer)
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")

        api_client.post(f"/api/v1/stores/{store.slug}/rating", {"rating": 2}, format="json")
        response = api_client.post(f"/api/v1/stores/{store.slug}/rating", {"rating": 5}, format="json")

        assert response.status_code == 200
        body = response.json()["data"]
        assert body["rating"] == 5
        assert body["rating_average"] == 5.0
        assert body["rating_count"] == 1
        assert StoreRating.objects.filter(store=store, customer_id=customer.id).count() == 1

    def test_average_across_multiple_customers_matches_list_and_detail(self, api_client, monkeypatch):
        store = _make_store(_make_customer())
        alice = _make_customer()
        bob = _make_customer()

        _authenticate_as(monkeypatch, alice)
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        api_client.post(f"/api/v1/stores/{store.slug}/rating", {"rating": 5}, format="json")

        _authenticate_as(monkeypatch, bob)
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post(f"/api/v1/stores/{store.slug}/rating", {"rating": 3}, format="json")

        body = response.json()["data"]
        assert body["rating_average"] == 4.0
        assert body["rating_count"] == 2

        # The list view annotates rating_average/rating_count in bulk
        # (a separate code path from the single-object aggregate in
        # _rating_fields()) -- checked independently so the two can
        # never silently drift apart. StoreListView paginates via
        # DRF's own PageNumberPagination directly (not the
        # success_response/paginated_response envelope helpers used
        # elsewhere), so results live under "results", not "data".
        listing = api_client.get("/api/v1/stores")
        row = next(s for s in listing.json()["results"] if s["slug"] == store.slug)
        assert row["rating_average"] == 4.0
        assert row["rating_count"] == 2

        detail = api_client.get(f"/api/v1/stores/{store.slug}")
        detail_data = detail.json()["data"]
        assert detail_data["rating_average"] == 4.0
        assert detail_data["rating_count"] == 2

    @pytest.mark.parametrize("rating", [0, 6, -1])
    def test_out_of_range_rating_rejected(self, api_client, monkeypatch, rating):
        store = _make_store(_make_customer())
        customer = _make_customer()
        _authenticate_as(monkeypatch, customer)
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")

        response = api_client.post(f"/api/v1/stores/{store.slug}/rating", {"rating": rating}, format="json")
        assert response.status_code == 422

    def test_owner_cannot_rate_own_store(self, api_client, monkeypatch):
        owner = _make_customer()
        store = _make_store(owner)
        _authenticate_as(monkeypatch, owner)
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")

        response = api_client.post(f"/api/v1/stores/{store.slug}/rating", {"rating": 5}, format="json")
        assert response.status_code == 422
        assert response.json()["error"]["details"]["fields"][0]["code"] == "CANNOT_RATE_OWN_STORE"
        assert not StoreRating.objects.filter(store=store, customer_id=owner.id).exists()


class TestStoreWithNoRatingsYet:
    def test_detail_shows_null_average_and_zero_count(self, api_client):
        store = _make_store(_make_customer())
        response = api_client.get(f"/api/v1/stores/{store.slug}")
        data = response.json()["data"]
        assert data["rating_average"] is None
        assert data["rating_count"] == 0

    def test_list_shows_null_average_and_zero_count(self, api_client):
        store = _make_store(_make_customer())
        response = api_client.get("/api/v1/stores")
        row = next(s for s in response.json()["results"] if s["slug"] == store.slug)
        assert row["rating_average"] is None
        assert row["rating_count"] == 0
