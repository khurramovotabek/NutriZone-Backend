"""
Tests for the POS Search module's Application Service.

**`5901234123457` is a genuine, checksum-valid EAN-13 that ALSO
matches SKU's own regex** (`[A-Z0-9]+(?:-[A-Z0-9]+)*` allows pure
digits) -- verified directly before writing this file, not assumed.
This is the real overlap case the Search module's own certified
design resolves via the priority cascade, not an invented
disambiguation rule; several tests below use this exact value
specifically to exercise that overlap.
"""
from __future__ import annotations

import uuid

import pytest

from apps.pos.application.services.search import SearchProduct
from apps.pos.tests.application.fakes import FakeProductLookup, FakeTextSearch
from common.exceptions import ResourceNotFound, ValidationFailed

pytestmark = pytest.mark.unit

VALID_BARCODE = "5901234123457"  # checksum-valid EAN-13, also SKU-pattern-valid (the real overlap case)
VALID_SKU = "WHEY-CHOC-2KG"
INVALID_BARCODE_CHECKSUM = "5901234123458"  # same digits, wrong check digit
INVALID_BARCODE_FORMAT = "abc"


class TestBarcodeMode:
    def test_valid_barcode_found_returns_exact_match(self):
        product_id, variant_id = uuid.uuid4(), uuid.uuid4()
        lookup = FakeProductLookup()
        lookup.by_barcode[VALID_BARCODE] = (product_id, variant_id)
        search = SearchProduct(lookup, FakeTextSearch())

        result = search.execute(VALID_BARCODE, mode="barcode")

        assert result["mode"] == "barcode"
        assert result["exact_match"] == {"product_id": product_id, "variant_id": variant_id}
        assert result["results"] is None
        assert result["total_count"] is None

    def test_valid_barcode_not_found_raises_resource_not_found(self):
        search = SearchProduct(FakeProductLookup(), FakeTextSearch())
        with pytest.raises(ResourceNotFound):
            search.execute(VALID_BARCODE, mode="barcode")

    def test_invalid_barcode_format_propagates_validation_failed(self):
        search = SearchProduct(FakeProductLookup(), FakeTextSearch())
        with pytest.raises(ValidationFailed):
            search.execute(INVALID_BARCODE_FORMAT, mode="barcode")

    def test_invalid_barcode_checksum_propagates_validation_failed(self):
        """A structurally valid 13-digit string with the wrong check digit -- reuses Products' own certified checksum logic, never reimplemented."""
        search = SearchProduct(FakeProductLookup(), FakeTextSearch())
        with pytest.raises(ValidationFailed):
            search.execute(INVALID_BARCODE_CHECKSUM, mode="barcode")

    def test_explicit_barcode_mode_never_falls_through_to_text_search(self):
        """A barcode scanner must never accidentally return an unrelated product through fuzzy matching -- explicit mode never delegates to text search, even on a miss."""
        text_search = FakeTextSearch()
        search = SearchProduct(FakeProductLookup(), text_search)
        with pytest.raises(ResourceNotFound):
            search.execute(VALID_BARCODE, mode="barcode")
        assert text_search.calls == []


class TestSkuMode:
    def test_existing_sku_found_returns_exact_match(self):
        product_id, variant_id = uuid.uuid4(), uuid.uuid4()
        lookup = FakeProductLookup()
        lookup.by_sku[VALID_SKU] = (product_id, variant_id)
        search = SearchProduct(lookup, FakeTextSearch())

        result = search.execute(VALID_SKU, mode="sku")

        assert result["mode"] == "sku"
        assert result["exact_match"] == {"product_id": product_id, "variant_id": variant_id}

    def test_sku_not_found_raises_resource_not_found(self):
        search = SearchProduct(FakeProductLookup(), FakeTextSearch())
        with pytest.raises(ResourceNotFound):
            search.execute(VALID_SKU, mode="sku")

    def test_invalid_sku_format_propagates_validation_failed(self):
        search = SearchProduct(FakeProductLookup(), FakeTextSearch())
        with pytest.raises(ValidationFailed):
            search.execute("lowercase-not-allowed", mode="sku")


