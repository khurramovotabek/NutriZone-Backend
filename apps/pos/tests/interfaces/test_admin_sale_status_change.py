"""
Sales history status changes from the admin: refunding (returning) a
completed sale -- which restocks what was sold -- and cancelling an
abandoned open one. Both go through the real application services.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

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


def _stocked_product(available: int):
    """A real product/default variant with one warehouse row holding `available` units."""
    from apps.inventory.infrastructure import models as inv_orm
    from apps.products.infrastructure import models as p_models

    suffix = uuid.uuid4().hex[:8].upper()
    product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
    variant = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{suffix}", is_default=True)
    inventory = inv_orm.InventoryModel.objects.create(id=uuid.uuid4(), code=f"INV-{suffix}", product_variant_id=variant.id, status="active")
    row = inv_orm.WarehouseInventoryModel.objects.create(id=uuid.uuid4(), inventory=inventory, warehouse_id=uuid.uuid4(), available_quantity=available)
    return product, row


def _sale(status: str, product_id=None, quantity=2):
    from apps.pos.infrastructure import models as orm

    sale = orm.SaleModel.objects.create(branch_id=uuid.uuid4(), cashier_id=uuid.uuid4(), status=status)
    orm.SaleLineItemModel.objects.create(sale=sale, product_id=product_id or uuid.uuid4(), quantity=quantity, unit_price_amount=Decimal("180000"), unit_price_currency="UZS")
    return sale


class TestRefund:
    def test_confirmation_page_shows_the_sale(self, staff_client):
        sale = _sale("completed")
        response = staff_client.get(f"/django-admin/pos/salemodel/{sale.id}/refund/")
        assert response.status_code == 200
        body = response.content.decode()
        assert "#" + str(sale.id)[:8].upper() in body
        assert "360 000" in body  # 2 x 180 000

    def test_post_refunds_and_restocks(self, staff_client):
        from apps.pos.infrastructure import models as orm

        product, row = _stocked_product(available=5)
        sale = _sale("completed", product_id=product.id, quantity=2)

        response = staff_client.post(f"/django-admin/pos/salemodel/{sale.id}/refund/")

        assert response.status_code == 302
        sale.refresh_from_db()
        assert sale.status == "refunded"
        assert sale.refunded_at is not None
        row.refresh_from_db()
        assert row.available_quantity == 7
        assert orm.PosOutboxEvent.objects.filter(event_type="SaleRefunded", payload__sale_id=str(sale.id)).exists()

    @pytest.mark.parametrize("status", ["open", "voided", "refunded"])
    def test_refund_is_refused_for_non_completed_sales(self, staff_client, status):
        sale = _sale(status)
        response = staff_client.post(f"/django-admin/pos/salemodel/{sale.id}/refund/")
        assert response.status_code == 302
        sale.refresh_from_db()
        assert sale.status == status

    def test_change_page_offers_the_refund_action(self, staff_client):
        sale = _sale("completed")
        body = staff_client.get(f"/django-admin/pos/salemodel/{sale.id}/change/").content.decode()
        assert f"/django-admin/pos/salemodel/{sale.id}/refund/" in body


class TestVoid:
    def test_post_voids_open_sale(self, staff_client):
        sale = _sale("open")
        response = staff_client.post(f"/django-admin/pos/salemodel/{sale.id}/void/")
        assert response.status_code == 302
        sale.refresh_from_db()
        assert sale.status == "voided"

    def test_void_is_refused_for_completed_sale(self, staff_client):
        sale = _sale("completed")
        staff_client.post(f"/django-admin/pos/salemodel/{sale.id}/void/")
        sale.refresh_from_db()
        assert sale.status == "completed"


def test_anonymous_cannot_refund():
    sale = _sale("completed")
    response = Client().post(f"/django-admin/pos/salemodel/{sale.id}/refund/")
    assert response.status_code in (302, 403)
    sale.refresh_from_db()
    assert sale.status == "completed"
