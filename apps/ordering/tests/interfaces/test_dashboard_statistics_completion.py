"""
Phase 03B Dashboard API completion tests. Covers two "built but never
wired" gaps closed this phase:
1. OrderStatisticsSelector.total_revenue_by_status() -- already
   correct (Phase 02I's own bug fix), never had an HTTP caller.
2. Products' StatisticsSelector -- existed with zero HTTP surface.
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


class TestOrderStatisticsRevenue:
    def test_revenue_by_status_defaults_to_completed(self, staff_client):
        line = make_line_item(unit_price=Money(amount=Decimal("100000.00"), currency="UZS"), quantity=1)
        order = Order(
            id=uuid.uuid4(), order_number=OrderNumber(_next_order_number()), customer_id=uuid.uuid4(), cart_id=uuid.uuid4(),
            shipping_address=make_address(), billing_address=make_address(), currency="UZS", channel=OrderChannel.WEB,
            status=OrderStatus.COMPLETED, lines={line.id: line}, placed_at=datetime.utcnow(),
        )
        ordering_composition.build_order_repository().save(order)

        response = staff_client.get("/api/v1/orders/statistics")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["revenue_by_status"]["status"] == "completed"
        assert data["revenue_by_status"]["revenue_by_currency"].get("UZS") == "100000.00"
        assert "completed" in data["counts_by_status"]

    def test_revenue_by_status_accepts_explicit_status(self, staff_client):
        response = staff_client.get("/api/v1/orders/statistics?status=cancelled")
        assert response.status_code == 200
        assert response.json()["data"]["revenue_by_status"]["status"] == "cancelled"

    def test_invalid_status_rejected(self, staff_client):
        response = staff_client.get("/api/v1/orders/statistics?status=not_a_real_status")
        assert response.status_code == 422

    def test_unauthenticated_rejected(self):
        response = APIClient().get("/api/v1/orders/statistics")
        assert response.status_code == 401


class TestProductStatistics:
    def test_returns_counts_and_average_media(self, staff_client):
        response = staff_client.get("/api/v1/admin/products/statistics")
        assert response.status_code == 200
        data = response.json()["data"]
        assert "counts_by_status" in data
        assert "average_media_per_product" in data
        assert isinstance(data["average_media_per_product"], (int, float))

    def test_unauthenticated_rejected(self):
        response = APIClient().get("/api/v1/admin/products/statistics")
        assert response.status_code == 401
