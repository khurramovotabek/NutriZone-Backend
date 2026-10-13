"""
POS Phase 7 -- Authoritative Pricing Integration tests.

**These tests never re-verify Pricing's own discount algorithm** --
that is Pricing's own, already-certified concern (`PriceCalculationEngine`,
tested wherever it was originally certified). These tests prove only
that POS's new `ResolveLineItemPrice` correctly depends on an
abstraction (`PricingResolver`), correctly delegates to it, correctly
handles its results and exceptions, and never touches Sale mutation.
"""
from __future__ import annotations

import ast
import inspect
import uuid
from datetime import datetime
from decimal import Decimal

import pytest

from apps.pos.application.ports import PricingResolver
from apps.pos.application.services.pricing import ResolveLineItemPrice
from apps.pos.tests.application.fakes import FakePricingResolver
from common.exceptions import ResourceNotFound
from shared.value_objects.money import Money


class TestResolveLineItemPrice:
    def test_valid_product_variant_resolves_authoritative_price(self):
        price_list_id, variant_id = uuid.uuid4(), uuid.uuid4()
        expected = Money(Decimal("19.99"), "UZS")
        resolver = FakePricingResolver(result=expected)
        service = ResolveLineItemPrice(resolver)

        result = service.execute(price_list_id=price_list_id, variant_id=variant_id)

        assert result == expected
        assert resolver.calls[0]["price_list_id"] == price_list_id
        assert resolver.calls[0]["variant_id"] == variant_id

    def test_no_valid_price_propagates_resource_not_found_unchanged(self):
        """Mirrors Pricing's own certified `CalculatePrice` behavior exactly (raises `ResourceNotFound` -- confirmed directly from live source, the same shared exception type used throughout this build) -- POS never catches or remaps it."""
        resolver = FakePricingResolver(exception=ResourceNotFound("No price is configured for product variant."))
        service = ResolveLineItemPrice(resolver)
        with pytest.raises(ResourceNotFound):
            service.execute(price_list_id=uuid.uuid4(), variant_id=uuid.uuid4())

    def test_price_list_not_found_propagates_unchanged(self):
        resolver = FakePricingResolver(exception=ResourceNotFound("Price list not found."))
        service = ResolveLineItemPrice(resolver)
        with pytest.raises(ResourceNotFound):
            service.execute(price_list_id=uuid.uuid4(), variant_id=uuid.uuid4())

    def test_quantity_is_forwarded_to_the_resolver_unchanged(self):
        """Quantity-tier discounts are Pricing's own concern -- POS only proves it forwards the value it was given, never computes a discount itself."""
        resolver = FakePricingResolver(result=Money(Decimal("1.00")))
        service = ResolveLineItemPrice(resolver)
        service.execute(price_list_id=uuid.uuid4(), variant_id=uuid.uuid4(), quantity=5)
        assert resolver.calls[0]["quantity"] == 5

    def test_effective_date_is_forwarded_unchanged(self):
        """Effective-period/expiry resolution is Pricing's own concern -- POS proves only that a caller-supplied `at` reaches the Port unmodified."""
        at = datetime(2026, 1, 1)
        resolver = FakePricingResolver(result=Money(Decimal("1.00")))
        service = ResolveLineItemPrice(resolver)
        service.execute(price_list_id=uuid.uuid4(), variant_id=uuid.uuid4(), at=at)
        assert resolver.calls[0]["at"] == at

    def test_coupon_region_membership_are_forwarded_unchanged_never_evaluated_locally(self):
        """Campaign/coupon/regional/membership rule evaluation happens entirely inside Pricing -- POS forwards these optional parameters verbatim, never inspects or branches on them."""
        resolver = FakePricingResolver(result=Money(Decimal("1.00")))
        service = ResolveLineItemPrice(resolver)
        service.execute(price_list_id=uuid.uuid4(), variant_id=uuid.uuid4(), coupon_code="SUMMER10", region="tashkent", membership_tier_code="gold")
        call = resolver.calls[0]
        assert call["coupon_code"] == "SUMMER10"
        assert call["region"] == "tashkent"
        assert call["membership_tier_code"] == "gold"

    def test_currency_is_preserved_exactly_from_the_resolved_money(self):
        resolver = FakePricingResolver(result=Money(Decimal("42.50"), "USD"))
        service = ResolveLineItemPrice(resolver)
        result = service.execute(price_list_id=uuid.uuid4(), variant_id=uuid.uuid4())
        assert result.currency == "USD"

    def test_amount_precision_is_preserved_exactly(self):
        """
        `Money.__post_init__()` deliberately quantizes to 2 decimal
        places with ROUND_HALF_UP (confirmed directly against
        `common/utils/money.py`) -- this is applied the moment
        `Money(Decimal("19.995"))` is constructed below, before
        `service.execute()` ever runs, so the resolver's own result is
        already `Decimal("20.00")`. The real, still-meaningful intent
        of this test is that `ResolveLineItemPrice` introduces no
        *further* rounding beyond `Money`'s own deliberate one -- the
        expected value was corrected this phase to match that real
        contract; the test's original expectation (`19.995` surviving
        unrounded) contradicted `Money`'s own documented behavior and
        was never actually true.
        """
        resolver = FakePricingResolver(result=Money(Decimal("19.995")))
        service = ResolveLineItemPrice(resolver)
        result = service.execute(price_list_id=uuid.uuid4(), variant_id=uuid.uuid4())
        assert result.amount == Decimal("20.00")

    def test_resolve_line_item_price_has_no_sale_repository_dependency(self):
        """The Section 20/22 architectural proof: this service cannot mutate a Sale even if it wanted to -- it has no repository capable of it."""
        service = ResolveLineItemPrice(FakePricingResolver())
        assert not hasattr(service, "_sale_repository")
        assert not hasattr(service, "sale_repository")

    def test_no_add_line_item_reference_anywhere_in_this_service(self):
        source = inspect.getsource(ResolveLineItemPrice)
        assert "add_line_item" not in source
        assert "SaleRepository" not in source


