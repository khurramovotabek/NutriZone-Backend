"""
Real, closed bug: `AdminCatalogSelector.list()` called
`_admin_product_card()`, a function never defined anywhere in
selectors.py -- any real call to `GET /admin/products`
(AdminProductListCreateView) crashed with `NameError`. Found via ruff
(F821 undefined name), confirmed by direct reproduction before fixing.
"""
from __future__ import annotations

import uuid

import pytest

from apps.products.infrastructure import models as p_models
from apps.products.infrastructure.selectors import AdminCatalogSelector

pytestmark = pytest.mark.django_db


class TestAdminCatalogSelector:
    def test_list_does_not_crash_and_returns_the_real_product(self):
        product = p_models.Product.objects.create(id=uuid.uuid4(), status="draft")
        slug = f"admin-list-{uuid.uuid4().hex[:8]}"
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name="Admin List Test", slug=slug)
        p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"AL-{uuid.uuid4().hex[:6].upper()}", status="active")

        cards, total = AdminCatalogSelector().list()

        card = next(c for c in cards if c["id"] == str(product.id))
        assert card["slug"] == slug
        assert card["name"] == "Admin List Test"
        assert card["status"] == "draft"
        assert card["variant_count"] == 1
        assert card["media_count"] == 0
        assert total >= 1

    def test_list_shows_every_status_not_just_published(self):
        """Unlike the public selector, staff must see draft/hidden/archived products too."""
        draft = p_models.Product.objects.create(id=uuid.uuid4(), status="draft")
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=draft, locale_code="en", name="Draft Product", slug=f"draft-{uuid.uuid4().hex[:8]}")

        cards, _total = AdminCatalogSelector().list(status="draft")
        assert any(c["id"] == str(draft.id) for c in cards)
