"""
Real, live-verified regression test for the Inventory admin dashboard
(apps/platform/infrastructure/inventory_view.py). Every scenario here
was proven live via a real staff request before being formalized.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.inventory.infrastructure import models as i_models
from apps.products.infrastructure import models as p_models

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_client():
    user = User.objects.create_superuser(username=f"admin_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
    client = Client()
    client.force_login(user)
    return client


class TestInventoryDashboard:
    def test_dashboard_shows_real_product_name_for_low_stock_item(self, staff_client):
        product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name="Whey Protein", slug=f"whey-{uuid.uuid4().hex[:6]}")
        variant = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:8]}", status="active")
        inventory = i_models.InventoryModel.objects.create(id=uuid.uuid4(), code=f"INV-{uuid.uuid4().hex[:6]}", product_variant_id=variant.id, status="active", low_stock_at=10)
        i_models.WarehouseInventoryModel.objects.create(id=uuid.uuid4(), inventory=inventory, warehouse_id=uuid.uuid4(), available_quantity=3)

        response = staff_client.get("/django-admin/inventory/")
        assert response.status_code == 200
        body = response.content.decode()
        assert "Whey Protein" in body
        assert variant.sku in body

    def test_dashboard_shows_expiring_batch(self, staff_client):
        product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name="Creatine", slug=f"creatine-{uuid.uuid4().hex[:6]}")
        variant = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:8]}", status="active")
        inventory = i_models.InventoryModel.objects.create(id=uuid.uuid4(), code=f"INV-{uuid.uuid4().hex[:6]}", product_variant_id=variant.id, status="active")
        batch = i_models.BatchModel.objects.create(id=uuid.uuid4(), inventory=inventory, batch_number=f"BATCH-{uuid.uuid4().hex[:6]}", status="active", expiration_date="2026-09-15", quantity_received=100)

        response = staff_client.get("/django-admin/inventory/")
        assert response.status_code == 200
        assert batch.batch_number in response.content.decode()

    def test_dashboard_with_no_data_does_not_crash(self, staff_client):
        response = staff_client.get("/django-admin/inventory/")
        assert response.status_code == 200
