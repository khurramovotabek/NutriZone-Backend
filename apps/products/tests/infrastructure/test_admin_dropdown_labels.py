"""
Confirmed, real bug: Category.__str__, Brand.__str__, and
Product.__str__ all literally returned `str(self.id)` -- the raw
UUID, not a readable name. Since Django Admin's default ForeignKey
widget labels each dropdown option using the related model's own
__str__, every Product create/edit page showed unreadable UUIDs for
Category and Brand selection instead of their names.

Fixed by using the first available translation from the model's own
`translations` related manager (this project's own established
translation-table pattern), with a safe fallback to the ID only if no
translation exists at all -- never crashes.

Every scenario here was verified live via a real admin form request
before being formalized.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.products.infrastructure import models as orm

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def staff_client():
    User = get_user_model()
    user = User.objects.create(username=f"nz_staff_{uuid.uuid4().hex[:8]}", is_staff=True, is_superuser=True)
    client = Client()
    client.force_login(user)
    return client


class TestCategoryStrReturnsReadableName:
    def test_str_returns_translated_name_not_uuid(self):
        category = orm.Category.objects.create(id=uuid.uuid4(), is_active=True, sort_order=1)
        orm.CategoryTranslation.objects.create(id=uuid.uuid4(), category=category, locale_code="uz", name="Protein Kukunlari", slug=f"protein-{uuid.uuid4().hex[:6]}")

        assert str(category) == "Protein Kukunlari"
        assert str(category) != str(category.id)

    def test_str_falls_back_to_id_when_no_translation_exists(self):
        category = orm.Category.objects.create(id=uuid.uuid4(), is_active=True, sort_order=1)
        assert str(category) == str(category.id)


class TestBrandStrReturnsReadableName:
    def test_str_returns_translated_name_not_uuid(self):
        brand = orm.Brand.objects.create(id=uuid.uuid4())
        orm.BrandTranslation.objects.create(id=uuid.uuid4(), brand=brand, locale_code="uz", name="Optimum Nutrition", slug=f"on-{uuid.uuid4().hex[:6]}")

        assert str(brand) == "Optimum Nutrition"
        assert str(brand) != str(brand.id)


class TestProductStrReturnsReadableName:
    def test_str_returns_translated_name_not_uuid(self):
        category = orm.Category.objects.create(id=uuid.uuid4(), is_active=True, sort_order=1)
        product = orm.Product.objects.create(id=uuid.uuid4(), status="published", category=category)
        orm.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="uz", name="Whey Protein 2kg", slug=f"whey-{uuid.uuid4().hex[:6]}")

        assert str(product) == "Whey Protein 2kg"
        assert str(product) != str(product.id)


class TestProductAdminFormShowsReadableDropdowns:
    def test_product_add_page_shows_readable_category_and_brand_labels(self, staff_client):
        category = orm.Category.objects.create(id=uuid.uuid4(), is_active=True, sort_order=1)
        orm.CategoryTranslation.objects.create(id=uuid.uuid4(), category=category, locale_code="uz", name="Protein Kukunlari", slug=f"protein-{uuid.uuid4().hex[:6]}")
        brand = orm.Brand.objects.create(id=uuid.uuid4())
        orm.BrandTranslation.objects.create(id=uuid.uuid4(), brand=brand, locale_code="uz", name="Optimum Nutrition", slug=f"on-{uuid.uuid4().hex[:6]}")

        response = staff_client.get("/django-admin/products/product/add/")
        assert response.status_code == 200
        body = response.content.decode()
        assert "Protein Kukunlari" in body
        assert "Optimum Nutrition" in body
        assert f">{category.id}<" not in body
        assert f">{brand.id}<" not in body


class TestProductVariantStrReturnsReadableName:
    """Phase 17.0: extends the same fix to ProductVariant -- the most frequently-referenced foreign key throughout the project (cart, pricing, POS all reference product_variant_id)."""

    def test_str_combines_product_name_and_sku(self):
        category = orm.Category.objects.create(id=uuid.uuid4(), is_active=True, sort_order=1)
        product = orm.Product.objects.create(id=uuid.uuid4(), status="published", category=category)
        orm.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="uz", name="Whey Protein 2kg", slug=f"whey-{uuid.uuid4().hex[:6]}")
        variant = orm.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku="WHEY-2KG-VANILLA", status="active", is_default=True)

        assert str(variant) == "Whey Protein 2kg — WHEY-2KG-VANILLA"
        assert str(variant.id) not in str(variant)

    def test_variant_add_page_shows_readable_product_label(self, staff_client):
        category = orm.Category.objects.create(id=uuid.uuid4(), is_active=True, sort_order=1)
        product = orm.Product.objects.create(id=uuid.uuid4(), status="published", category=category)
        orm.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="uz", name="Creatine Monohydrate", slug=f"creatine-{uuid.uuid4().hex[:6]}")

        assert staff_client.get("/django-admin/products/productvariant/add/").status_code == 200
        # The variant page's product field is an autocomplete: its options come from the admin autocomplete endpoint.
        response = staff_client.get("/django-admin/autocomplete/", {"app_label": "products", "model_name": "productvariant", "field_name": "product", "term": "Creatine"})
        assert response.status_code == 200
        labels = [r["text"] for r in response.json()["results"] if r["id"] == str(product.id)]
        assert labels and "Creatine Monohydrate" in labels[0]
        assert str(product.id) not in labels[0]


class TestTagFlavourStrReturnReadableNames:
    """Phase 17.0: closes the same gap for admin-registered catalog models that previously had no __str__ at all (Django's own generic 'Object (uuid)' fallback applied)."""

    def test_tag_str_uses_translation_when_available(self):
        tag = orm.Tag.objects.create(id=uuid.uuid4(), code="high-protein")
        orm.TagTranslation.objects.create(id=uuid.uuid4(), tag=tag, locale_code="uz", name="Yuqori Protein")
        assert str(tag) == "Yuqori Protein"

    def test_tag_str_falls_back_to_code_not_uuid(self):
        tag = orm.Tag.objects.create(id=uuid.uuid4(), code="high-protein")
        assert str(tag) == "high-protein"
        assert str(tag.id) not in str(tag)

    def test_flavour_str_uses_translation_when_available(self):
        flavour = orm.Flavour.objects.create(id=uuid.uuid4(), slug=f"vanilla-{uuid.uuid4().hex[:6]}", color_hex="#F5DEB3")
        orm.FlavourTranslation.objects.create(id=uuid.uuid4(), flavour=flavour, locale_code="uz", name="Vanil")
        assert str(flavour) == "Vanil"

    def test_flavour_str_falls_back_to_id_without_crashing(self):
        flavour = orm.Flavour.objects.create(id=uuid.uuid4(), slug=f"vanilla-{uuid.uuid4().hex[:6]}", color_hex="#F5DEB3")
        assert str(flavour.id) in str(flavour)
