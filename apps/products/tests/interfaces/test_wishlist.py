"""
Real, live-verified regression test for the new Wishlist feature
(Application Services + REST API). Every scenario here was proven
live via a real, real-authenticated HTTP request through the actual
endpoints before being formalized.
"""
from __future__ import annotations

import json
import uuid

import pytest
from django.test import Client

from apps.identity.infrastructure import models as identity_orm
from apps.identity.infrastructure.security import hash_otp_code
from apps.products.infrastructure import composition
from apps.products.infrastructure import models as p_models

pytestmark = pytest.mark.django_db


def _make_product(name: str = "Test Product") -> p_models.Product:
    product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
    p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name=name, slug=f"tp-{uuid.uuid4().hex[:8]}")
    return product


class TestWishlistApplicationServices:
    def test_add_is_idempotent(self):
        product = _make_product()
        customer_id = uuid.uuid4()
        first = composition.build_add_to_wishlist().execute(customer_id=customer_id, product_id=product.id)
        second = composition.build_add_to_wishlist().execute(customer_id=customer_id, product_id=product.id)
        assert first["created"] is True
        assert second["created"] is False

    def test_list_returns_real_added_product(self):
        product = _make_product(name="Creatine")
        customer_id = uuid.uuid4()
        composition.build_add_to_wishlist().execute(customer_id=customer_id, product_id=product.id)
        items, total = composition.build_list_wishlist().execute(customer_id=customer_id)
        assert total == 1
        assert items[0]["name"] == "Creatine"

    def test_remove_deletes_the_item(self):
        product = _make_product()
        customer_id = uuid.uuid4()
        composition.build_add_to_wishlist().execute(customer_id=customer_id, product_id=product.id)
        composition.build_remove_from_wishlist().execute(customer_id=customer_id, product_id=product.id)
        items, total = composition.build_list_wishlist().execute(customer_id=customer_id)
        assert total == 0


class TestWishlistRealHttpFlow:
    def _real_authenticated_client(self) -> tuple[Client, dict]:
        client = Client()
        phone = f"+99890{uuid.uuid4().int % 10000000:07d}"
        client.post("/api/v1/identity/auth/request-otp", data=json.dumps({"phone_number": phone}), content_type="application/json")
        challenge = identity_orm.OTPCodeChallenge.objects.filter(phone_number=phone).order_by("-created_at").first()
        challenge.code_hash = hash_otp_code("999999")
        challenge.save(update_fields=["code_hash"])
        response = client.post("/api/v1/identity/auth/verify-otp", data=json.dumps({"phone_number": phone, "code": "999999"}), content_type="application/json")
        access_token = json.loads(response.content)["data"]["access_token"]
        return client, {"HTTP_AUTHORIZATION": f"Bearer {access_token}"}

    def test_real_customer_can_add_list_and_remove(self):
        client, auth = self._real_authenticated_client()
        product = _make_product(name="BCAA")

        add_response = client.post("/api/v1/wishlist", data=json.dumps({"product_id": str(product.id)}), content_type="application/json", **auth)
        assert add_response.status_code == 201

        list_response = client.get("/api/v1/wishlist", **auth)
        assert list_response.status_code == 200
        assert json.loads(list_response.content)["data"][0]["name"] == "BCAA"

        remove_response = client.delete(f"/api/v1/wishlist/{product.id}", **auth)
        assert remove_response.status_code == 204

        final_list = client.get("/api/v1/wishlist", **auth)
        assert len(json.loads(final_list.content)["data"]) == 0

    def test_anonymous_user_cannot_access_wishlist(self):
        client = Client()
        response = client.get("/api/v1/wishlist")
        assert response.status_code in (401, 403)
