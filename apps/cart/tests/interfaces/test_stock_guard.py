"""A sold-out variant (e.g. Ostrovit Creatine 1 kg with 0 units) can't be added, grown past the shelf, or checked out."""
from __future__ import annotations

import uuid

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.identity.infrastructure import models as identity_orm
from apps.products.infrastructure import models as p_models
from apps.stores.infrastructure.models import Store, StoreProductStock

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _variant(units: int | None):
    owner = identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", full_name="Owner", status="active")
    store = Store.objects.create(id=uuid.uuid4(), owner=owner, name="Filial", slug=f"filial-{uuid.uuid4().hex[:6]}")
    product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
    variant = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:6]}", weight_value=1, weight_unit="kg")
    if units is not None:
        StoreProductStock.objects.create(store=store, product_variant=variant, quantity=units)
    return variant


def _guest_cart():
    client = APIClient()
    data = client.post("/api/v1/cart/", {"currency": "UZS", "cart_type": "guest"}, format="json").json()["data"]
    client.credentials(HTTP_X_CART_TOKEN=data["token"])
    return client, data["code"]


@override_settings(CART_STOCK_GUARD=True)
def test_sold_out_variant_cannot_be_added():
    variant = _variant(0)
    client, code = _guest_cart()
    res = client.post(f"/api/v1/cart/{code}/items", {"product_variant_id": str(variant.id), "quantity": 1}, format="json")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "OUT_OF_STOCK"


@override_settings(CART_STOCK_GUARD=True)
def test_untracked_variant_counts_as_sold_out():
    variant = _variant(None)
    client, code = _guest_cart()
    res = client.post(f"/api/v1/cart/{code}/items", {"product_variant_id": str(variant.id), "quantity": 1}, format="json")
    assert res.status_code == 409


@override_settings(CART_STOCK_GUARD=True)
def test_adding_beyond_the_shelf_is_refused_but_within_is_fine():
    variant = _variant(2)
    client, code = _guest_cart()
    assert client.post(f"/api/v1/cart/{code}/items", {"product_variant_id": str(variant.id), "quantity": 2}, format="json").status_code == 201
    # a third unit (the cart already holds two) is more than the warehouse has
    res = client.post(f"/api/v1/cart/{code}/items", {"product_variant_id": str(variant.id), "quantity": 1}, format="json")
    assert res.status_code == 409


@override_settings(CART_STOCK_GUARD=True)
def test_quantity_can_be_lowered_but_not_raised_past_stock():
    variant = _variant(3)
    client, code = _guest_cart()
    cart = client.post(f"/api/v1/cart/{code}/items", {"product_variant_id": str(variant.id), "quantity": 3}, format="json").json()["data"]
    line_id = cart["items"][0]["id"]
    assert client.patch(f"/api/v1/cart/{code}/items/{line_id}", {"quantity": 4}, format="json").status_code == 409
    assert client.patch(f"/api/v1/cart/{code}/items/{line_id}", {"quantity": 1}, format="json").status_code == 200
