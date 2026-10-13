"""
Phase 08.4: NutriZone Admin Orders & Fulfillment Workspace tests.

Real database fixtures throughout, reusing the proven Order factory
pattern already established in this project's own earlier sessions.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.db import connection

from apps.ordering.domain.aggregates import Order
from apps.ordering.domain.enums import OrderChannel, OrderStatus
from apps.ordering.domain.value_objects import OrderNumber
from apps.ordering.infrastructure import composition as ordering_composition
from apps.ordering.tests.factories import _next_order_number, make_address, make_line_item
from common.utils.money import Money

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _make_order(status=OrderStatus.PENDING_PAYMENT, quantity=2, unit_price=Decimal("50000.00")):
    line = make_line_item(unit_price=Money(amount=unit_price, currency="UZS"), quantity=quantity)
    order = Order(
        id=uuid.uuid4(), order_number=OrderNumber(_next_order_number()), customer_id=uuid.uuid4(), cart_id=uuid.uuid4(),
        shipping_address=make_address(), billing_address=make_address(), currency="UZS", channel=OrderChannel.WEB,
        status=status, lines={line.id: line}, placed_at=datetime.utcnow(),
    )
    return ordering_composition.build_order_repository().save(order)


@pytest.fixture
def staff_client():
    User = get_user_model()
    user = User.objects.create(username=f"nz_staff_{uuid.uuid4().hex[:8]}", is_staff=True, is_superuser=True)
    user.set_password("pw")
    user.save()
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def non_staff_client():
    User = get_user_model()
    user = User.objects.create(username=f"nz_customer_{uuid.uuid4().hex[:8]}", is_staff=False)
    user.set_password("pw")
    user.save()
    client = Client()
    client.force_login(user)
    return client


class TestOrdersAccessControl:
    def test_anonymous_denied(self):
        response = Client().get("/django-admin/ordering/ordermodel/")
        assert response.status_code in (302, 403)

    def test_non_staff_denied(self, non_staff_client):
        response = non_staff_client.get("/django-admin/ordering/ordermodel/")
        assert response.status_code in (302, 403)

    def test_non_staff_cannot_access_order_detail_by_id(self, non_staff_client):
        """IDOR check: a non-staff user must be denied even with a real order's own ID in the URL."""
        order = _make_order()
        response = non_staff_client.get(f"/django-admin/ordering/ordermodel/{order.id}/change/")
        assert response.status_code in (302, 403)

    def test_staff_with_explicit_view_permission_but_not_superuser(self):
        """Distinct from superuser -- a staff user granted only view_ordermodel, matching this phase's own access matrix."""
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType
        from apps.ordering.infrastructure import models as orm

        # Real Django test-infrastructure gap, found via a genuine
        # cross-test-suite failure: ContentType.objects's own
        # in-memory cache is not transaction-aware, so when the full
        # suite runs together with other apps' migrations, a stale
        # content_type_id can cause a real ForeignKeyViolation here.
        # Django's own documented remedy for any test that resolves
        # ContentType dynamically.
        ContentType.objects.clear_cache()

        User = get_user_model()
        user = User.objects.create(username=f"nz_permstaff_{uuid.uuid4().hex[:8]}", is_staff=True, is_superuser=False)
        user.set_password("pw")
        user.save()
        content_type = ContentType.objects.get_for_model(orm.OrderModel)
        permission, _ = Permission.objects.get_or_create(codename="view_ordermodel", content_type=content_type, defaults={"name": "Can view order model"})
        user.user_permissions.add(permission)

        client = Client()
        client.force_login(user)
        response = client.get("/django-admin/ordering/ordermodel/")
        assert response.status_code == 200

        response = client.get("/django-admin/ordering/orderreturnmodel/")
        assert response.status_code == 403


