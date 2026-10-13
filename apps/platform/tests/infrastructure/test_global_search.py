"""
Phase 17.1: global admin search (Ctrl+K command palette) backend
tests. Every scenario was verified live via a real Django test-client
request before being formalized.
"""
from __future__ import annotations

import json
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def staff_client():
    User = get_user_model()
    user = User.objects.create(username=f"nz_staff_{uuid.uuid4().hex[:8]}", is_staff=True, is_superuser=True)
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def non_staff_client():
    User = get_user_model()
    user = User.objects.create(username=f"nz_customer_{uuid.uuid4().hex[:8]}", is_staff=False)
    client = Client()
    client.force_login(user)
    return client


class TestGlobalSearchPermissions:
    def test_unauthenticated_request_is_redirected(self):
        response = Client().get("/django-admin/search/?q=whey")
        assert response.status_code == 302

    def test_non_staff_request_is_redirected(self, non_staff_client):
        response = non_staff_client.get("/django-admin/search/?q=whey")
        assert response.status_code == 302

    def test_staff_request_succeeds(self, staff_client):
        response = staff_client.get("/django-admin/search/?q=whey")
        assert response.status_code == 200


class TestGlobalSearchQueryValidation:
    def test_short_query_returns_empty_groups(self, staff_client):
        response = staff_client.get("/django-admin/search/?q=w")
        body = json.loads(response.content)
        assert body["groups"] == []

    def test_missing_query_returns_empty_groups(self, staff_client):
        response = staff_client.get("/django-admin/search/")
        body = json.loads(response.content)
        assert body["groups"] == []


class TestGlobalSearchProductResults:
    def test_finds_product_by_readable_name(self, staff_client):
        from apps.products.infrastructure import models as products_orm

        category = products_orm.Category.objects.create(id=uuid.uuid4(), is_active=True, sort_order=1)
        product = products_orm.Product.objects.create(id=uuid.uuid4(), status="published", category=category)
        products_orm.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="uz", name="Whey Protein Vanilla", slug=f"whey-{uuid.uuid4().hex[:6]}")

        response = staff_client.get("/django-admin/search/?q=whey")
        body = json.loads(response.content)
        product_group = next((g for g in body["groups"] if g["label"] == "Products"), None)
        assert product_group is not None
        assert any("Whey Protein Vanilla" in r["title"] for r in product_group["results"])
        assert not any(str(product.id) == r["title"] for r in product_group["results"])


class TestGlobalSearchOrderResults:
    def test_finds_order_by_order_number(self, staff_client):
        import uuid as uuid_module
        from datetime import datetime
        from decimal import Decimal

        from apps.ordering.domain.aggregates import Order
        from apps.ordering.domain.enums import OrderChannel, OrderStatus
        from apps.ordering.domain.value_objects import OrderNumber
        from apps.ordering.infrastructure import composition as ordering_composition
        from apps.ordering.tests.factories import make_address, make_line_item
        from common.utils.money import Money

        order_number = f"ORD-{uuid_module.uuid4().hex[:10].upper()}"
        line = make_line_item(unit_price=Money(amount=Decimal("50000.00"), currency="UZS"), quantity=1)
        order = Order(
            id=uuid_module.uuid4(), order_number=OrderNumber(order_number), customer_id=uuid_module.uuid4(), cart_id=uuid_module.uuid4(),
            shipping_address=make_address(), billing_address=make_address(), currency="UZS", channel=OrderChannel.WEB,
            status=OrderStatus.PENDING_PAYMENT, lines={line.id: line}, placed_at=datetime.utcnow(),
        )
        ordering_composition.build_order_repository().save(order)

        response = staff_client.get(f"/django-admin/search/?q={order_number[-8:]}")
        body = json.loads(response.content)
        order_group = next((g for g in body["groups"] if g["label"] == "Orders"), None)
        assert order_group is not None
        assert any(order_number in r["title"] for r in order_group["results"])


class TestGlobalSearchCustomerResults:
    def test_finds_customer_by_phone_number(self, staff_client):
        from apps.identity.infrastructure import models as identity_orm

        phone = f"+99890{uuid.uuid4().hex[:7]}"
        identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=phone, full_name="Test Customer Search", status="active")

        response = staff_client.get(f"/django-admin/search/?q={phone[-8:]}")
        body = json.loads(response.content)
        customer_group = next((g for g in body["groups"] if g["label"] == "Customers"), None)
        assert customer_group is not None
        assert any(phone in r["subtitle"] for r in customer_group["results"])
