"""
Real, live-verified regression test for Category.image and
Brand.logo thumbnail rendering. Both Media Asset architectures
(ProductMediaAsset FK/table) were fully removed per explicit product
decision -- now use direct storage fields
(image_storage_path/image_thumbnail_paths and
logo_storage_path/logo_thumbnail_paths, respectively). The
ProductMediaAsset model itself is gone entirely.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.products.infrastructure import models as p_models

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_client():
    user = User.objects.create_superuser(username=f"admin_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
    client = Client()
    client.force_login(user)
    return client


class TestBrandLogoThumbnail:
    def test_brand_with_real_logo_shows_real_thumbnail_url(self, staff_client):
        brand = p_models.Brand.objects.create(id=uuid.uuid4(), logo_storage_path="brands/logo.webp", logo_thumbnail_paths={"small": "brands/logo_small.webp"})
        p_models.BrandTranslation.objects.create(id=uuid.uuid4(), brand=brand, locale_code="en", name="Optimum Nutrition", slug=f"optimum-{uuid.uuid4().hex[:6]}")

        response = staff_client.get("/django-admin/products/brand/")
        assert response.status_code == 200
        assert "brands/logo_small.webp" in response.content.decode()

    def test_brand_without_logo_shows_fallback_not_a_broken_image(self, staff_client):
        brand = p_models.Brand.objects.create(id=uuid.uuid4())
        p_models.BrandTranslation.objects.create(id=uuid.uuid4(), brand=brand, locale_code="en", name="No Logo Brand", slug=f"no-logo-{uuid.uuid4().hex[:6]}")

        response = staff_client.get("/django-admin/products/brand/")
        assert response.status_code == 200
        assert "nz-thumb-empty" in response.content.decode()


class TestCategoryImageThumbnail:
    def test_category_with_real_image_shows_real_thumbnail_url(self, staff_client):
        category = p_models.Category.objects.create(id=uuid.uuid4(), image_storage_path="categories/protein.webp", image_thumbnail_paths={"small": "categories/protein_small.webp"})
        p_models.CategoryTranslation.objects.create(id=uuid.uuid4(), category=category, locale_code="en", name="Protein", slug=f"protein-{uuid.uuid4().hex[:6]}")

        response = staff_client.get("/django-admin/products/category/")
        assert response.status_code == 200
        assert "categories/protein_small.webp" in response.content.decode()
