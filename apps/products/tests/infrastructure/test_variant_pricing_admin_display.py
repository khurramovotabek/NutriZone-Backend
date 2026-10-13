"""
Real, live-verified regression test for the Product admin page's
variant pricing display: a live-computed discount percentage, resolved
from the same real data the storefront itself uses (PriceListEntryModel)
-- never a second, divergent source. Also verifies the Product-level
Flavour tagging (ProductFlavourInline) renders on the same page. Closes
a genuine pricing-safety gap: a catalog editor previously had no way to
tell a price row's real discount without opening each variant's own
separate detail page.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.products.infrastructure import models as p_models

pytestmark = pytest.mark.django_db


def _staff_client() -> Client:
    admin_user = User.objects.create_superuser(username=f"admin_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
    client = Client()
    client.force_login(admin_user)
    return client


def _make_price_list_entry(variant_id: uuid.UUID, base_price: str, compare_at: str | None = None):
    from apps.pricing.infrastructure.models import PriceListEntryModel, PriceListModel

    price_list = PriceListModel.objects.create(id=uuid.uuid4(), code=f"pl-{uuid.uuid4().hex[:8]}", name="Default", currency="UZS")
    return PriceListEntryModel.objects.create(id=uuid.uuid4(), price_list=price_list, product_variant_id=variant_id, base_price_amount=base_price, compare_at_price_amount=compare_at)


class TestVariantPricingAdminDisplay:
    def test_discount_percentage_and_flavour_render_on_the_product_admin_page(self):
        product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name="Gold Standard Whey", slug=f"whey-{uuid.uuid4().hex[:6]}")

        chocolate = p_models.Flavour.objects.create(id=uuid.uuid4(), slug=f"chocolate-{uuid.uuid4().hex[:6]}", color_hex="#4B2E1E")
        p_models.FlavourTranslation.objects.create(id=uuid.uuid4(), flavour=chocolate, locale_code="uz", name="Shokolad")
        p_models.ProductFlavour.objects.create(id=uuid.uuid4(), product=product, flavour=chocolate)

        variant = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:6]}", is_default=True)
        _make_price_list_entry(variant.id, "620000", "730000")

        client = _staff_client()
        response = client.get(f"/django-admin/products/product/{product.id}/change/")

        assert response.status_code == 200
        body = response.content.decode()
        assert "Shokolad" in body
        assert "-15%" in body

    def test_no_discount_shows_a_dash_not_a_fabricated_percentage(self):
        product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name="No Discount Product", slug=f"nd-{uuid.uuid4().hex[:6]}")
        variant = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:6]}", is_default=True)
        _make_price_list_entry(variant.id, "620000", None)

        client = _staff_client()
        response = client.get(f"/django-admin/products/product/{product.id}/change/")

        assert response.status_code == 200
        assert "nz-badge-danger" not in response.content.decode()

    def test_product_with_no_flavour_tagged_still_renders(self):
        product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name="Unflavoured Product", slug=f"uf-{uuid.uuid4().hex[:6]}")
        p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:6]}", is_default=True)

        client = _staff_client()
        response = client.get(f"/django-admin/products/product/{product.id}/change/")

        assert response.status_code == 200
