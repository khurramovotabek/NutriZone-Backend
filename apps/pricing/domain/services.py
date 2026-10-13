"""
Pricing domain services.

`PriceCalculationEngine` is the single, deterministic source of truth
for combining a base price with any number of discounts -- per this
phase's explicit "no duplicated pricing calculation" requirement,
every price computation in this module (admin preview, a future
Cart/Ordering line-item price, an API price-lookup) must route through
this one engine, never re-implement stacking/priority logic locally.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from apps.pricing.domain.entities import DiscountLine
from apps.pricing.domain.enums import DiscountSourceType, StackingMode
from apps.pricing.domain.exceptions import NegativeMargin
from apps.pricing.domain.value_objects import DiscountValue, MarginPercentage, Money, Percentage, TaxRate

# Deterministic tiebreak ordering when two discount sources otherwise
# tie on priority -- declaration order of DiscountSourceType itself.
_SOURCE_TYPE_ORDER = {member.value: index for index, member in enumerate(DiscountSourceType)}


@dataclass(frozen=True, slots=True)
class DiscountSource:
    """One candidate discount fed into `PriceCalculationEngine.calculate()` -- callers (Application Services) assemble this list from whatever PricingRule/Campaign/Coupon matches apply, plus any Loyalty/Wallet discount supplied as a plain parameter."""

    source_type: str  # DiscountSourceType.value
    source_id: uuid.UUID | None
    label: str
    discount: DiscountValue
    stacking_mode: str  # StackingMode.value
    priority: int = 100  # lower number = higher precedence


@dataclass(frozen=True, slots=True)
class PriceCalculationResult:
    base_price: Money
    final_price: Money
    applied_discounts: tuple[DiscountLine, ...]

    @property
    def total_discount_amount(self) -> Money:
        total = sum((line.amount_deducted.amount for line in self.applied_discounts), Decimal("0.00"))
        return Money(amount=total, currency=self.base_price.currency)


class PriceCalculationEngine:
    """
    Deterministic algorithm (documented here, not left implicit):

    1. Sort every candidate `DiscountSource` by `priority` ascending,
       tiebroken by `DiscountSourceType` declaration order, then by
       `source_id` (UUID) for full determinism even across otherwise
       identical entries.
    2. If any EXCLUSIVE-mode source is present: apply ONLY the single
       highest-precedence (post-sort) EXCLUSIVE source. All other
       candidates, of any stacking mode, are ignored entirely --
       "exclusive" means exclusive.
    3. Otherwise, if any BEST_OF-mode sources are present: compute
       each one's discount amount independently against the base
       price, and apply only the single LARGEST resulting discount
       (ties broken by the same sort order from step 1).
    4. Every STACKABLE-mode source is then applied cumulatively, in
       sorted order, each computed against the price remaining AFTER
       every prior stackable discount (sequential, not all against the
       original base price) -- this is a deliberate, documented
       business choice (sequential stacking is more conservative than
       summing percentages against the original base, and avoids ever
       producing a negative price without an explicit floor check at
       every step, since `DiscountValue.apply_to` already floors at
       zero).
    """

    @staticmethod
    def calculate(base_price: Money, sources: list[DiscountSource]) -> PriceCalculationResult:
        ordered = sorted(sources, key=lambda s: (s.priority, _SOURCE_TYPE_ORDER.get(s.source_type, 999), str(s.source_id or "")))

        exclusive = [s for s in ordered if s.stacking_mode == StackingMode.EXCLUSIVE.value]
        if exclusive:
            chosen = exclusive[0]
            line = PriceCalculationEngine._apply_one(base_price, chosen)
            final_price = chosen.discount.apply_to(base_price)
            return PriceCalculationResult(base_price=base_price, final_price=final_price, applied_discounts=(line,))

        applied_lines: list[DiscountLine] = []
        running_price = base_price

        best_of_candidates = [s for s in ordered if s.stacking_mode == StackingMode.BEST_OF.value]
        if best_of_candidates:
            best = max(best_of_candidates, key=lambda s: (base_price.amount - s.discount.apply_to(base_price).amount, -_SOURCE_TYPE_ORDER.get(s.source_type, 999)))
            line = PriceCalculationEngine._apply_one(running_price, best)
            running_price = best.discount.apply_to(running_price)
            applied_lines.append(line)

        for source in [s for s in ordered if s.stacking_mode == StackingMode.STACKABLE.value]:
            line = PriceCalculationEngine._apply_one(running_price, source)
            running_price = source.discount.apply_to(running_price)
            applied_lines.append(line)

        return PriceCalculationResult(base_price=base_price, final_price=running_price, applied_discounts=tuple(applied_lines))

    @staticmethod
    def _apply_one(price_before: Money, source: DiscountSource) -> DiscountLine:
        price_after = source.discount.apply_to(price_before)
        deducted = Money(amount=price_before.amount - price_after.amount, currency=price_before.currency)
        return DiscountLine(id=uuid.uuid4(), source_type=source.source_type, source_id=source.source_id, label=source.label, amount_deducted=deducted, stacking_mode=source.stacking_mode)


class MarginCalculator:
    """Margin/Profit Calculation -- pure functions over cost vs. sale price."""

    @staticmethod
    def margin_percentage(cost_price: Money, sale_price: Money) -> MarginPercentage:
        if sale_price.amount == 0:
            return MarginPercentage(value=Decimal("0.00"))
        margin = ((sale_price.amount - cost_price.amount) / sale_price.amount) * Decimal(100)
        return MarginPercentage(value=margin.quantize(Decimal("0.01")))

    @staticmethod
    def profit_amount(cost_price: Money, sale_price: Money) -> Money:
        return Money(amount=sale_price.amount - cost_price.amount, currency=sale_price.currency)

    @staticmethod
    def assert_non_negative_margin(cost_price: Money, sale_price: Money, allow_loss_leader: bool = False) -> None:
        if not allow_loss_leader and sale_price.amount < cost_price.amount:
            raise NegativeMargin(f"Sale price {sale_price.amount} is below cost price {cost_price.amount}. Pass allow_loss_leader=True to permit an intentional loss-leader price.")


class TaxCalculator:
    """Tax-ready Calculation -- applies a caller-supplied TaxRate; Pricing does not own jurisdiction/rate lookup logic (a future concern), only the arithmetic given a rate."""

    @staticmethod
    def apply(price: Money, tax_rate: TaxRate) -> Money:
        return tax_rate.apply_to(price)


class CashbackPolicy:
    """Cashback Calculation -- a pure function; see domain/events.py::CashbackCalculated for how the result reaches Wallet."""

    @staticmethod
    def calculate(price: Money, cashback_rate: Percentage) -> Money:
        return cashback_rate.apply_to(price)


class WalletDiscountPolicy:
    """Wallet Discount -- pure calculation given a caller-supplied wallet balance (never queried by Pricing itself, per this phase's Step 1 resolution)."""

    @staticmethod
    def apply(price: Money, wallet_balance: Money, max_redemption_percentage: Percentage) -> Money:
        max_redeemable = max_redemption_percentage.apply_to(price)
        redeemable = min(wallet_balance.amount, max_redeemable.amount)
        remaining = price.amount - redeemable
        floored = remaining if remaining > 0 else Decimal("0.00")
        return Money(amount=floored, currency=price.currency)


class LoyaltyDiscountPolicy:
    """Loyalty Discount / Membership Pricing -- pure calculation given a caller-supplied tier code and discount configuration (Pricing owns the discount VALUE per tier via a MEMBERSHIP-type PricingRule; it never looks up which tier a customer holds)."""

    @staticmethod
    def apply(price: Money, loyalty_tier_code: str | None, tier_discounts: dict[str, DiscountValue]) -> Money:
        if loyalty_tier_code is None or loyalty_tier_code not in tier_discounts:
            return price
        return tier_discounts[loyalty_tier_code].apply_to(price)


class PricePreviewPolicy:
    """Price Preview -- assembles a human-readable preview from a PriceCalculationResult without re-deriving anything, per the 'no duplicated calculation' rule."""

    @staticmethod
    def summarize(result: PriceCalculationResult) -> dict:
        return {
            "base_price": {"amount": str(result.base_price.amount), "currency": result.base_price.currency},
            "final_price": {"amount": str(result.final_price.amount), "currency": result.final_price.currency},
            "total_discount": {"amount": str(result.total_discount_amount.amount), "currency": result.base_price.currency},
            "applied_discounts": [
                {"source_type": line.source_type, "label": line.label, "amount_deducted": str(line.amount_deducted.amount)}
                for line in result.applied_discounts
            ],
        }
