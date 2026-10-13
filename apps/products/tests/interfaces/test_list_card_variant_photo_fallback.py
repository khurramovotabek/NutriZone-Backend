"""
Real, closed bug: a product whose photos were only ever uploaded
against its own default variant (never a separate, family-level
"primary" image) rendered the generic fallback icon on every list/
search/best-sellers card -- even though its own Product Detail page
already showed a real photo, via the exact same "fall back to the
selected variant's own gallery" rule (see ProductPurchaseExperience.
tsx's own `familyGallery`). List/search cards carry no per-variant
gallery data at all, so `_product_card()` now resolves the same real
fallback server-side: the customer sees a real photo everywhere, not
just on Detail.

Also closes a second, adjacent real gap found while fixing this:
`DjangoProductSearchBackend.search()` never resolved
`default_variant_id` at all, silently breaking quick-add-to-cart on
every search result card (in addition to blocking this exact photo
fallback, which needs it).
"""
from __future__ import annotations

import uuid

import pytest
from django.test import Client

from apps.products.infrastructure import models as p_models

pytestmark = pytest.mark.django_db


def _product_with_variant_only_photo(slug: str):
    product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
    p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name="Variant Photo Only Product", slug=slug)
    variant = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"VP-{uuid.uuid4().hex[:8].upper()}", status="active", is_default=True)
    # Deliberately no family-level ProductMedia row (variant_id=None) --
    # only a variant-tagged photo, matching the real product that
    # exposed this bug.
    p_models.ProductMedia.objects.create(id=uuid.uuid4(), product=product, variant=variant, storage_path="image/variant-only.jpg", media_role="gallery", sort_order=0)
    p_models.ProductMedia.objects.create(id=uuid.uuid4(), product=product, variant=variant, storage_path="image/variant-only-primary.jpg", media_role="primary", sort_order=1)
    return product, variant


class TestListCardFallsBackToDefaultVariantPhoto:
    def test_catalog_list_shows_the_variant_photo_not_the_generic_fallback(self):
        product, _variant = _product_with_variant_only_photo(f"list-{uuid.uuid4().hex[:8]}")

        client = Client()
        response = client.get("/api/v1/products")
        assert response.status_code == 200
        card = next(c for c in response.json()["data"] if c["id"] == str(product.id))

        # The variant-tagged "primary" photo wins over the plain "gallery" one, same precedence as the family-level rule.
        assert card["primary_image_path"] is not None
        assert card["primary_image_path"].endswith("variant-only-primary.jpg")

    def test_search_results_also_get_the_photo_and_a_real_default_variant_id(self):
        product, variant = _product_with_variant_only_photo(f"search-{uuid.uuid4().hex[:8]}")

        client = Client()
        response = client.get("/api/v1/products/search", {"q": "Variant Photo Only Product"})
        assert response.status_code == 200
        card = next(c for c in response.json()["data"] if c["id"] == str(product.id))

        assert card["primary_image_path"] is not None
        assert card["default_variant_id"] == str(variant.id)  # closes the adjacent quick-add-to-cart gap too

    def test_product_with_genuinely_no_photo_anywhere_still_returns_null_not_fabricated(self):
        product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name="No Photo Anywhere", slug=f"nophoto-{uuid.uuid4().hex[:8]}")
        p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"NP-{uuid.uuid4().hex[:8].upper()}", status="active", is_default=True)

        client = Client()
        response = client.get("/api/v1/products")
        card = next(c for c in response.json()["data"] if c["id"] == str(product.id))
        assert card["primary_image_path"] is None

    def test_family_level_primary_photo_still_wins_over_variant_photo(self):
        """The existing, real family-level primary photo must never be shadowed by this new fallback -- the fallback only ever applies when the family level genuinely has none."""
        product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name="Has Family Photo", slug=f"family-{uuid.uuid4().hex[:8]}")
        variant = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"FP-{uuid.uuid4().hex[:8].upper()}", status="active", is_default=True)
        p_models.ProductMedia.objects.create(id=uuid.uuid4(), product=product, variant=None, storage_path="image/family-primary.jpg", media_role="primary", sort_order=0)
        p_models.ProductMedia.objects.create(id=uuid.uuid4(), product=product, variant=variant, storage_path="image/variant-primary.jpg", media_role="primary", sort_order=0)

        client = Client()
        response = client.get("/api/v1/products")
        card = next(c for c in response.json()["data"] if c["id"] == str(product.id))
        assert card["primary_image_path"].endswith("family-primary.jpg")
