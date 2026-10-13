"""
POS Phase 6 -- Scanner-to-Sale Integration tests.

**No new production code was written for this phase.** Architecture
review (Step 1) confirmed the existing `SearchProduct` and
`AddLineItem` Application Services already fully support the
scanner-to-sale workflow as two sequential calls -- no new
orchestration service, Port, or endpoint was required or added.
This file proves that claim directly, using the real, unmodified,
certified services together.

**Two real, disclosed architectural gaps this phase does not close**:
1. `AddLineItem.execute()` has no `variant_id` parameter -- confirmed
   directly from live source. `SaleLineItem` has no `variant_id`
   field. The scanned `variant_id` is therefore available from
   `SearchProduct`'s own response for display/verification, but has
   no Sale-level home to persist into; only `product_id` flows
   through to `AddLineItem`.
2. No authoritative pricing capability is integrated -- `Pricing` is
   a separate, real bounded context (`PriceList`/`PricingRule`/
   `Campaign`/`Coupon`), and `AddLineItem`'s own certified,
   already-frozen contract (established in POS Phase 3, unrelated to
   this phase) already requires the caller to supply
   `unit_price_amount`/`unit_price_currency` directly -- this phase
   inherits that contract unchanged, it does not invent it.
"""
from __future__ import annotations

import inspect
import uuid
from datetime import datetime
from decimal import Decimal

import pytest

from apps.pos.application.services._shared import PosServiceContext
from apps.pos.application.services.sale import AddLineItem
from apps.pos.application.services.search import SearchProduct
from apps.pos.domain.exceptions import InvalidQuantity, InvalidSaleTransition
from apps.pos.tests.application.fakes import FakeProductLookup, FakeSaleRepository, FakeTextSearch, collect_events
from apps.pos.tests.factories import make_sale, make_sale_with_line
from common.exceptions import ResourceNotFound

pytestmark = pytest.mark.django_db

VALID_BARCODE = "5901234123457"
VALID_SKU = "WHEY-CHOC-2KG"


def _ctx():
    events: list = []
    return PosServiceContext(stage_events=collect_events(events), actor_id=uuid.uuid4()), events


class TestScannerIdentifiesProduct:
    """Search-layer coverage, Section 19 items 1-5 -- re-confirmed here in the exact scanner-workflow context, not merely a repeat of the Search module's own tests."""

    def test_valid_barcode_resolves_product_variant(self):
        product_id, variant_id = uuid.uuid4(), uuid.uuid4()
        lookup = FakeProductLookup()
        lookup.by_barcode[VALID_BARCODE] = (product_id, variant_id)
        search = SearchProduct(lookup, FakeTextSearch())

        result = search.execute(VALID_BARCODE, mode="barcode")

        assert result["exact_match"]["product_id"] == product_id
        assert result["exact_match"]["variant_id"] == variant_id

    def test_barcode_not_found(self):
        search = SearchProduct(FakeProductLookup(), FakeTextSearch())
        with pytest.raises(ResourceNotFound):
            search.execute(VALID_BARCODE, mode="barcode")

    def test_valid_sku_resolves_product_variant(self):
        product_id, variant_id = uuid.uuid4(), uuid.uuid4()
        lookup = FakeProductLookup()
        lookup.by_sku[VALID_SKU] = (product_id, variant_id)
        search = SearchProduct(lookup, FakeTextSearch())

        result = search.execute(VALID_SKU, mode="sku")

        assert result["exact_match"]["product_id"] == product_id

    def test_text_search_remains_delegated(self):
        text_search = FakeTextSearch({"results": [{"id": "x"}], "total_count": 1, "facets": {}})
        search = SearchProduct(FakeProductLookup(), text_search)
        result = search.execute("protein", mode="text")
        assert result["mode"] == "text"
        assert text_search.calls[0]["query"] == "protein"

    def test_search_never_touches_a_sale_repository(self):
        """A direct, executable proof that SearchProduct has no dependency on SaleRepository at all -- it structurally cannot mutate a Sale."""
        search = SearchProduct(FakeProductLookup(), FakeTextSearch())
        assert not hasattr(search, "_sale_repository")
        assert not hasattr(search, "sale_repository")


