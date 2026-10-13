"""
Tests for the POS Search module's Infrastructure wiring:
`ProductLookupAdapter` and the 2 new composition factories
(`build_product_lookup`, `build_search_product`).

**Deliberately does not add any test file to Products' own test
suite** -- this task's own Section 18 explicitly restricts touching
Products beyond the minimal, authorized capability itself; Products'
own test coverage for `get_by_sku()`/`get_by_barcode()` is that
module's own concern, not this task's. Coverage for the new
capability lives entirely within POS's own test suite, exercising
`ProductLookupAdapter`'s delegation against a real database.
"""
from __future__ import annotations

import inspect

import pytest

from apps.pos.infrastructure import composition
from apps.pos.infrastructure.composition import ProductLookupAdapter
from apps.products.infrastructure import models as products_orm

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestProductLookupAdapter:
    def test_find_by_barcode_delegates_to_products_repository(self):
        """A real database round-trip: creates a real Products ProductVariant with a barcode, then confirms the adapter resolves it -- proving the wiring, not merely that a fake returns what it's told to."""
        product = products_orm.Product.objects.create(status="published")
        variant = products_orm.ProductVariant.objects.create(product=product, sku="ADAPTER-TEST-SKU", barcode="5901234123457")

        adapter = ProductLookupAdapter()
        result = adapter.find_by_barcode("5901234123457")

        assert result == (product.id, variant.id)

    def test_find_by_barcode_missing_returns_none(self):
        adapter = ProductLookupAdapter()
        assert adapter.find_by_barcode("99999999") is None

    def test_find_by_sku_delegates_to_products_repository(self):
        product = products_orm.Product.objects.create(status="published")
        variant = products_orm.ProductVariant.objects.create(product=product, sku="ADAPTER-TEST-SKU-2")

        adapter = ProductLookupAdapter()
        result = adapter.find_by_sku("ADAPTER-TEST-SKU-2")

        assert result == (product.id, variant.id)

    def test_find_by_sku_missing_returns_none(self):
        adapter = ProductLookupAdapter()
        assert adapter.find_by_sku("DOES-NOT-EXIST") is None


class TestSearchComposition:
    def test_build_product_lookup_returns_a_real_adapter(self):
        lookup = composition.build_product_lookup()
        assert lookup is not None

    def test_build_search_product_is_callable(self):
        service = composition.build_search_product()
        assert service is not None

    def test_search_factories_present_and_callable(self):
        """Phase 05 final closure: replaced the previous fragile exact-count assertion (assert len(factories) == 10) with a robust, name-based contract, matching test_all_8_original_factories_still_present's own established pattern in this same file. The exact count was confirmed stale by direct reconnaissance -- 15 factories now genuinely exist, all legitimate (each traced to either a direct HTTP view caller or a genuine internal caller within composition.py itself)."""
        for name in ("build_product_lookup", "build_search_product"):
            assert hasattr(composition, name), f"{name} is missing -- POS Search composition regression"
            factory = getattr(composition, name)
            assert factory() is not None

    def test_all_8_original_factories_still_present(self):
        for name in ("build_sale_repository", "build_pos_service_context", "build_open_sale", "build_load_sale", "build_add_line_item", "build_remove_line_item", "build_complete_sale", "build_void_sale"):
            assert hasattr(composition, name), f"{name} is missing -- POS Phase 3/4 composition regression"
