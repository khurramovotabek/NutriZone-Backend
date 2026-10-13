"""
Phase 03B: Top Products, the last remaining Dashboard candidate.
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
from apps.ordering.tests.factories import _next_order_number, make_address, make_line_item
from apps.products.domain.aggregates import Product, ProductVariant
from apps.products.domain.entities import ProductMedia
from apps.products.domain.enums import MediaRole
from apps.products.domain.value_objects import SKU, Slug
from apps.products.infrastructure.repositories import DjangoProductRepository
from common.permissions import HasPermissionCode
from common.utils.money import Money

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class _AllowAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return True


@pytest.fixture
def staff_client(monkeypatch) -> APIClient:
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


def _published_product(slug: str) -> Product:
    from apps.products.infrastructure import models as orm
    suffix = uuid.uuid4().hex[:8].upper()
    product = Product(id=uuid.uuid4(), slug=Slug(slug), name=f"Product {slug}")
    product.add_variant(ProductVariant(id=uuid.uuid4(), sku=SKU(f"SKU-{suffix}")))
    product.add_media(ProductMedia(id=uuid.uuid4(), media_id=uuid.uuid4(), media_role=MediaRole.PRIMARY, storage_path=f"products/{slug}.jpg"))
    product.publish()
    return product


def _completed_order_line(variant_id: uuid.UUID, quantity: int):
    line = make_line_item(product_variant_id=variant_id, unit_price=Money(amount=Decimal("1000.00"), currency="UZS"), quantity=quantity)
    order = Order(
        id=uuid.uuid4(), order_number=OrderNumber(_next_order_number()), customer_id=uuid.uuid4(), cart_id=uuid.uuid4(),
        shipping_address=make_address(), billing_address=make_address(), currency="UZS", channel=OrderChannel.WEB,
        status=OrderStatus.COMPLETED, lines={line.id: line}, placed_at=datetime.utcnow(),
    )
    ordering_composition.build_order_repository().save(order)


def _pending_order_line(variant_id: uuid.UUID, quantity: int):
    line = make_line_item(product_variant_id=variant_id, unit_price=Money(amount=Decimal("1000.00"), currency="UZS"), quantity=quantity)
    order = Order(
        id=uuid.uuid4(), order_number=OrderNumber(_next_order_number()), customer_id=uuid.uuid4(), cart_id=uuid.uuid4(),
        shipping_address=make_address(), billing_address=make_address(), currency="UZS", channel=OrderChannel.WEB,
        status=OrderStatus.PENDING_PAYMENT, lines={line.id: line}, placed_at=datetime.utcnow(),
    )
    ordering_composition.build_order_repository().save(order)


class TestTopProducts:
    def test_staff_access_succeeds(self, staff_client):
        response = staff_client.get("/api/v1/admin/products/top")
        assert response.status_code == 200

    def test_unauthenticated_rejected(self):
        response = APIClient().get("/api/v1/admin/products/top")
        assert response.status_code == 401

    def test_empty_state_returns_empty_list(self, staff_client):
        response = staff_client.get("/api/v1/admin/products/top")
        assert response.status_code == 200
        assert response.json()["data"] == []

    def test_completed_orders_drive_ranking(self, staff_client):
        repo = DjangoProductRepository()
        low_seller = _published_product("top-low-seller")
        repo.save(low_seller)
        high_seller = _published_product("top-high-seller")
        repo.save(high_seller)

        low_variant_id = next(iter(low_seller.variants.keys()))
        high_variant_id = next(iter(high_seller.variants.keys()))
        _completed_order_line(low_variant_id, quantity=2)
        _completed_order_line(high_variant_id, quantity=10)

        response = staff_client.get("/api/v1/admin/products/top")
        assert response.status_code == 200
        data = response.json()["data"]
        slugs_in_order = [item["slug"] for item in data]
        assert slugs_in_order.index("top-high-seller") < slugs_in_order.index("top-low-seller")

    def test_quantity_aggregation_correct(self, staff_client):
        repo = DjangoProductRepository()
        product = _published_product("top-aggregation")
        repo.save(product)
        variant_id = next(iter(product.variants.keys()))

        _completed_order_line(variant_id, quantity=3)
        _completed_order_line(variant_id, quantity=4)

        response = staff_client.get("/api/v1/admin/products/top")
        item = next(i for i in response.json()["data"] if i["slug"] == "top-aggregation")
        assert item["quantity_sold"] == 7

    def test_non_completed_orders_do_not_affect_ranking(self, staff_client):
        repo = DjangoProductRepository()
        product = _published_product("top-pending-only")
        repo.save(product)
        variant_id = next(iter(product.variants.keys()))
        _pending_order_line(variant_id, quantity=100)

        response = staff_client.get("/api/v1/admin/products/top")
        slugs = {item["slug"] for item in response.json()["data"]}
        assert "top-pending-only" not in slugs

    def test_result_bounded_by_limit(self, staff_client):
        repo = DjangoProductRepository()
        for i in range(15):
            product = _published_product(f"top-bound-{i}")
            repo.save(product)
            variant_id = next(iter(product.variants.keys()))
            _completed_order_line(variant_id, quantity=1)

        response = staff_client.get("/api/v1/admin/products/top?limit=5")
        assert len(response.json()["data"]) <= 5