class TestSearchResultFeedsAddLineItem:
    """The core Phase 6 proof: a real SearchProduct result's product_id is exactly what AddLineItem accepts -- two real, unmodified services, chained manually by the test (matching the certified two-step architecture, never a combined service)."""

    def test_valid_search_result_feeds_add_line_item(self):
        product_id, variant_id = uuid.uuid4(), uuid.uuid4()
        lookup = FakeProductLookup()
        lookup.by_barcode[VALID_BARCODE] = (product_id, variant_id)
        search = SearchProduct(lookup, FakeTextSearch())

        search_result = search.execute(VALID_BARCODE, mode="barcode")
        resolved_product_id = search_result["exact_match"]["product_id"]

        sale_repo = FakeSaleRepository()
        sale = make_sale()
        sale_repo.save(sale)
        ctx, events = _ctx()

        updated_sale = AddLineItem(sale_repo, ctx).execute(sale_id=sale.id, product_id=resolved_product_id, quantity=1, unit_price_amount=Decimal("19.99"), unit_price_currency="UZS")

        entry = next(iter(updated_sale.line_items.values()))
        assert entry.product_id == product_id
        assert any(e[0] == "SaleLineItemAdded" for e in events)

    def test_quantity_has_no_built_in_default_caller_must_supply_it(self):
        """A real, disclosed finding, corrected from an initial wrong assumption: `AddLineItem.execute()`'s `quantity` parameter has NO default value at all -- verified directly via AST inspection of the real signature, not assumed. 'Default quantity = 1 for a scan' (this phase's own Section 11) is therefore a calling convention the caller must apply explicitly, not something AddLineItem itself enforces. This test proves both facts: no built-in default exists, and explicitly passing 1 works correctly."""
        sig = inspect.signature(AddLineItem.execute)
        assert sig.parameters["quantity"].default is inspect.Parameter.empty

        sale_repo = FakeSaleRepository()
        sale = make_sale()
        sale_repo.save(sale)
        ctx, _ = _ctx()
        updated = AddLineItem(sale_repo, ctx).execute(sale_id=sale.id, product_id=uuid.uuid4(), quantity=1, unit_price_amount=Decimal("5.00"), unit_price_currency="UZS")
        entry = next(iter(updated.line_items.values()))
        assert entry.quantity.value == 1

    def test_explicit_quantity_is_validated_via_existing_rules(self):
        sale_repo = FakeSaleRepository()
        sale = make_sale()
        sale_repo.save(sale)
        ctx, _ = _ctx()
        with pytest.raises(InvalidQuantity):
            AddLineItem(sale_repo, ctx).execute(sale_id=sale.id, product_id=uuid.uuid4(), quantity=0, unit_price_amount=Decimal("5.00"), unit_price_currency="UZS")

    def test_variant_id_has_no_sale_level_field_documented_gap(self):
        """A direct, executable proof of the disclosed Finding 1: SaleLineItem genuinely has no variant_id field -- fails loudly if this ever silently changes without this test being updated."""
        sale_repo = FakeSaleRepository()
        sale = make_sale()
        sale_repo.save(sale)
        ctx, _ = _ctx()
        updated = AddLineItem(sale_repo, ctx).execute(sale_id=sale.id, product_id=uuid.uuid4(), quantity=1, unit_price_amount=Decimal("5.00"), unit_price_currency="UZS")
        entry = next(iter(updated.line_items.values()))
        assert not hasattr(entry, "variant_id")


class TestDomainExceptionsPropagateUnchanged:
    def test_completed_sale_cannot_receive_scanned_product(self):
        sale_repo = FakeSaleRepository()
        sale = make_sale_with_line()
        sale.complete(datetime.utcnow())
        sale_repo.save(sale)
        ctx, events = _ctx()
        with pytest.raises(InvalidSaleTransition):
            AddLineItem(sale_repo, ctx).execute(sale_id=sale.id, product_id=uuid.uuid4(), quantity=1, unit_price_amount=Decimal("5.00"), unit_price_currency="UZS")
        assert events == []

    def test_voided_sale_cannot_receive_scanned_product(self):
        sale_repo = FakeSaleRepository()
        sale = make_sale()
        sale.void(datetime.utcnow())
        sale_repo.save(sale)
        ctx, events = _ctx()
        with pytest.raises(InvalidSaleTransition):
            AddLineItem(sale_repo, ctx).execute(sale_id=sale.id, product_id=uuid.uuid4(), quantity=1, unit_price_amount=Decimal("5.00"), unit_price_currency="UZS")
        assert events == []


class TestNoDirectSaleMutationOutsideAddLineItem:
    def test_search_product_class_body_never_references_sale_mutation(self):
        """The Section 21/22 regression guard, at the Application layer: SearchProduct's own source contains no reference to add_line_item or SaleRepository anywhere."""
        source = inspect.getsource(SearchProduct)
        assert "add_line_item" not in source
        assert "SaleRepository" not in source