class TestOrdersWorkspace:
    def test_list_shows_real_order_number(self, staff_client):
        order = _make_order()
        response = staff_client.get("/django-admin/ordering/ordermodel/")
        assert response.status_code == 200
        assert order.order_number.value in response.content.decode()

    def test_search_finds_by_order_number(self, staff_client):
        order = _make_order()
        response = staff_client.get(f"/django-admin/ordering/ordermodel/?q={order.order_number.value}")
        assert response.status_code == 200
        assert order.order_number.value in response.content.decode()

    def test_filter_by_status(self, staff_client):
        order = _make_order(status=OrderStatus.CONFIRMED)
        response = staff_client.get("/django-admin/ordering/ordermodel/?status__exact=confirmed")
        assert response.status_code == 200
        assert order.order_number.value in response.content.decode()

    def test_no_n_plus_1_on_order_list(self, staff_client):
        """Query count must not scale linearly with order count -- proves prefetch_related is actually effective."""
        for _ in range(5):
            _make_order()

        with CaptureQueriesContext(connection) as ctx:
            response = staff_client.get("/django-admin/ordering/ordermodel/")
        assert response.status_code == 200
        query_count_5 = len(ctx.captured_queries)

        for _ in range(5):
            _make_order()

        with CaptureQueriesContext(connection) as ctx:
            response = staff_client.get("/django-admin/ordering/ordermodel/")
        assert response.status_code == 200
        query_count_10 = len(ctx.captured_queries)

        assert query_count_10 < query_count_5 + 5, f"Query count grew from {query_count_5} to {query_count_10} for 5 more orders -- possible N+1"


class TestOrderDetail:
    def test_detail_renders_with_real_order(self, staff_client):
        order = _make_order()
        response = staff_client.get(f"/django-admin/ordering/ordermodel/{order.id}/change/")
        assert response.status_code == 200


class TestOrderFinancialSummary:
    """Phase 08.4: closes a genuine gap -- the Order Detail page had no financial summary section before this. Reuses the exact formula already certified in OrderStatisticsSelector.total_revenue_by_status()."""

    def test_financial_summary_reflects_real_line_items(self, staff_client):
        order = _make_order(quantity=3, unit_price=Decimal("20000.00"))
        response = staff_client.get(f"/django-admin/ordering/ordermodel/{order.id}/change/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "60 000" in content  # 3 * 20000, subtotal with zero discount/tax


class TestOrderReturnRefund:
    """Phase 08.4: closes a genuine gap -- RefundReturn (an existing, certified Application Service, Phase 03A's own refund-amount-cap enforcement) had zero Admin caller before this."""

    def _make_return(self, order_id=None):
        from apps.ordering.infrastructure import models as orm

        return orm.OrderReturnModel.objects.create(return_number=f"RET-{uuid.uuid4().hex[:8]}", order_id=order_id or uuid.uuid4(), status="approved")

    def test_refund_confirmation_form_renders(self, staff_client):
        order_return = self._make_return()
        response = staff_client.get(f"/django-admin/ordering/orderreturnmodel/{order_return.id}/refund/")
        assert response.status_code == 200
        assert order_return.return_number in response.content.decode()

    def test_refund_form_present_once_goods_are_received(self, staff_client):
        """The return workspace offers the refund step inline as soon as the goods are back."""
        order_return = self._make_return()
        order_return.status = "received"
        order_return.save(update_fields=["status"])
        response = staff_client.get(f"/django-admin/ordering/orderreturnmodel/{order_return.id}/change/")
        assert response.status_code == 200
        body = response.content.decode()
        assert 'name="action" value="refund"' in body
        assert "Record refund" in body

    def test_refund_exceeding_paid_amount_rejected(self, staff_client):
        """The existing, certified refund-amount-cap rule (refund <= paid amount) is exercised through the real Admin path, not bypassed."""
        order = _make_order(status=OrderStatus.COMPLETED, quantity=1, unit_price=Decimal("10000.00"))
        order_return = self._make_return(order_id=order.id)

        response = staff_client.post(
            f"/django-admin/ordering/orderreturnmodel/{order_return.id}/refund/",
            {"amount": "999999999.00", "currency": "UZS"},
        )
        assert response.status_code == 302  # redirected back with an error message, not a 500

        from apps.ordering.infrastructure import models as orm
        order_return.refresh_from_db()
        assert order_return.status == "approved"  # unchanged -- the refund was correctly rejected, not silently applied

    def test_non_staff_cannot_access_refund_view(self, non_staff_client):
        order_return = self._make_return()
        response = non_staff_client.get(f"/django-admin/ordering/orderreturnmodel/{order_return.id}/refund/")
        assert response.status_code in (302, 403)


class TestCrossWorkspaceRegression:
    """Phase 08.4 must not break Phase 08.2 (Dashboard) or Phase 08.3 (Commerce)."""

    def test_dashboard_home_still_renders(self, staff_client):
        response = staff_client.get("/django-admin/")
        assert response.status_code == 200
        assert "nz-dashboard" in response.content.decode()

    def test_commerce_products_still_renders(self, staff_client):
        response = staff_client.get("/django-admin/products/product/")
        assert response.status_code == 200
