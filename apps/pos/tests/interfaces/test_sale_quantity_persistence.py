"""
Regression: a cart line's quantity change (the POS "+" button) must be
persisted, not only returned in the API response.

The bug: DjangoSaleRepository.save() wrote new line items and deleted
removed ones but never updated an existing line's quantity. The cashier
saw 4 x 180 000 on screen (the in-memory response), while the database
kept quantity 1 -- so completing the sale reloaded it at quantity 1 and
the receipt, the change calculation, the Telegram Orders Channel post
and the stock decrement were all based on 1 item.
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

API = "/django-admin/pos/terminal/api"


@pytest.fixture
def staff_client():
    user = get_user_model().objects.create(username=f"nz_staff_{uuid.uuid4().hex[:8]}", is_staff=True, is_superuser=True)
    client = Client()
    client.force_login(user)
    return client


def _post(client, url, body=None):
    response = client.post(url, data=json.dumps(body or {}), content_type="application/json")
    assert response.status_code in (200, 201), response.content
    return response.json()["data"]


def _stocked_product(available=10):
    from apps.inventory.infrastructure import models as inv_orm
    from apps.products.infrastructure import models as p_models

    suffix = uuid.uuid4().hex[:8].upper()
    product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
    p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="uz", name="Creatine", slug=f"cr-{suffix.lower()}")
    variant = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{suffix}", is_default=True)
    inventory = inv_orm.InventoryModel.objects.create(id=uuid.uuid4(), code=f"INV-{suffix}", product_variant_id=variant.id, status="active")
    row = inv_orm.WarehouseInventoryModel.objects.create(id=uuid.uuid4(), inventory=inventory, warehouse_id=uuid.uuid4(), available_quantity=available)
    return product, row


def _sale_with_four_items(client, product):
    sale = _post(client, f"{API}/open-sale", {"branch_id": str(uuid.uuid4())})
    sale = _post(client, f"{API}/sales/{sale['id']}/line-items", {"product_id": str(product.id), "quantity": 1, "unit_price_amount": "180000", "unit_price_currency": "UZS"})
    line_id = sale["line_items"][0]["id"]
    for quantity in (2, 3, 4):
        sale = _post(client, f"{API}/sales/{sale['id']}/line-items/{line_id}/quantity", {"quantity": quantity})
    return sale


def test_quantity_change_is_persisted(staff_client):
    from apps.pos.infrastructure.models import SaleLineItemModel

    product, _row = _stocked_product()
    sale = _sale_with_four_items(staff_client, product)

    assert SaleLineItemModel.objects.get(sale_id=sale["id"]).quantity == 4


def test_completed_sale_charges_receipts_and_destocks_all_four_items(staff_client):
    from apps.pos.infrastructure.models import SaleModel

    product, row = _stocked_product(available=10)
    sale = _sale_with_four_items(staff_client, product)

    completed = _post(staff_client, f"{API}/sales/{sale['id']}/complete", {"delivery_fee": "30000"})

    assert Decimal(completed["total_amount"]) == Decimal("720000")
    assert completed["line_items"][0]["quantity"] == 4
    stored = SaleModel.objects.get(id=sale["id"])
    assert stored.delivery_fee_amount == Decimal("30000")
    row.refresh_from_db()
    assert row.available_quantity == 6


def test_orders_channel_post_uses_the_real_quantity_and_delivery_total(staff_client, settings):
    from apps.notifications.infrastructure import composition as notifications_composition
    from apps.telegram_bot.infrastructure.pos_sales_channel_subscriber import sync_pos_sales_channel

    product, _row = _stocked_product()
    sale = _sale_with_four_items(staff_client, product)
    _post(staff_client, f"{API}/sales/{sale['id']}/complete", {"delivery_fee": "30000"})

    sent = []

    class _Gateway:
        def send_message_with_keyboard(self, chat_id, text, keyboard):
            sent.append(text)
            return "1"

        def send_photo(self, chat_id, photo_url, caption, inline_keyboard=None):
            sent.append(caption)
            return "1"

    settings.TELEGRAM_ORDERS_CHAT_ID = "-100123"
    with patch.object(notifications_composition, "build_orders_telegram_gateway", return_value=_Gateway()):
        sync_pos_sales_channel()

    (text,) = [t for t in sent if "#" + sale["id"][:8].upper() in t]
    assert "4 x 180 000 so'm" in text
    assert "Jami: 750 000 so'm" in text
