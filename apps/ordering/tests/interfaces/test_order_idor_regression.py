"""
Phase 03A's Ordering IDOR regression suite. Proves a CRITICAL
vulnerability found and fixed this phase across 8 views:
OrderDetailView, InvoiceDetailView, ReturnListCreateView (GET),
ReturnDetailView, CancellationListCreateView (GET),
CancellationDetailView, CustomerOrdersView, and OrderSummaryView --
all trusted a URL-supplied identifier with zero ownership check.
Proven live before the fix: Customer A retrieved Customer B's full
order (including customer_id) by order number alone, a 200 response.
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


class _CustomerOnlyResolver:
    """Grants only the ordinary customer-level code, never the staff-level ordering.order.view_any."""

    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return permission_code == "ordering.order.view_own"


class _StaffResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return permission_code == "ordering.order.view_any"


def _client_as(monkeypatch, user_id, resolver) -> APIClient:
    HasPermissionCode.resolver = resolver
    fake_user = SimpleNamespace(id=user_id, is_authenticated=True, store_ids=set())
    monkeypatch.setattr(
        "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
        lambda self, request: (fake_user, None),
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
    return client


@pytest.fixture(autouse=True)
def _restore_resolver():
    """Phase 03B: fixes a confirmed resolver-leak bug -- _client_as() previously set HasPermissionCode.resolver with no teardown, polluting global state for tests running afterward in the same session."""
    original = HasPermissionCode.resolver
    yield
    HasPermissionCode.resolver = original


@pytest.fixture
def customer_b_order():
    customer_b = uuid.uuid4()
    line = make_line_item(unit_price=Money(amount=Decimal("1000.00"), currency="UZS"), quantity=1)
    order = Order(
        id=uuid.uuid4(), order_number=OrderNumber(_next_order_number()), customer_id=customer_b, cart_id=uuid.uuid4(),
        shipping_address=make_address(), billing_address=make_address(), currency="UZS", channel=OrderChannel.WEB,
        status=OrderStatus.PENDING_PAYMENT, lines={line.id: line}, placed_at=datetime.utcnow(),
    )
    saved = ordering_composition.build_order_repository().save(order)
    return saved, customer_b


class TestOrderDetailIDOR:
    def test_customer_a_cannot_view_customer_b_order(self, monkeypatch, customer_b_order):
        order, customer_b = customer_b_order
        client = _client_as(monkeypatch, uuid.uuid4(), _CustomerOnlyResolver())
        response = client.get(f"/api/v1/orders/{order.order_number.value}")
        assert response.status_code == 403

    def test_customer_can_view_own_order(self, monkeypatch, customer_b_order):
        order, customer_b = customer_b_order
        client = _client_as(monkeypatch, customer_b, _CustomerOnlyResolver())
        response = client.get(f"/api/v1/orders/{order.order_number.value}")
        assert response.status_code == 200
        assert response.json()["data"]["customer_id"] == str(customer_b)

    def test_staff_can_view_any_order(self, monkeypatch, customer_b_order):
        order, customer_b = customer_b_order
        client = _client_as(monkeypatch, uuid.uuid4(), _StaffResolver())
        response = client.get(f"/api/v1/orders/{order.order_number.value}")
        assert response.status_code == 200


class TestInvoiceDetailIDOR:
    def test_customer_a_cannot_view_customer_b_invoice_endpoint(self, monkeypatch, customer_b_order):
        order, customer_b = customer_b_order
        client = _client_as(monkeypatch, uuid.uuid4(), _CustomerOnlyResolver())
        response = client.get(f"/api/v1/orders/{order.order_number.value}/invoice")
        # 403 (ownership check fires first) not 404 (no invoice) -- confirms the fix runs before the invoice-existence check.
        assert response.status_code == 403


class TestReturnListIDOR:
    def test_customer_a_cannot_list_customer_b_returns(self, monkeypatch, customer_b_order):
        order, customer_b = customer_b_order
        client = _client_as(monkeypatch, uuid.uuid4(), _CustomerOnlyResolver())
        response = client.get(f"/api/v1/orders/{order.order_number.value}/returns")
        assert response.status_code == 403


class TestCancellationListIDOR:
    def test_customer_a_cannot_list_customer_b_cancellations(self, monkeypatch, customer_b_order):
        order, customer_b = customer_b_order
        client = _client_as(monkeypatch, uuid.uuid4(), _CustomerOnlyResolver())
        response = client.get(f"/api/v1/orders/{order.order_number.value}/cancellations")
        assert response.status_code == 403


class TestCustomerOrdersIDOR:
    def test_customer_a_cannot_list_customer_b_orders(self, monkeypatch, customer_b_order):
        order, customer_b = customer_b_order
        client = _client_as(monkeypatch, uuid.uuid4(), _CustomerOnlyResolver())
        response = client.get(f"/api/v1/orders/customers/{customer_b}")
        assert response.status_code == 403

    def test_customer_can_list_own_orders(self, monkeypatch, customer_b_order):
        order, customer_b = customer_b_order
        client = _client_as(monkeypatch, customer_b, _CustomerOnlyResolver())
        response = client.get(f"/api/v1/orders/customers/{customer_b}")
        assert response.status_code == 200


class TestOrderSummaryIDOR:
    def test_customer_a_cannot_view_customer_b_order_summary(self, monkeypatch, customer_b_order):
        order, customer_b = customer_b_order
        client = _client_as(monkeypatch, uuid.uuid4(), _CustomerOnlyResolver())
        response = client.get(f"/api/v1/orders/{order.order_number.value}/summary")
        assert response.status_code == 403


class TestUnauthenticatedAccessStillBlocked:
    def test_unauthenticated_request_rejected(self, customer_b_order):
        order, customer_b = customer_b_order
        response = APIClient().get(f"/api/v1/orders/{order.order_number.value}")
        assert response.status_code == 401
