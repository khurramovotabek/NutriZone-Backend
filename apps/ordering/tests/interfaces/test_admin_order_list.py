"""
Phase 03B Dashboard completion: Recent Orders. Wires the fully-built,
already N+1-safe OrderSelector.list() to HTTP.
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
def staff_client(monkeypatch):
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


def _make_order(status=OrderStatus.PENDING_PAYMENT) -> Order:
    line = make_line_item(unit_price=Money(amount=Decimal("50000.00"), currency="UZS"), quantity=1)
    order = Order(
        id=uuid.uuid4(), order_number=OrderNumber(_next_order_number()), customer_id=uuid.uuid4(), cart_id=uuid.uuid4(),
        shipping_address=make_address(), billing_address=make_address(), currency="UZS", channel=OrderChannel.WEB,
        status=status, lines={line.id: line}, placed_at=datetime.utcnow(),
    )
    return ordering_composition.build_order_repository().save(order)


class TestAdminOrderList:
    def test_returns_orders_newest_first(self, staff_client):
        first = _make_order()
        second = _make_order()

        response = staff_client.get("/api/v1/orders/admin")
        assert response.status_code == 200
        ids = [item["id"] for item in response.json()["data"]]
        assert ids.index(str(second.id)) < ids.index(str(first.id))

    def test_filters_by_status(self, staff_client):
        _make_order(status=OrderStatus.CANCELLED)
        response = staff_client.get("/api/v1/orders/admin?filter[status]=cancelled")
        assert response.status_code == 200
        assert all(item["status"] == "cancelled" for item in response.json()["data"])

    def test_pagination_metadata_present(self, staff_client):
        response = staff_client.get("/api/v1/orders/admin")
        assert response.status_code == 200
        assert "total_count" in response.json()["pagination"]

    def test_unauthenticated_rejected(self):
        response = APIClient().get("/api/v1/orders/admin")
        assert response.status_code == 401
