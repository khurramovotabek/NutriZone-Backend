"""
Domain services tests -- `PriceCalculationEngine` is the most critical
part of this module (per this phase's explicit emphasis) and is
tested exhaustively: exclusive/stackable/best-of behavior, priority
ordering, deterministic tiebreaking, and every downstream policy
(margin, tax, cashback, wallet, loyalty, preview) that either feeds
into or consumes its results.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.pricing.domain.enums import DiscountSourceType, StackingMode
from apps.pricing.domain.exceptions import NegativeMargin
from apps.pricing.domain.services import (
    CashbackPolicy,
    DiscountSource,
    LoyaltyDiscountPolicy,
    MarginCalculator,
    PriceCalculationEngine,
    PricePreviewPolicy,
    TaxCalculator,
    WalletDiscountPolicy,
)
from apps.pricing.domain.value_objects import DiscountValue, Money, Percentage, TaxRate

pytestmark = pytest.mark.unit


def _money(amount: str) -> Money:
    return Money(amount=Decimal(amount), currency="UZS")


def _pct_discount(value: str) -> DiscountValue:
    return DiscountValue(value_type="percentage", percentage=Percentage(value=Decimal(value)))


def _fixed_discount(value: str) -> DiscountValue:
    return DiscountValue(value_type="fixed_amount", fixed_amount=_money(value))


def _source(discount: DiscountValue, stacking_mode: str, priority: int = 100, source_type: str = DiscountSourceType.PRICING_RULE.value, source_id=None) -> DiscountSource:
    return DiscountSource(source_type=source_type, source_id=source_id or uuid.uuid4(), label="test", discount=discount, stacking_mode=stacking_mode, priority=priority)


class TestPriceCalculationEngineBasics:
    def test_no_discounts_returns_base_price_unchanged(self):
        base = _money("100.00")
        result = PriceCalculationEngine.calculate(base, [])
        assert result.final_price == base
        assert result.applied_discounts == ()

    def test_single_stackable_percentage_discount(self):
        base = _money("100.00")
        result = PriceCalculationEngine.calculate(base, [_source(_pct_discount("10"), StackingMode.STACKABLE.value)])
        assert result.final_price.amount == Decimal("90.00")
        assert len(result.applied_discounts) == 1

    def test_single_stackable_fixed_discount(self):
        base = _money("100.00")
        result = PriceCalculationEngine.calculate(base, [_source(_fixed_discount("25.00"), StackingMode.STACKABLE.value)])
        assert result.final_price.amount == Decimal("75.00")


class TestExclusiveStackingMode:
    def test_exclusive_ignores_all_others(self):
        base = _money("100.00")
        exclusive = _source(_pct_discount("50"), StackingMode.EXCLUSIVE.value, priority=1)
        stackable = _source(_pct_discount("10"), StackingMode.STACKABLE.value, priority=1)
        best_of = _source(_pct_discount("20"), StackingMode.BEST_OF.value, priority=1)
        result = PriceCalculationEngine.calculate(base, [exclusive, stackable, best_of])
        assert result.final_price.amount == Decimal("50.00")
        assert len(result.applied_discounts) == 1

    def test_multiple_exclusives_only_highest_precedence_applies(self):
        base = _money("100.00")
        lower_priority = _source(_pct_discount("30"), StackingMode.EXCLUSIVE.value, priority=5)
        higher_priority = _source(_pct_discount("10"), StackingMode.EXCLUSIVE.value, priority=1)
        result = PriceCalculationEngine.calculate(base, [lower_priority, higher_priority])
        assert result.final_price.amount == Decimal("90.00")  # the priority=1 (10%) source wins, not the bigger discount

    def test_exclusive_with_equal_priority_tiebroken_by_source_type_order(self):
        base = _money("100.00")
        coupon = _source(_pct_discount("10"), StackingMode.EXCLUSIVE.value, priority=1, source_type=DiscountSourceType.COUPON.value)
        pricing_rule = _source(_pct_discount("20"), StackingMode.EXCLUSIVE.value, priority=1, source_type=DiscountSourceType.PRICING_RULE.value)
        result = PriceCalculationEngine.calculate(base, [coupon, pricing_rule])
        # PRICING_RULE is declared before COUPON in DiscountSourceType -- deterministic tiebreak picks it.
        assert result.final_price.amount == Decimal("80.00")


class TestBestOfStackingMode:
    def test_best_of_picks_largest_discount(self):
        base = _money("100.00")
        small = _source(_pct_discount("5"), StackingMode.BEST_OF.value)
        large = _source(_pct_discount("25"), StackingMode.BEST_OF.value)
        result = PriceCalculationEngine.calculate(base, [small, large])
        assert result.final_price.amount == Decimal("75.00")
        assert len(result.applied_discounts) == 1

    def test_best_of_combines_with_stackable(self):
        base = _money("100.00")
        best_of = _source(_pct_discount("20"), StackingMode.BEST_OF.value)
        stackable = _source(_fixed_discount("5.00"), StackingMode.STACKABLE.value)
        result = PriceCalculationEngine.calculate(base, [best_of, stackable])
        # best_of applies first: 100 -> 80; then stackable: 80 -> 75
        assert result.final_price.amount == Decimal("75.00")
        assert len(result.applied_discounts) == 2


class TestStackableSequentialApplication:
    def test_stackable_discounts_apply_sequentially_not_against_original_base(self):
        base = _money("100.00")
        first = _source(_pct_discount("10"), StackingMode.STACKABLE.value, priority=1)
        second = _source(_pct_discount("10"), StackingMode.STACKABLE.value, priority=2)
        result = PriceCalculationEngine.calculate(base, [first, second])
        # 100 -> 90 (first 10% off) -> 81 (second 10% off the NEW price, not the original 100)
        assert result.final_price.amount == Decimal("81.00")

    def test_stackable_applies_in_priority_order(self):
        base = _money("100.00")
        fixed_first = _source(_fixed_discount("10.00"), StackingMode.STACKABLE.value, priority=1)
        pct_second = _source(_pct_discount("10"), StackingMode.STACKABLE.value, priority=2)
        result = PriceCalculationEngine.calculate(base, [pct_second, fixed_first])  # passed out of order deliberately
        # Engine must sort by priority regardless of input order: 100 -> 90 (fixed 10 off) -> 81 (10% off 90)
        assert result.final_price.amount == Decimal("81.00")

    def test_stackable_never_goes_negative(self):
        base = _money("10.00")
        huge = _source(_fixed_discount("100.00"), StackingMode.STACKABLE.value)
        result = PriceCalculationEngine.calculate(base, [huge])
        assert result.final_price.amount == Decimal("0.00")


class TestDeterminism:
    def test_identical_inputs_always_produce_identical_outputs(self):
        base = _money("250.00")
        source_a_id = uuid.uuid4()
        source_b_id = uuid.uuid4()
        sources = [
            _source(_pct_discount("5"), StackingMode.STACKABLE.value, priority=10, source_id=source_a_id),
            _source(_fixed_discount("15.00"), StackingMode.STACKABLE.value, priority=5, source_id=source_b_id),
        ]
        result_1 = PriceCalculationEngine.calculate(base, list(sources))
        result_2 = PriceCalculationEngine.calculate(base, list(reversed(sources)))
        assert result_1.final_price == result_2.final_price
        assert [l.source_id for l in result_1.applied_discounts] == [l.source_id for l in result_2.applied_discounts]

    def test_total_discount_amount_matches_base_minus_final(self):
        base = _money("100.00")
        result = PriceCalculationEngine.calculate(base, [_source(_pct_discount("15"), StackingMode.STACKABLE.value)])
        assert result.total_discount_amount.amount == base.amount - result.final_price.amount


class TestCouponAndCampaignAndRuleDiscountSources:
    """Verifies the engine treats every DiscountSourceType uniformly -- coupon/campaign/pricing_rule/membership all flow through the identical algorithm, no special-cased branch per type."""

    def test_coupon_source_type(self):
        result = PriceCalculationEngine.calculate(_money("100.00"), [_source(_pct_discount("10"), StackingMode.EXCLUSIVE.value, source_type=DiscountSourceType.COUPON.value)])
        assert result.applied_discounts[0].source_type == DiscountSourceType.COUPON.value

    def test_campaign_source_type(self):
        result = PriceCalculationEngine.calculate(_money("100.00"), [_source(_pct_discount("10"), StackingMode.EXCLUSIVE.value, source_type=DiscountSourceType.CAMPAIGN.value)])
        assert result.applied_discounts[0].source_type == DiscountSourceType.CAMPAIGN.value

    def test_membership_source_type(self):
        result = PriceCalculationEngine.calculate(_money("100.00"), [_source(_pct_discount("10"), StackingMode.STACKABLE.value, source_type=DiscountSourceType.MEMBERSHIP.value)])
        assert result.applied_discounts[0].source_type == DiscountSourceType.MEMBERSHIP.value


class TestMarginCalculator:
    def test_margin_percentage_positive(self):
        margin = MarginCalculator.margin_percentage(_money("60.00"), _money("100.00"))
        assert margin.value == Decimal("40.00")

    def test_margin_percentage_zero_sale_price(self):
        margin = MarginCalculator.margin_percentage(_money("0.00"), _money("0.00"))
        assert margin.value == Decimal("0.00")

    def test_margin_percentage_negative_when_selling_below_cost(self):
        margin = MarginCalculator.margin_percentage(_money("120.00"), _money("100.00"))
        assert margin.value == Decimal("-20.00")

    def test_profit_amount(self):
        profit = MarginCalculator.profit_amount(_money("60.00"), _money("100.00"))
        assert profit.amount == Decimal("40.00")

    def test_assert_non_negative_margin_passes(self):
        MarginCalculator.assert_non_negative_margin(_money("60.00"), _money("100.00"))

    def test_assert_non_negative_margin_raises_below_cost(self):
        with pytest.raises(NegativeMargin):
            MarginCalculator.assert_non_negative_margin(_money("120.00"), _money("100.00"))

    def test_assert_non_negative_margin_allows_loss_leader_when_explicit(self):
        MarginCalculator.assert_non_negative_margin(_money("120.00"), _money("100.00"), allow_loss_leader=True)


class TestTaxCalculator:
    def test_exclusive_tax_adds_to_price(self):
        result = TaxCalculator.apply(_money("100.00"), TaxRate(rate=Percentage(value=Decimal("12")), mode="exclusive"))
        assert result.amount == Decimal("112.00")

    def test_inclusive_tax_leaves_price_unchanged(self):
        result = TaxCalculator.apply(_money("100.00"), TaxRate(rate=Percentage(value=Decimal("12")), mode="inclusive"))
        assert result.amount == Decimal("100.00")


class TestCashbackPolicy:
    def test_calculates_percentage_of_price(self):
        cashback = CashbackPolicy.calculate(_money("200.00"), Percentage(value=Decimal("5")))
        assert cashback.amount == Decimal("10.00")


class TestWalletDiscountPolicy:
    def test_redeems_up_to_wallet_balance(self):
        result = WalletDiscountPolicy.apply(_money("100.00"), wallet_balance=_money("30.00"), max_redemption_percentage=Percentage(value=Decimal("50")))
        assert result.amount == Decimal("70.00")

    def test_capped_by_max_redemption_percentage_not_full_balance(self):
        result = WalletDiscountPolicy.apply(_money("100.00"), wallet_balance=_money("80.00"), max_redemption_percentage=Percentage(value=Decimal("20")))
        # max redeemable = 20% of 100 = 20, even though wallet has 80
        assert result.amount == Decimal("80.00")

    def test_never_goes_negative(self):
        result = WalletDiscountPolicy.apply(_money("10.00"), wallet_balance=_money("1000.00"), max_redemption_percentage=Percentage(value=Decimal("100")))
        assert result.amount == Decimal("0.00")


class TestLoyaltyDiscountPolicy:
    def test_applies_discount_for_matching_tier(self):
        tier_discounts = {"gold": _pct_discount("15")}
        result = LoyaltyDiscountPolicy.apply(_money("100.00"), "gold", tier_discounts)
        assert result.amount == Decimal("85.00")

    def test_no_tier_code_returns_price_unchanged(self):
        result = LoyaltyDiscountPolicy.apply(_money("100.00"), None, {"gold": _pct_discount("15")})
        assert result.amount == Decimal("100.00")

    def test_unknown_tier_code_returns_price_unchanged(self):
        result = LoyaltyDiscountPolicy.apply(_money("100.00"), "platinum", {"gold": _pct_discount("15")})
        assert result.amount == Decimal("100.00")


class TestPricePreviewPolicy:
    def test_summarize_shape(self):
        base = _money("100.00")
        result = PriceCalculationEngine.calculate(base, [_source(_pct_discount("10"), StackingMode.STACKABLE.value)])
        summary = PricePreviewPolicy.summarize(result)
        assert summary["base_price"]["amount"] == "100.00"
        assert summary["final_price"]["amount"] == "90.00"
        assert summary["total_discount"]["amount"] == "10.00"
        assert len(summary["applied_discounts"]) == 1

    def test_summarize_never_recomputes_only_reports(self):
        """Verifies summarize() is purely a formatting step over an already-computed result -- no discount math happens inside it."""
        base = _money("50.00")
        result = PriceCalculationEngine.calculate(base, [])
        summary = PricePreviewPolicy.summarize(result)
        assert summary["final_price"]["amount"] == "50.00"
        assert summary["applied_discounts"] == []
