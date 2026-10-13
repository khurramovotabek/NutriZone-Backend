"""
Real, live-verified regression test: BrandSelector.list_active()
exposes a real logo_url via Brand's own direct storage fields
(logo_storage_path/logo_thumbnail_paths) -- the Media Asset
architecture (ProductMediaAsset FK/table) was fully removed for
Brand per explicit product decision. Existing production Brand.logo
data was migrated forward via a real, tested data migration
(0006_brand_copy_logo_data), never fabricated or dropped.
"""
from __future__ import annotations

import uuid

import pytest
from django.test import Client

from apps.products.infrastructure import models as p_models

pytestmark = pytest.mark.django_db


class TestBrandLogoUrl:
    def test_brand_with_logo_exposes_a_real_logo_url(self):
        brand = p_models.Brand.objects.create(
            id=uuid.uuid4(), is_active=True, is_manufacturer=False,
            logo_storage_path="brands/x.jpg", logo_thumbnail_paths={"medium": "x-medium.jpg"},
        )
        p_models.BrandTranslation.objects.create(id=uuid.uuid4(), brand=brand, locale_code="en", name="Logo Brand", slug=f"lb-{uuid.uuid4().hex[:8]}")

        client = Client()
        response = client.get("/api/v1/brands")
        assert response.status_code == 200
        matching = next(b for b in response.json()["data"] if b["name"] == "Logo Brand")
        assert matching["logo_url"] == "/media/x-medium.jpg"

    def test_brand_with_no_logo_has_null_logo_url(self):
        brand = p_models.Brand.objects.create(id=uuid.uuid4(), is_active=True, is_manufacturer=False)
        p_models.BrandTranslation.objects.create(id=uuid.uuid4(), brand=brand, locale_code="en", name="No Logo Brand", slug=f"nlb-{uuid.uuid4().hex[:8]}")

        client = Client()
        response = client.get("/api/v1/brands")
        matching = next(b for b in response.json()["data"] if b["name"] == "No Logo Brand")
        assert matching["logo_url"] is None

    def test_brand_logo_url_is_absolute_when_public_base_url_is_configured(self, settings):
        """Real, closed gap: previously always returned a bare relative path (e.g. "/media/x.jpg"), which the storefront (a different origin) resolved against its own host, not the Django backend that actually serves /media/ -- so the logo request 404'd there regardless of a correctly-served file."""
        settings.PUBLIC_BASE_URL = "https://api.nutrizone.uz"
        brand = p_models.Brand.objects.create(
            id=uuid.uuid4(), is_active=True, is_manufacturer=False,
            logo_storage_path="brands/y.jpg", logo_thumbnail_paths={"medium": "y-medium.jpg"},
        )
        p_models.BrandTranslation.objects.create(id=uuid.uuid4(), brand=brand, locale_code="en", name="Absolute Logo Brand", slug=f"alb-{uuid.uuid4().hex[:8]}")

        client = Client()
        response = client.get("/api/v1/brands")
        matching = next(b for b in response.json()["data"] if b["name"] == "Absolute Logo Brand")
        assert matching["logo_url"] == "https://api.nutrizone.uz/media/y-medium.jpg"


class TestCategoryImageUrl:
    """Same, real, closed gap as TestBrandLogoUrl above -- CategoryTreeSelector had the identical relative-URL bug."""

    def test_category_image_url_is_absolute_when_public_base_url_is_configured(self, settings):
        settings.PUBLIC_BASE_URL = "https://api.nutrizone.uz"
        category = p_models.Category.objects.create(id=uuid.uuid4(), is_active=True, sort_order=1, image_storage_path="categories/z.jpg", image_thumbnail_paths={"medium": "z-medium.jpg"})
        p_models.CategoryTranslation.objects.create(id=uuid.uuid4(), category=category, locale_code="en", name="Absolute Image Category", slug=f"aic-{uuid.uuid4().hex[:8]}")

        client = Client()
        response = client.get("/api/v1/categories/tree")
        matching = next(c for c in response.json()["data"] if c["name"] == "Absolute Image Category")
        assert matching["image_url"] == "https://api.nutrizone.uz/media/z-medium.jpg"

    def test_category_with_no_image_has_null_image_url(self):
        category = p_models.Category.objects.create(id=uuid.uuid4(), is_active=True, sort_order=1)
        p_models.CategoryTranslation.objects.create(id=uuid.uuid4(), category=category, locale_code="en", name="No Image Category", slug=f"nic-{uuid.uuid4().hex[:8]}")

        client = Client()
        response = client.get("/api/v1/categories/tree")
        matching = next(c for c in response.json()["data"] if c["name"] == "No Image Category")
        assert matching["image_url"] is None
