"""
Full-stack API test for `POST /my-store/products` -- restocking a
variant the store already carries must ADD to the existing quantity,
never overwrite it. Real, confirmed bug this covers: `update_or_create(
..., defaults={"quantity": ...})` used to silently replace 4 in stock
with "add 10" -> 10, not 14.

Auth simulated the same way `test_store_rating.py` does (monkeypatching
`JWTIdentityAuthentication.authenticate`), not the full OTP flow.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.identity.infrastructure import models as identity_orm
from apps.products.infrastructure.models import Product, ProductVariant
from apps.stores.infrastructure.models import Store, StoreProductStock

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


def _make_owner(**overrides) -> identity_orm.User:
    defaults = {"id": uuid.uuid4(), "phone_number": f"+99890{uuid.uuid4().int % 10000000:07d}", "full_name": "Store Owner", "status": "active", "language": "uz"}
    defaults.update(overrides)
    return identity_orm.User.objects.create(**defaults)


def _make_store(owner: identity_orm.User, **overrides) -> Store:
    defaults = {"id": uuid.uuid4(), "owner": owner, "name": f"Store {uuid.uuid4().hex[:8]}"}
    defaults.update(overrides)
    return Store.objects.create(**defaults)


def _make_variant(**overrides) -> ProductVariant:
    product = Product.objects.create(id=uuid.uuid4())
    defaults = {"id": uuid.uuid4(), "product": product, "sku": f"SKU-{uuid.uuid4().hex[:10]}"}
    defaults.update(overrides)
    return ProductVariant.objects.create(**defaults)


def _authenticate_as(monkeypatch, user: identity_orm.User) -> None:
    fake_user = SimpleNamespace(id=user.id, is_authenticated=True, store_ids=set())
    monkeypatch.setattr(
        "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
        lambda self, request: (fake_user, None),
    )


class TestOwnerCannotEditStock:
    """Business rule: stock is managed by NutriZone staff; the owner's view is read-only (GET /my-store/pos/stock)."""

    def test_owner_cannot_add_change_or_remove_stock(self, api_client, monkeypatch):
        owner = _make_owner()
        store = _make_store(owner)
        variant = _make_variant()
        entry = StoreProductStock.objects.create(store=store, product_variant=variant, quantity=4)
        _authenticate_as(monkeypatch, owner)

        add = api_client.post("/api/v1/my-store/products", {"product_variant_id": str(variant.id), "quantity": 10}, format="json")
        patch = api_client.patch(f"/api/v1/my-store/products/{entry.id}", {"quantity": 99}, format="json")
        delete = api_client.delete(f"/api/v1/my-store/products/{entry.id}")

        assert add.status_code == patch.status_code == delete.status_code == 403
        assert add.json()["error"]["code"] == "STOCK_MANAGED_BY_STAFF"
        entry.refresh_from_db()
        assert entry.quantity == 4
