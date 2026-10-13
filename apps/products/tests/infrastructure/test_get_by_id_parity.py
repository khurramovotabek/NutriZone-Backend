"""
Real, closed gap: `ProductDetailSelector.get_by_id` used to never pass
`include_variants`/`include_details` to `_product_card`, unlike its own
sibling `get_by_slug` (used by the real website) which always does --
confirmed as the actual root cause of `apps.telegram_bot`'s product
detail screen always rendering "no purchasable variant" regardless of
real stock, since `TelegramCatalogService.get_product` is `get_by_id`'s
only real caller. Fixed to match `get_by_slug` exactly; this test
guards that parity directly.
"""
from __future__ import annotations

import uuid

import pytest

from apps.products.infrastructure import models as p_models
from apps.products.infrastructure.selectors import ProductDetailSelector

pytestmark = pytest.mark.django_db


class TestGetByIdParityWithGetBySlug:
    def test_get_by_id_includes_variants_and_details_like_get_by_slug(self):
        product = p_models.Product.objects.create(id=uuid.uuid4(), status="published", specifications=[{"key": "Protein", "value": "25 g"}])
        p_models.ProductTranslation.objects.create(
            id=uuid.uuid4(), product=product, locale_code="en", name="ISO100 Hydrolyzed",
            slug=f"iso100-{uuid.uuid4().hex[:6]}", description="Premium hydrolyzed whey protein.",
        )
        p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:6]}", status="active", is_default=True)

        by_id = ProductDetailSelector().get_by_id(product.id, locale="en")
        by_slug = ProductDetailSelector().get_by_slug(product.translations.first().slug, locale="en")

        assert by_id is not None
        assert len(by_id["variants"]) == 1
        assert by_id["variants"][0]["status"] == "active"
        assert by_id["description"] == "Premium hydrolyzed whey protein."
        assert by_id["specifications"] == [{"key": "Protein", "value": "25 g"}]
        # Same shape either way in -- the only difference between the two lookups is id vs slug.
        assert set(by_id.keys()) == set(by_slug.keys())

    def test_get_by_id_returns_none_for_unpublished_product(self):
        product = p_models.Product.objects.create(id=uuid.uuid4(), status="draft")
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name="Draft Product", slug=f"draft-{uuid.uuid4().hex[:6]}")

        assert ProductDetailSelector().get_by_id(product.id) is None
