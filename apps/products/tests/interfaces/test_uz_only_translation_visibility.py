"""
Real, closed gaps found live during this phase's own investigation:

1. _product_card() (backs catalog list, product detail, search
   results, and similar/recommended products) only looked up the
   translation matching effective_locale, which defaults to "en" at
   every call site that never passes a locale explicitly (the
   overwhelming majority of them). A product with only a "uz"
   translation -- the ordinary case for this Uzbekistan-targeted
   project -- rendered a blank name on every product card across the
   entire storefront.

2. DjangoProductRepository.get_by_slug() and
   ProductDetailSelector.get_by_slug() both filtered translations by
   locale_code=_DEFAULT_LOCALE ("en") in addition to slug -- a
   "uz"-only product's real slug never matched, so the product detail
   page returned a hard 404 ("Product not found.") for every such
   product. The same gap existed in Brand/Category/Bundle
   get_by_slug() and in AdminListProducts' name search.
"""
from __future__ import annotations

import uuid

import pytest
from django.test import Client

from apps.products.infrastructure import models as p_models

pytestmark = pytest.mark.django_db


def _make_uz_only_product(name_suffix: str, sku_suffix: str) -> tuple:
    product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
    p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="uz", name=f"Faqat Uzbekcha {name_suffix}", slug=f"fu-{name_suffix.lower()}")
    variant = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{sku_suffix}", is_default=True)
    return product, variant


class TestCatalogListShowsRealNameForUzOnlyProducts:
    def test_catalog_list_shows_the_real_uz_name_not_a_blank_string(self):
        suffix = uuid.uuid4().hex[:8].upper()
        product, _variant = _make_uz_only_product(suffix, suffix)

        client = Client()
        response = client.get("/api/v1/products?page_size=1000")
        assert response.status_code == 200
        card = next((p for p in response.json()["data"] if p["id"] == str(product.id)), None)
        assert card is not None, "the uz-only product must appear in the catalog list at all"
        assert card["name"] == f"Faqat Uzbekcha {suffix}"
        assert card["name"] != ""


class TestProductDetailFindsUzOnlySlug:
    def test_product_detail_returns_200_not_404_for_a_uz_only_slug(self):
        suffix = uuid.uuid4().hex[:8].upper()
        product, variant = _make_uz_only_product(suffix, suffix)
        real_slug = product.translations.get(locale_code="uz").slug

        client = Client()
        response = client.get(f"/api/v1/products/{real_slug}")
        assert response.status_code == 200, "a uz-only product's own real slug must resolve, not 404"
        data = response.json()["data"]
        assert data["name"] == f"Faqat Uzbekcha {suffix}"
        assert len(data["variants"]) == 1
        assert data["variants"][0]["sku"] == f"SKU-{suffix}"


class TestAdminProductSearchFindsUzOnlyNames:
    def test_admin_search_finds_a_product_by_its_uz_only_name(self):
        from django.contrib.auth.models import User as AuthUser
        from django.contrib.contenttypes.models import ContentType

        ContentType.objects.clear_cache()
        suffix = uuid.uuid4().hex[:8].upper()
        product, _variant = _make_uz_only_product(suffix, suffix)

        admin_user = AuthUser.objects.create_superuser(username=f"admin_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
        client = Client()
        client.force_login(admin_user)

        response = client.get(f"/django-admin/products/product/?q=Faqat+Uzbekcha+{suffix}")
        assert response.status_code == 200
        assert f"Faqat Uzbekcha {suffix}" in response.content.decode()