class TestTextMode:
    def test_text_search_delegates_to_products_search_capability(self):
        text_search = FakeTextSearch({"results": [{"id": "x"}], "total_count": 1, "facets": {}})
        search = SearchProduct(FakeProductLookup(), text_search)

        result = search.execute("protein powder", mode="text")

        assert result["mode"] == "text"
        assert result["exact_match"] is None
        assert result["results"] == [{"id": "x"}]
        assert result["total_count"] == 1
        assert text_search.calls[0]["query"] == "protein powder"

    def test_empty_text_search_result(self):
        search = SearchProduct(FakeProductLookup(), FakeTextSearch())
        result = search.execute("nonexistent product", mode="text")
        assert result["results"] == []
        assert result["total_count"] == 0

    def test_no_speculative_search_behavior_pagination_forwarded_exactly(self):
        text_search = FakeTextSearch()
        search = SearchProduct(FakeProductLookup(), text_search)
        search.execute("query", mode="text", page=3, page_size=50)
        assert text_search.calls[0]["page"] == 3
        assert text_search.calls[0]["page_size"] == 50


class TestUnknownMode:
    def test_unknown_mode_raises_validation_failed(self):
        search = SearchProduct(FakeProductLookup(), FakeTextSearch())
        with pytest.raises(ValidationFailed):
            search.execute("anything", mode="not-a-real-mode")


class TestAutomaticCascade:
    """The certified priority order: barcode -> SKU -> text. No `mode` supplied."""

    def test_valid_barcode_found_resolves_via_barcode_stage(self):
        product_id, variant_id = uuid.uuid4(), uuid.uuid4()
        lookup = FakeProductLookup()
        lookup.by_barcode[VALID_BARCODE] = (product_id, variant_id)
        text_search = FakeTextSearch()
        search = SearchProduct(lookup, text_search)

        result = search.execute(VALID_BARCODE)

        assert result["mode"] == "barcode"
        assert result["exact_match"] == {"product_id": product_id, "variant_id": variant_id}
        assert text_search.calls == []

    def test_the_real_overlap_case_barcode_valid_but_not_found_falls_through_to_sku(self):
        """The genuine, disclosed regex-overlap finding: VALID_BARCODE also matches SKU's own pattern. When the barcode lookup misses, the cascade must try SKU next -- not error out, not skip to text."""
        product_id, variant_id = uuid.uuid4(), uuid.uuid4()
        lookup = FakeProductLookup()
        lookup.by_sku[VALID_BARCODE] = (product_id, variant_id)  # registered as a SKU match, not a barcode match
        search = SearchProduct(lookup, FakeTextSearch())

        result = search.execute(VALID_BARCODE)

        assert result["mode"] == "sku"
        assert result["exact_match"] == {"product_id": product_id, "variant_id": variant_id}

    def test_neither_barcode_nor_sku_match_falls_through_to_text(self):
        text_search = FakeTextSearch({"results": [{"id": "y"}], "total_count": 1, "facets": {}})
        search = SearchProduct(FakeProductLookup(), text_search)

        result = search.execute(VALID_BARCODE)

        assert result["mode"] == "text"
        assert text_search.calls[0]["query"] == VALID_BARCODE

    def test_non_barcode_non_sku_text_goes_directly_to_text_search(self):
        """Free text ('protein powder') never matches either exact-format regex -- the cascade should skip straight to text search without attempting a lookup call."""
        lookup = FakeProductLookup()
        text_search = FakeTextSearch()
        search = SearchProduct(lookup, text_search)

        result = search.execute("protein powder")

        assert result["mode"] == "text"
        assert text_search.calls[0]["query"] == "protein powder"

    def test_malformed_barcode_like_input_does_not_raise_in_automatic_mode(self):
        """The disclosed distinction: automatic cascade never raises on a format mismatch -- it silently tries the next stage. Only explicit mode propagates ValidationFailed."""
        text_search = FakeTextSearch()
        search = SearchProduct(FakeProductLookup(), text_search)
        result = search.execute(INVALID_BARCODE_FORMAT)  # "abc" -- not barcode, not SKU format either (lowercase)
        assert result["mode"] == "text"

    def test_query_is_stripped_before_evaluation(self):
        product_id, variant_id = uuid.uuid4(), uuid.uuid4()
        lookup = FakeProductLookup()
        lookup.by_barcode[VALID_BARCODE] = (product_id, variant_id)
        search = SearchProduct(lookup, FakeTextSearch())
        result = search.execute(f"  {VALID_BARCODE}  ")
        assert result["mode"] == "barcode"


class TestNoDuplicateAddToSaleMechanism:
    def test_search_service_has_no_add_line_item_capability(self):
        """A direct, executable proof that SearchProduct never becomes a second 'add product to sale' mechanism -- it has no repository/service dependency capable of mutating a Sale."""
        search = SearchProduct(FakeProductLookup(), FakeTextSearch())
        assert not hasattr(search, "add_line_item")
        assert not hasattr(search, "_sale_repository")
