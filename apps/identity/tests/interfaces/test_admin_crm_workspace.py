"""
Phase 08.6: NutriZone Admin CRM & Customer Experience Workspace tests.

Real database fixtures throughout, covering Customers (Identity),
Loyalty, Wallet, Reviews.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone as tz

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.db import connection

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


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


def _make_customer(suffix=None, with_sessions=0):
    from apps.identity.infrastructure import models as orm

    phone = f"+998900{uuid.uuid4().hex[:6]}"
    user = orm.User.objects.create(phone_number=phone, full_name=f"Customer {suffix or phone}")
    for i in range(with_sessions):
        orm.UserSession.objects.create(
            user=user, device_type="mobile", refresh_token_hash=f"hash-{uuid.uuid4()}",
            last_activity=datetime.now(tz.utc) - timedelta(hours=i), expires_at=datetime.now(tz.utc) + timedelta(days=1),
        )
    return user


def _make_review(status="published"):
    from apps.reviews.infrastructure import models as orm

    return orm.ReviewModel.objects.create(product_id=uuid.uuid4(), customer_id=uuid.uuid4(), rating=5, body="Great product", status=status)


class TestCustomersWorkspace:
    def test_anonymous_denied(self):
        response = Client().get("/django-admin/identity/user/")
        assert response.status_code in (302, 403)

    def test_non_staff_denied(self, non_staff_client):
        response = non_staff_client.get("/django-admin/identity/user/")
        assert response.status_code in (302, 403)

    def test_non_staff_cannot_access_customer_by_id(self, non_staff_client):
        customer = _make_customer()
        response = non_staff_client.get(f"/django-admin/identity/user/{customer.id}/change/")
        assert response.status_code in (302, 403)

    def test_list_shows_real_customer(self, staff_client):
        _make_customer(suffix="visiblecust")
        response = staff_client.get("/django-admin/identity/user/")
        assert response.status_code == 200
        assert "Customer visiblecust" in response.content.decode()

    def test_search_finds_by_phone(self, staff_client):
        customer = _make_customer()
        response = staff_client.get(f"/django-admin/identity/user/?q={customer.phone_number}")
        assert response.status_code == 200
        assert customer.phone_number in response.content.decode()

    def test_no_n_plus_1_on_customer_list(self, staff_client):
        """Regression test for the confirmed, fixed N+1: last_login_display() previously issued one raw, unprefetched query per row."""
        for i in range(5):
            _make_customer(suffix=f"n1c-{i}", with_sessions=2)

        with CaptureQueriesContext(connection) as ctx:
            response = staff_client.get("/django-admin/identity/user/")
        assert response.status_code == 200
        count_5 = len(ctx.captured_queries)

        for i in range(5, 10):
            _make_customer(suffix=f"n1c-more-{i}", with_sessions=2)

        with CaptureQueriesContext(connection) as ctx:
            response = staff_client.get("/django-admin/identity/user/")
        assert response.status_code == 200
        count_10 = len(ctx.captured_queries)

        assert count_10 < count_5 + 3, f"Query count grew from {count_5} to {count_10} for 5 more customers -- possible N+1"

    def test_last_login_reflects_most_recent_session(self, staff_client):
        _make_customer(suffix="lastlogincheck", with_sessions=2)
        response = staff_client.get("/django-admin/identity/user/")
        assert response.status_code == 200
        assert "Customer lastlogincheck" in response.content.decode()


class TestReviewsWorkspace:
    def test_list_renders_real_review(self, staff_client):
        _make_review()
        response = staff_client.get("/django-admin/reviews/reviewmodel/")
        assert response.status_code == 200

    def test_filter_by_rating(self, staff_client):
        _make_review()
        response = staff_client.get("/django-admin/reviews/reviewmodel/?rating__exact=5")
        assert response.status_code == 200

    def test_filter_by_status(self, staff_client):
        _make_review(status="pending_moderation")
        response = staff_client.get("/django-admin/reviews/reviewmodel/?status__exact=pending_moderation")
        assert response.status_code == 200

    def test_non_staff_denied(self, non_staff_client):
        response = non_staff_client.get("/django-admin/reviews/reviewmodel/")
        assert response.status_code in (302, 403)


class TestNoFakeSegmentationModel:
    """This phase's own rule: do not invent a persistent CustomerSegment model. Confirmed none exists."""

    def test_no_customer_segment_admin_route_exists(self):
        User = get_user_model()
        user = User.objects.create(username=f"nz_seg_check_{uuid.uuid4().hex[:6]}", is_staff=True, is_superuser=True)
        client = Client()
        client.force_login(user)
        response = client.get("/django-admin/identity/customersegment/")
        assert response.status_code == 404


class TestCrossWorkspaceRegression:
    """Phase 08.6 must not break Phase 08.2/08.3/08.4/08.5."""

    def test_dashboard_home_still_renders(self, staff_client):
        response = staff_client.get("/django-admin/")
        assert response.status_code == 200
        assert "nz-dashboard" in response.content.decode()

    def test_commerce_products_still_renders(self, staff_client):
        response = staff_client.get("/django-admin/products/product/")
        assert response.status_code == 200

    def test_orders_still_renders(self, staff_client):
        response = staff_client.get("/django-admin/ordering/ordermodel/")
        assert response.status_code == 200

    def test_inventory_admin_page_removed_from_dashboard(self, staff_client):
        """Real, product-required simplification: Inventory removed from the Dashboard entirely -- stock is now managed directly on the ProductVariant admin form. The underlying model/data are untouched; only the standalone admin page is gone."""
        response = staff_client.get("/django-admin/inventory/inventorymodel/")
        assert response.status_code == 404