class TestPricingBoundaryRegressionGuard:
    """Section 22, mandatory: proves POS does not directly own or reproduce Pricing rules -- protects against a future contributor silently duplicating campaign/coupon/discount logic inside POS.

    **A real false positive caught and fixed here**: an earlier version of this test scanned `inspect.getsource()` (including docstrings) for terms like "campaign"/"coupon"/"discount" -- but `pricing.py`'s own docstring legitimately *discusses* these terms while explaining they are NOT implemented locally, producing a guaranteed false failure. Fixed to inspect only the class's actual executable statements via AST (function bodies, not docstrings), which is what would genuinely indicate duplicated logic if it ever appeared."""

    def _has_any_conditional_logic(self, cls) -> bool:
        """A more accurate signal than substring matching (see this class's own docstring): any real discount-calculation duplication would necessarily involve branching (checking rule types, active periods, stacking priority, etc.). `ResolveLineItemPrice` is a single, direct pass-through call with zero conditionals -- if this ever finds an `if`/comparison, that is the real red flag, not the mere presence of a parameter named `coupon_code`."""
        tree = ast.parse(inspect.getsource(cls))
        return any(isinstance(node, (ast.If, ast.Compare, ast.IfExp)) for node in ast.walk(tree))

    def test_pos_pricing_service_has_no_discount_calculation_logic(self):
        """A real false positive was caught and fixed while writing this test: substring-matching against `ast.dump()` output also matches legitimate parameter names (`coupon_code` contains "coupon"), not just genuine logic. Fixed to check for the presence of any conditional/branching statement at all -- the real, accurate signal of duplicated calculation logic, since `ResolveLineItemPrice` is a pure, unconditional pass-through by design."""
        assert self._has_any_conditional_logic(ResolveLineItemPrice) is False, "ResolveLineItemPrice must remain a pure, unconditional pass-through to Pricing's own CalculatePrice -- any branching here would indicate duplicated discount-calculation logic."

    def test_pos_application_never_imports_pricing_domain_or_infrastructure_directly(self):
        """Only the composition root (Infrastructure) may reach Pricing's own composition root -- Application must depend on the PricingResolver Port only."""
        source = inspect.getsource(ResolveLineItemPrice)
        assert "apps.pricing" not in source
        assert "from apps.pricing" not in source

    def test_pricing_resolver_port_has_exactly_one_method(self):
        """A structural proof the Port stays narrow -- POS defines exactly what it needs, never re-exports Pricing's own richer contract."""
        methods = [name for name in dir(PricingResolver) if not name.startswith("_")]
        assert methods == ["calculate_price"]
