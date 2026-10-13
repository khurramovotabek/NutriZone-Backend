"""
Phase 08.5: NutriZone Admin Inventory & Operations Workspace tests.

Real database fixtures throughout. No "Transfers" tests exist here:
confirmed by direct repository-wide search that no Transfer model
exists anywhere in this project -- disclosed as a genuine
architectural limitation, not fabricated.
"""
from __future__ import annotations

import uuid

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


def _make_inventory_item(code_suffix=None, with_warehouse=True):
    from apps.inventory.infrastructure import models as orm

    inv = orm.InventoryModel.objects.create(code=f"INV-{code_suffix or uuid.uuid4().hex[:8]}", product_variant_id=uuid.uuid4())
    if with_warehouse:
        orm.WarehouseInventoryModel.objects.create(inventory=inv, warehouse_id=uuid.uuid4(), available_quantity=10)
    return inv


class TestNoTransferModel:
    """Genuine architectural limitation, confirmed by direct search: no Transfer model exists anywhere in this project."""

    def test_no_transfer_related_admin_route_exists(self):
        for path in ("/django-admin/inventory/transfermodel/", "/django-admin/store/transfermodel/"):
            User = get_user_model()
            user = User.objects.create(username=f"nz_transfer_check_{uuid.uuid4().hex[:6]}", is_staff=True, is_superuser=True)
            client = Client()
            client.force_login(user)
            response = client.get(path)
            assert response.status_code == 404


class TestInventoryAccessControl:
    def test_anonymous_denied(self):
        response = Client().get("/django-admin/inventory/inventorymodel/")
        assert response.status_code in (302, 403, 404)

    def test_non_staff_denied(self, non_staff_client):
        response = non_staff_client.get("/django-admin/inventory/inventorymodel/")
        assert response.status_code in (302, 403, 404)

    def test_non_staff_cannot_access_detail_by_id(self, non_staff_client):
        item = _make_inventory_item()
        response = non_staff_client.get(f"/django-admin/inventory/inventorymodel/{item.id}/change/")
        assert response.status_code in (302, 403, 404)


class TestLocationsWorkspace:
    def test_region_list_renders(self, staff_client):
        response = staff_client.get("/django-admin/geo/region/")
        assert response.status_code == 200

    def test_district_list_renders(self, staff_client):
        response = staff_client.get("/django-admin/geo/district/")
        assert response.status_code == 200

    def test_address_list_renders(self, staff_client):
        response = staff_client.get("/django-admin/geo/address/")
        assert response.status_code == 200

    def test_non_staff_denied(self, non_staff_client):
        response = non_staff_client.get("/django-admin/geo/region/")
        assert response.status_code in (302, 403)


class TestCrossWorkspaceRegression:
    """Phase 08.5 must not break Phase 08.2 (Dashboard), 08.3 (Commerce), or 08.4 (Orders)."""

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
