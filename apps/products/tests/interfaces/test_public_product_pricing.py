"""
Real, live-verified regression test for Phase Pricing: the public
Product list/detail endpoints previously never exposed a price at
all -- confirmed directly from _product_card()'s own prior field set
and the storefront's own api.ts docstring disclosing this exact
omission. Every scenario here was proven live before being
formalized.
"""
from __future__ import annotations

import uuid

import pytest
from django.test import Client

from apps.pricing.infrastructure import models as pr_models
from apps.products.infrastructure import models as p_models

pytestmark = pytest.mark.django_db


def _make_priced_product(price: str = "549000") -> tuple[p_models.Product, str]:
    product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
    slug = f"tp-{uuid.uuid4().hex[:8]}"
    p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name="Test Product", slug=slug)
    sku = f"TP-{uuid.uuid4().hex[:6].upper()}"
    variant = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=sku, status="active", is_default=True)
    price_list = pr_models.PriceListModel.objects.create(id=uuid.uuid4(), code=f"PL-{uuid.uuid4().hex[:6]}", name="Default", currency="UZS", status="active")
    pr_models.PriceListEntryModel.objects.create(id=uuid.uuid4(), price_list=price_list, product_variant_id=variant.id, base_price_amount=price)
    return product, slug


class TestPublicProductPricing:
    def test_product_detail_exposes_real_price_and_currency(self):
        product, slug = _make_priced_product(price="549000")
        client = Client()
        response = client.get(f"/api/v1/products/{slug}")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["price"] == "549000.00"
        assert data["currency"] == "UZS"

    def test_product_list_exposes_real_price_for_the_same_product(self):
        product, slug = _make_priced_product(price="780000")
        client = Client()
        response = client.get("/api/v1/products?page_size=200")
        assert response.status_code == 200
        matching = next((p for p in response.json()["data"] if p["id"] == str(product.id)), None)
        assert matching is not None
        assert matching["price"] == "780000.00"
        assert matching["currency"] == "UZS"

    def test_product_without_any_variant_returns_null_price_not_an_error(self):
        product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
        slug = f"noprice-{uuid.uuid4().hex[:8]}"
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name="No Price Product", slug=slug)

        client = Client()
        response = client.get(f"/api/v1/products/{slug}")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["price"] is None
        assert data["currency"] is None
