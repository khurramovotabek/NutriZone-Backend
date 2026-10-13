"""
Real, live-verified regression test for Phase B1/B3: ProductVariant
itself has no price/stock field (confirmed via direct model
inspection) -- these are bulk-loaded from the separate pricing/
inventory bounded contexts via a loose product_variant_id UUID
reference. Every scenario here was proven live via a real admin
request before being formalized.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.pricing.infrastructure import models as pr_models
from apps.products.infrastructure import models as p_models
from apps.products.tests.stock_helpers import put_stock

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_client():
    user = User.objects.create_superuser(username=f"admin_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
    client = Client()
    client.force_login(user)
    return client


def _make_priced_stocked_variant(product, is_default=True, price=100000, stock=10):
    variant = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:8]}", status="active", is_default=is_default)
    price_list = pr_models.PriceListModel.objects.create(id=uuid.uuid4(), code=f"PL-{uuid.uuid4().hex[:6]}", name="Default", currency="UZS", status="active")
    pr_models.PriceListEntryModel.objects.create(id=uuid.uuid4(), price_list=price_list, product_variant_id=variant.id, base_price_amount=price)
    put_stock(variant.id, stock)
    return variant


class TestProductVariantRealPriceStock:
    def test_variant_inline_shows_real_price_and_stock(self, staff_client):
        product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name="Whey Protein", slug=f"whey-{uuid.uuid4().hex[:6]}")
        _make_priced_stocked_variant(product, price=780000, stock=24)

        response = staff_client.get(f"/django-admin/products/product/{product.id}/change/")
        assert response.status_code == 200
        body = response.content.decode()
        assert "780000" in body
        assert "24" in body


class TestProductListRealPriceStock:
    def test_product_with_default_variant_shows_its_price_and_stock(self, staff_client):
        product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name="Priced Product", slug=f"priced-{uuid.uuid4().hex[:6]}")
        _make_priced_stocked_variant(product, price=549000, stock=15)

        response = staff_client.get("/django-admin/products/product/")
        assert response.status_code == 200
        body = response.content.decode()
        assert "549000" in body
        assert "15" in body

    def test_product_without_any_variant_does_not_crash(self, staff_client):
        product = p_models.Product.objects.create(id=uuid.uuid4(), status="draft")
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name="No Variant Product", slug=f"no-variant-{uuid.uuid4().hex[:6]}")

        response = staff_client.get("/django-admin/products/product/")
        assert response.status_code == 200


class TestProductMediaPreviewUsesThumbnail:
    def test_preview_uses_small_thumbnail_not_full_size_original(self, staff_client):
        product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name="Test Product", slug=f"test-{uuid.uuid4().hex[:6]}")
        p_models.ProductMedia.objects.create(id=uuid.uuid4(), product=product, storage_path="products/full.webp", thumbnail_paths={"small": "products/full_small.webp"}, media_role="primary", sort_order=0)

        response = staff_client.get(f"/django-admin/products/product/{product.id}/change/")
        assert response.status_code == 200
        body = response.content.decode()
        assert "products/full_small.webp" in body
        assert body.count("products/full.webp") == 0
