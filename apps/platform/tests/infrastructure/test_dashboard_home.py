"""
Phase 08.2: NutriZone Admin Dashboard Home tests.

Access control and real-data rendering, using real database
fixtures -- not just status-code assertions, per this phase's own
explicit testing requirement.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.ordering.domain.aggregates import Order
from apps.ordering.domain.enums import OrderChannel, OrderStatus
from apps.ordering.domain.value_objects import OrderNumber
from apps.ordering.infrastructure import composition as ordering_composition
from apps.ordering.tests.factories import _next_order_number, make_address, make_line_item
from apps.platform.infrastructure.dashboard_home import DashboardHomeAggregator, DashboardPeriod
from common.utils.money import Money

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _make_completed_order(quantity=2, unit_price=Decimal("50000.00")):
    line = make_line_item(unit_price=Money(amount=unit_price, currency="UZS"), quantity=quantity)
    order = Order(
        id=uuid.uuid4(), order_number=OrderNumber(_next_order_number()), customer_id=uuid.uuid4(), cart_id=uuid.uuid4(),
        shipping_address=make_address(), billing_address=make_address(), currency="UZS", channel=OrderChannel.WEB,
        status=OrderStatus.COMPLETED, lines={line.id: line}, placed_at=datetime.utcnow(),
    )
    return ordering_composition.build_order_repository().save(order)


class TestDashboardHomeAccess:
    def test_anonymous_denied(self):
        response = Client().get("/django-admin/")
        assert response.status_code in (302, 403)  # redirected to login, not shown the dashboard

    def test_non_staff_customer_denied(self):
        User = get_user_model()
        user = User.objects.create(username="nz_customer", is_staff=False)
        user.set_password("pw")
        user.save()
        client = Client()
        client.force_login(user)
        response = client.get("/django-admin/")
        assert response.status_code in (302, 403)

    def test_staff_user_sees_dashboard(self):
        User = get_user_model()
        user = User.objects.create(username="nz_staff", is_staff=True)
        user.set_password("pw")
        user.save()
        client = Client()
        client.force_login(user)
        response = client.get("/django-admin/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "nz-dashboard" in content
        assert "nz-kpi-grid" in content

    def test_superuser_sees_dashboard(self):
        User = get_user_model()
        user = User.objects.create(username="nz_super", is_staff=True, is_superuser=True)
        user.set_password("pw")
        user.save()
        client = Client()
        client.force_login(user)
        response = client.get("/django-admin/")
        assert response.status_code == 200
        assert "nz-dashboard" in response.content.decode()


class TestDashboardHomeRealData:
    def test_empty_database_shows_zero_not_crash(self):
        """No orders, customers, or products exist -- the dashboard must render real zeros, not crash, not fabricate numbers."""
        period = DashboardPeriod.last_n_days(7, "Last 7 Days")
        kpis = DashboardHomeAggregator(period).kpis()
        assert kpis["revenue"]["current"] == Decimal("0")
        assert kpis["revenue"]["change"]["value"] is None  # no previous data, not a fabricated 0% or crash
        assert kpis["orders"]["current"] == 0

    def test_completed_order_revenue_reflected_in_kpis(self):
        """A real completed order in the database must actually change the KPI numbers -- proves the aggregator is reading real data, not returning a static shape."""
        _make_completed_order(quantity=2, unit_price=Decimal("50000.00"))

        period = DashboardPeriod.last_n_days(7, "Last 7 Days")
        kpis = DashboardHomeAggregator(period).kpis()
        assert kpis["revenue"]["current"] == Decimal("100000.00")
        assert kpis["orders"]["current"] == 1
        assert kpis["average_order_value"] == Decimal("100000.00")

    def test_recent_orders_reflects_real_order(self):
        order = _make_completed_order()
        period = DashboardPeriod.last_n_days(7, "Last 7 Days")
        recent = DashboardHomeAggregator(period).recent_orders()
        assert any(o["id"] == str(order.id) for o in recent)

    def test_revenue_series_has_one_entry_per_day(self):
        period = DashboardPeriod.last_n_days(7, "Last 7 Days")
        series = DashboardHomeAggregator(period).revenue_series(days=7)
        assert len(series) == 7

    def test_dashboard_renders_real_revenue_number_in_html(self):
        """End-to-end: a real order's revenue actually appears in the rendered page, not just in the aggregator's own return value."""
        _make_completed_order(quantity=1, unit_price=Decimal("75000.00"))

        User = get_user_model()
        user = User.objects.create(username="nz_staff2", is_staff=True)
        user.set_password("pw")
        user.save()
        client = Client()
        client.force_login(user)
        response = client.get("/django-admin/")
        assert response.status_code == 200
        assert "75 000" in response.content.decode()

    def test_recent_orders_shows_translated_status_not_raw_enum_value(self):
        """
        Phase 17.0: closes a real gap found in this otherwise-complete
        template -- {{ order.status }} previously rendered the raw
        OrderStatus enum value (e.g. "pending_payment") as visible text,
        not a translated label.
        """
        order = _make_completed_order(quantity=1, unit_price=Decimal("30000.00"))

        User = get_user_model()
        user = User.objects.create(username=f"nz_staff_{uuid.uuid4().hex[:8]}", is_staff=True)
        user.set_password("pw")
        user.save()
        client = Client()
        client.force_login(user)

        response = client.get("/django-admin/")
        assert response.status_code == 200
        body = response.content.decode()
        assert "Completed" in body  # the real, translated label for OrderStatus.COMPLETED
        assert f">{order.status.value}<" not in body  # the raw enum value must never leak as visible text
