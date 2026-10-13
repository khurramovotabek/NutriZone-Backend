"""Store detail's product list carries what a shopper needs: price, old price/discount, size and a link."""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from apps.identity.infrastructure import models as identity_orm
from apps.pricing.infrastructure.models import PriceListEntryModel, PriceListModel
from apps.products.infrastructure import models as p_models
from apps.stores.infrastructure.models import Store, StoreProductStock

pytestmark = pytest.mark.django_db


def test_store_products_show_price_discount_and_product_link():
    owner = identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", full_name="Owner", status="active")
    store = Store.objects.create(id=uuid.uuid4(), owner=owner, name="Filial", slug=f"filial-{uuid.uuid4().hex[:6]}")
    product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
    p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="uz", name="Kreatin", slug="kreatin-250")
    variant = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:6]}", weight_value=250, weight_unit="g")
    price_list = PriceListModel.objects.create(id=uuid.uuid4(), code=f"pl-{uuid.uuid4().hex[:6]}", name="Default", currency="UZS")
    PriceListEntryModel.objects.create(id=uuid.uuid4(), price_list=price_list, product_variant_id=variant.id, base_price_amount="850000", compare_at_price_amount="1000000")
    StoreProductStock.objects.create(store=store, product_variant=variant, quantity=7)

    item = APIClient().get(f"/api/v1/stores/{store.slug}").json()["data"]["products"][0]

    assert item["price"] == "850000.00" and item["compare_at_price"] == "1000000.00" and item["discount_percent"] == 15
    assert item["product_slug"] == "kreatin-250"
    assert item["weight_value"] == 250 and item["weight_unit"] == "g"
    assert item["quantity"] == 7
