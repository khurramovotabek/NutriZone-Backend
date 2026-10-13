"""
Real, live-verified regression test for the Product Detail page
redesign: the public detail endpoint previously exposed none of
description/gallery/specifications, and hard-coded default_variant_id
to null -- confirmed directly against `_product_card()`'s own prior
field set (see selectors.py's own `include_details` docstring).
"""
from __future__ import annotations

import uuid

import pytest
from django.test import Client

from apps.products.infrastructure import models as p_models

pytestmark = pytest.mark.django_db


class TestProductDetailRichFields:
    def test_description_gallery_specifications_and_default_variant_are_exposed(self):
        product = p_models.Product.objects.create(id=uuid.uuid4(), status="published", specifications=[
            {"key": "Protein per serving", "value": "25g", "sort_order": 2},
            {"key": "Flavor", "value": "Chocolate", "sort_order": 1},
            {"key": "Empty ignored", "value": "", "sort_order": 0},
        ])
        slug = f"rich-{uuid.uuid4().hex[:8]}"
        p_models.ProductTranslation.objects.create(
            id=uuid.uuid4(), product=product, locale_code="en", name="Rich Product", slug=slug, description="A genuinely long description.",
        )
        default_variant = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"RP-{uuid.uuid4().hex[:6].upper()}", status="active", is_default=True)
        p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"RP-{uuid.uuid4().hex[:6].upper()}", status="active", is_default=False)

        p_models.ProductMedia.objects.create(id=uuid.uuid4(), product=product, storage_path="image/primary.jpg", media_role="primary", sort_order=0)
        p_models.ProductMedia.objects.create(id=uuid.uuid4(), product=product, storage_path="image/gallery-2.jpg", media_role="gallery", sort_order=2)
        p_models.ProductMedia.objects.create(id=uuid.uuid4(), product=product, storage_path="image/gallery-1.jpg", media_role="gallery", sort_order=1)

        client = Client()
        response = client.get(f"/api/v1/products/{slug}")
        assert response.status_code == 200
        data = response.json()["data"]

        assert data["description"] == "A genuinely long description."

        # Primary image first, then gallery images in sort_order -- never fabricated, never reordered arbitrarily.
        assert len(data["gallery"]) == 3
        assert data["gallery"][0].endswith("image/primary.jpg")
        assert data["gallery"][1].endswith("image/gallery-1.jpg")
        assert data["gallery"][2].endswith("image/gallery-2.jpg")

        # Empty-value spec dropped; real ones sorted by sort_order, never by insertion order.
        assert data["specifications"] == [
            {"key": "Flavor", "value": "Chocolate"},
            {"key": "Protein per serving", "value": "25g"},
        ]

        # The confirmed default_variant_id-always-null bug is fixed on this endpoint specifically.
        assert data["default_variant_id"] == str(default_variant.id)

    def test_product_with_no_description_media_or_specs_returns_empty_not_broken(self):
        product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
        slug = f"bare-{uuid.uuid4().hex[:8]}"
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name="Bare Product", slug=slug)

        client = Client()
        response = client.get(f"/api/v1/products/{slug}")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["description"] == ""
        assert data["gallery"] == []
        assert data["specifications"] == []
        assert data["default_variant_id"] is None


class TestProductDetailSupplementFactsWarningsDirections:
    """Real, closed gap: supplement_facts_text_*/warnings_text_*/directions_text_* already existed on Product (edited via ProductAdmin's own fieldsets), but no public read endpoint ever surfaced them -- a customer could never see what's actually in the product they're buying."""

    def test_uz_locale_field_is_returned_for_a_uz_request(self):
        product = p_models.Product.objects.create(
            id=uuid.uuid4(), status="published",
            supplement_facts_text_uz="Har bir xizmatda 25g oqsil.", warnings_text_uz="18 yoshgacha tavsiya etilmaydi.", directions_text_uz="Kuniga 1 marta ichishga aralashtiring.",
        )
        slug = f"facts-{uuid.uuid4().hex[:8]}"
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="uz", name="Facts Product", slug=slug)

        client = Client()
        response = client.get(f"/api/v1/products/{slug}", HTTP_ACCEPT_LANGUAGE="uz")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["supplement_facts"] == "Har bir xizmatda 25g oqsil."
        assert data["warnings"] == "18 yoshgacha tavsiya etilmaydi."
        assert data["directions"] == "Kuniga 1 marta ichishga aralashtiring."

    def test_missing_locale_falls_back_to_uz_then_any_available(self):
        """A product with only an English translation of these 3 fields must never show blank to a uz/ru visitor when a real value exists in another language."""
        product = p_models.Product.objects.create(id=uuid.uuid4(), status="published", supplement_facts_text_en="25g protein per serving.")
        slug = f"facts-en-{uuid.uuid4().hex[:8]}"
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name="EN Only Product", slug=slug)

        client = Client()
        response = client.get(f"/api/v1/products/{slug}")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["supplement_facts"] == "25g protein per serving."

    def test_product_with_none_of_these_fields_returns_null_not_a_fabricated_value(self):
        product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
        slug = f"nofacts-{uuid.uuid4().hex[:8]}"
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name="No Facts Product", slug=slug)

        client = Client()
        response = client.get(f"/api/v1/products/{slug}")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["supplement_facts"] is None
        assert data["warnings"] is None
        assert data["directions"] is None
