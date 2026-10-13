"""
Phase 08.7: NutriZone Admin Marketing & Promotions Workspace tests.

Real database fixtures throughout, covering Coupons and Campaigns
(Pricing bounded context). No Banner model exists anywhere in this
project -- confirmed by direct search, disclosed as a genuine
architectural limitation, not fabricated. "Promotions" as a concept
separate from Campaign also does not exist: Campaign (with its own
CampaignTargetModel for product/category targeting) is this
project's real equivalent.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone as tz

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


def _make_coupon(code_suffix=None, status="active"):
    from apps.pricing.infrastructure import models as orm

    return orm.CouponModel.objects.create(
        code=f"C{code_suffix or uuid.uuid4().hex[:6].upper()}", coupon_type="coupon",
        discount_value_type="fixed_amount", discount_fixed_amount=1000, status=status,
    )


def _make_campaign(name_suffix=None, status="draft"):
    from apps.pricing.infrastructure import models as orm

    return orm.CampaignModel.objects.create(
        name=f"Campaign {name_suffix or uuid.uuid4().hex[:6]}", campaign_type="campaign",
        discount_value_type="percentage", discount_percentage=10, validity_starts_at=datetime.now(tz.utc), status=status,
    )


class TestNoBannerModel:
    """Genuine architectural limitation, confirmed by direct search: no Banner model exists anywhere in this project."""

    def test_no_banner_related_admin_route_exists(self):
        User = get_user_model()
        user = User.objects.create(username=f"nz_banner_check_{uuid.uuid4().hex[:6]}", is_staff=True, is_superuser=True)
        client = Client()
        client.force_login(user)
        for path in ("/django-admin/pricing/bannermodel/", "/django-admin/products/bannermodel/"):
            response = client.get(path)
            assert response.status_code == 404


class TestCouponsAccessControl:
    def test_anonymous_denied(self):
        response = Client().get("/django-admin/pricing/couponmodel/")
        assert response.status_code in (302, 403)

    def test_non_staff_denied(self, non_staff_client):
        response = non_staff_client.get("/django-admin/pricing/couponmodel/")
        assert response.status_code in (302, 403)

    def test_non_staff_cannot_access_coupon_by_id(self, non_staff_client):
        coupon = _make_coupon()
        response = non_staff_client.get(f"/django-admin/pricing/couponmodel/{coupon.id}/change/")
        assert response.status_code in (302, 403)

    def test_staff_with_explicit_view_permission_but_not_superuser(self):
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType
        from apps.pricing.infrastructure import models as orm

        User = get_user_model()
        user = User.objects.create(username=f"nz_permstaff_{uuid.uuid4().hex[:8]}", is_staff=True, is_superuser=False)
        user.set_password("pw")
        user.save()
        content_type = ContentType.objects.get_for_model(orm.CouponModel)
        permission, _ = Permission.objects.get_or_create(codename="view_couponmodel", content_type=content_type, defaults={"name": "Can view coupon model"})
        user.user_permissions.add(permission)

        client = Client()
        client.force_login(user)
        response = client.get("/django-admin/pricing/couponmodel/")
        assert response.status_code == 200

        # Campaigns were removed from the admin surface entirely (see
        # CampaignAdmin's own docstring) -- the route no longer exists
        # at all, so this staff member (or anyone) gets a 404, not a
        # permission-denied 403.
        response = client.get("/django-admin/pricing/campaignmodel/")
        assert response.status_code == 404


class TestCouponsWorkspace:
    def test_list_shows_real_coupon(self, staff_client):
        _make_coupon(code_suffix="VISIBLE1")
        response = staff_client.get("/django-admin/pricing/couponmodel/")
        assert response.status_code == 200
        assert "CVISIBLE1" in response.content.decode()

    def test_search_finds_by_code(self, staff_client):
        _make_coupon(code_suffix="SEARCH99")
        response = staff_client.get("/django-admin/pricing/couponmodel/?q=SEARCH99")
        assert response.status_code == 200
        assert "CSEARCH99" in response.content.decode()

    def test_filter_by_status(self, staff_client):
        _make_coupon(code_suffix="STATUSCK", status="active")
        response = staff_client.get("/django-admin/pricing/couponmodel/?status__exact=active")
        assert response.status_code == 200
        assert "CSTATUSCK" in response.content.decode()

    def test_no_n_plus_1_on_coupon_list(self, staff_client):
        """Regression test for the confirmed, fixed N+1 (redemption_preview() had no prefetch at all before this phase's own fix)."""
        for i in range(5):
            _make_coupon(code_suffix=f"N1A{i:03d}")

        with CaptureQueriesContext(connection) as ctx:
            response = staff_client.get("/django-admin/pricing/couponmodel/")
        assert response.status_code == 200
        count_5 = len(ctx.captured_queries)

        for i in range(5, 10):
            _make_coupon(code_suffix=f"N1B{i:03d}")

        with CaptureQueriesContext(connection) as ctx:
            response = staff_client.get("/django-admin/pricing/couponmodel/")
        assert response.status_code == 200
        count_10 = len(ctx.captured_queries)

        assert count_10 < count_5 + 3, f"Query count grew from {count_5} to {count_10} for 5 more coupons -- possible N+1"

    def test_revoke_action_wired_to_real_service_and_persists(self, staff_client):
        """Phase 08.7: closes a real, confirmed gap -- RevokeCoupon existed but was never wired. Verifies real persisted state, not just the HTTP response."""
        coupon = _make_coupon(code_suffix="REVOKEME", status="active")

        response = staff_client.post(
            "/django-admin/pricing/couponmodel/",
            {"action": "revoke_selected", "_selected_action": [str(coupon.id)]},
            follow=True,
        )
        assert response.status_code == 200

        coupon.refresh_from_db()
        assert coupon.status == "revoked"


class TestCampaignsRemovedFromAdmin:
    """
    Real, product-required simplification (this phase's own explicit
    instruction to drop Campaigns from the visible admin surface, to
    avoid unnecessary complexity): `CampaignAdmin` is no longer
    registered (see its own docstring in apps/pricing/infrastructure/
    admin.py) -- the admin route genuinely no longer exists for
    anyone. The underlying `CampaignModel`/`EndCampaign` Application
    Service are untouched and still covered directly at the
    application layer (apps/pricing/tests/application/test_rules_campaigns.py) --
    only this Django-admin-integration surface is gone.
    """

    def test_campaign_admin_route_no_longer_exists(self, staff_client):
        _make_campaign(name_suffix="removedcamp")
        response = staff_client.get("/django-admin/pricing/campaignmodel/")
        assert response.status_code == 404


class TestCrossWorkspaceRegression:
    """Phase 08.7 must not break Phase 08.2/08.3/08.4/08.5/08.6."""

    def test_dashboard_home_still_renders(self, staff_client):
        response = staff_client.get("/django-admin/")
        assert response.status_code == 200
        assert "nz-dashboard" in response.content.decode()

    def test_commerce_products_still_renders(self, staff_client):
        response = staff_client.get("/django-admin/products/product/")
        assert response.status_code == 200

    def test_crm_customers_still_renders(self, staff_client):
        response = staff_client.get("/django-admin/identity/user/")
        assert response.status_code == 200
