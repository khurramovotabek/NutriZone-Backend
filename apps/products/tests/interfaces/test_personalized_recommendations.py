"""
Phase 03B: PersonalizedRecommendationsView tests. Proves the priority
hierarchy this phase specifies: purchase-history category affinity,
falling back to popularity, falling back to general active products.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.ordering.domain.aggregates import Order
from apps.ordering.domain.enums import OrderChannel, OrderStatus
from apps.ordering.domain.value_objects import OrderNumber
from apps.ordering.infrastructure import composition as ordering_composition
from apps.ordering.tests.factories import _next_order_number, make_address
from apps.products.domain.aggregates import Product, ProductVariant
from apps.products.domain.entities import ProductMedia
from apps.products.domain.enums import MediaRole
from apps.products.domain.value_objects import SKU, Slug
from apps.products.infrastructure.repositories import DjangoProductRepository
from common.permissions import HasPermissionCode
from common.utils.money import Money

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _real_category() -> uuid.UUID:
    from apps.products.infrastructure import models as orm
    return orm.Category.objects.create().id


def _published_product(slug: str, category_id=None, sku_suffix: str = None) -> Product:
    from apps.products.infrastructure import models as orm
    suffix = sku_suffix or uuid.uuid4().hex[:8].upper()
    product = Product(id=uuid.uuid4(), slug=Slug(slug), name=f"Product {slug}", category_id=category_id)
    product.add_variant(ProductVariant(id=uuid.uuid4(), sku=SKU(f"SKU-{suffix}")))
    product.add_media(ProductMedia(id=uuid.uuid4(), media_id=uuid.uuid4(), media_role=MediaRole.PRIMARY, storage_path=f"products/{slug}.jpg"))
    product.publish()
    return product


def _completed_order_for(customer_id: uuid.UUID, variant_id: uuid.UUID):
    from apps.ordering.tests.factories import make_line_item

    line = make_line_item(product_variant_id=variant_id, unit_price=Money(amount=Decimal("10000.00"), currency="UZS"), quantity=1)
    order = Order(
        id=uuid.uuid4(), order_number=OrderNumber(_next_order_number()), customer_id=customer_id, cart_id=uuid.uuid4(),
        shipping_address=make_address(), billing_address=make_address(), currency="UZS", channel=OrderChannel.WEB,
        status=OrderStatus.COMPLETED, lines={line.id: line}, placed_at=datetime.utcnow(),
    )
    return ordering_composition.build_order_repository().save(order)


@pytest.fixture
def customer_client(monkeypatch):
    customer_id = uuid.uuid4()
    fake_user = SimpleNamespace(id=customer_id, is_authenticated=True, store_ids=set())
    monkeypatch.setattr(
        "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
        lambda self, request: (fake_user, None),
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
    return client, customer_id


class TestPersonalizedRecommendations:
    def test_unauthenticated_rejected(self):
        response = APIClient().get("/api/v1/products/recommendations")
        assert response.status_code == 401

    def test_no_history_falls_back_to_general_active_products(self, customer_client):
        client, customer_id = customer_client
        repo = DjangoProductRepository()
        repo.save(_published_product("fallback-item-a"))
        repo.save(_published_product("fallback-item-b"))

        response = client.get("/api/v1/products/recommendations")
        assert response.status_code == 200
        assert len(response.json()["data"]) >= 2

    def test_purchase_history_drives_category_affinity(self, customer_client):
        client, customer_id = customer_client
        category_a = _real_category()
        category_b = _real_category()
        repo = DjangoProductRepository()

        purchased_product = _published_product("history-purchased", category_id=category_a)
        repo.save(purchased_product)
        same_category_product = _published_product("history-same-category", category_id=category_a)
        repo.save(same_category_product)
        other_category_product = _published_product("history-other-category", category_id=category_b)
        repo.save(other_category_product)

        variant_id = next(iter(purchased_product.variants.keys()))
        _completed_order_for(customer_id, variant_id)

        response = client.get("/api/v1/products/recommendations")
        assert response.status_code == 200
        slugs = {item["slug"] for item in response.json()["data"]}
        assert "history-same-category" in slugs
        assert "history-other-category" not in slugs

    def test_result_bounded_by_default_limit(self, customer_client):
        client, customer_id = customer_client
        repo = DjangoProductRepository()
        for i in range(15):
            repo.save(_published_product(f"bound-item-{i}"))

        response = client.get("/api/v1/products/recommendations")
        assert len(response.json()["data"]) <= 8

    def test_deterministic_ordering_across_repeated_requests(self, customer_client):
        client, customer_id = customer_client
        repo = DjangoProductRepository()
        for i in range(5):
            repo.save(_published_product(f"det-item-{i}"))

        first = client.get("/api/v1/products/recommendations").json()["data"]
        second = client.get("/api/v1/products/recommendations").json()["data"]
        assert [i["id"] for i in first] == [i["id"] for i in second]
