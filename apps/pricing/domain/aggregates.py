"""
Pricing aggregate roots: PriceList, PricingRule, Campaign, Coupon,
PriceSnapshot.

Five aggregates cover this phase's named capabilities as follows:
Base/Cost/Sale/Compare-at/Discount Price -> PriceList (+PriceListEntry);
Dynamic/Quantity/Time-based/Scheduled/Regional/Membership Pricing ->
PricingRule; Flash Sale/Campaign Pricing -> Campaign; Coupon/Promo
Pricing -> Coupon; Price Lock/Snapshot -> PriceSnapshot; Pricing
History -> PriceHistoryEntry (owned by PriceList); Loyalty/Wallet
Discount/Cashback -> parameters into PriceCalculationEngine
(domain/services.py), never aggregates of their own, per this phase's
Step 1 resolution (no Wallet/Loyalty dependency). Tax-ready/Margin/
Profit/Discount-Stacking/Promotion-Priority/Price-Preview are pure
calculations, also in domain/services.py -- not aggregate state.

Cross-module references (PriceListEntry.product_variant_id ->
products.ProductVariant) are IDs only, per the platform-wide
modular-monolith isolation rule.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from apps.pricing.domain.entities import CampaignTarget, CouponRedemption, PriceHistoryEntry, PriceListEntry
from apps.pricing.domain.enums import (
    CampaignStatus, CampaignType, CouponStatus, CouponType, PriceChangeReason,
    PriceListStatus, PriceSnapshotStatus, PriceType, PricingRuleStatus, PricingRuleType, StackingMode,
)
from apps.pricing.domain.events import (
    CampaignActivated, CampaignCancelled, CampaignCreated, CampaignEnded, CouponCreated,
    CouponRedeemed, CouponRevoked, PriceListActivated, PriceListArchivedEvent, PriceListCreated, PriceLocked,
    PriceSet, PriceSnapshotConsumed, PriceSnapshotReleased, PricingRuleActivated, PricingRuleArchived,
    PricingRuleCreated,
)
from apps.pricing.domain.exceptions import (
    CampaignNotActive, CouponExhausted, CouponExpired, CouponNotActive,
    InvalidCampaignLifecycleTransition, InvalidCouponLifecycleTransition, InvalidPriceListLifecycleTransition,
    InvalidPricingRuleLifecycleTransition, PriceListArchived, PriceSnapshotAlreadyConsumed, PriceSnapshotExpired,
)
from apps.pricing.domain.value_objects import (
    CouponCode, DiscountValue, Money, PriceListCode, PriceSnapshotToken, PriceValidityPeriod, QuantityTier,
    RegionCode,
)
from common.exceptions import ValidationFailed


@dataclass(slots=True)
class PriceList:
    """Aggregate root -- a named collection of Base/Cost/Sale/Compare-at prices, one per product variant, for a given channel/region/currency."""

    id: uuid.UUID
    code: PriceListCode
    name: str
    currency: str
    status: PriceListStatus = PriceListStatus.DRAFT
    region: RegionCode | None = None
    entries: dict[uuid.UUID, PriceListEntry] = field(default_factory=dict)  # keyed by entry id
    history: list[PriceHistoryEntry] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValidationFailed("Price list name must not be empty.")

    def _entry_for_variant(self, product_variant_id: uuid.UUID) -> PriceListEntry | None:
        return next((e for e in self.entries.values() if e.product_variant_id == product_variant_id), None)

    def entry_for_variant(self, product_variant_id: uuid.UUID) -> PriceListEntry | None:
        """Public read accessor -- `_entry_for_variant()` is used internally by `set_price()`; this is the same lookup exposed for Application Service read paths (e.g. CalculatePrice) so they never need to reach into a "private" method."""
        return self._entry_for_variant(product_variant_id)

    def set_price(self, product_variant_id: uuid.UUID, base_price: Money, reason: PriceChangeReason = PriceChangeReason.MANUAL, cost_price: Money | None = None, sale_price: Money | None = None, compare_at_price: Money | None = None, at: datetime | None = None) -> PriceSet:
        """Creates or updates the PriceListEntry for one variant -- every call appends a PriceHistoryEntry, backing 'Pricing History' unconditionally, not as an opt-in."""
        if self.status == PriceListStatus.ARCHIVED:
            raise PriceListArchived("This price list is archived and cannot be modified.")

        existing = self._entry_for_variant(product_variant_id)
        old_amount = existing.base_price if existing else None
        entry = PriceListEntry(id=existing.id if existing else uuid.uuid4(), product_variant_id=product_variant_id, base_price=base_price, cost_price=cost_price, sale_price=sale_price, compare_at_price=compare_at_price)
        self.entries[entry.id] = entry

        self.history.append(PriceHistoryEntry(
            id=uuid.uuid4(), product_variant_id=product_variant_id, price_type=PriceType.BASE.value,
            old_amount=old_amount, new_amount=base_price, reason=reason.value, changed_at=at or datetime.utcnow(),
        ))
        return PriceSet(price_list_id=self.id, product_variant_id=product_variant_id, price_type=PriceType.BASE.value, old_amount=str(old_amount.amount) if old_amount else None, new_amount=str(base_price.amount))

    def activate(self) -> PriceListActivated:
        if self.status == PriceListStatus.ARCHIVED:
            raise InvalidPriceListLifecycleTransition("An archived price list must be restored before activation.")
        self.status = PriceListStatus.ACTIVE
        return PriceListActivated(price_list_id=self.id)

    def archive(self) -> PriceListArchivedEvent:
        if self.status == PriceListStatus.ARCHIVED:
            raise InvalidPriceListLifecycleTransition("This price list is already archived.")
        self.status = PriceListStatus.ARCHIVED
        return PriceListArchivedEvent(price_list_id=self.id)


@dataclass(slots=True)
class PricingRule:
    """
    Aggregate root -- a single rule contributing a discount under
    specific conditions: Quantity Discount (via `quantity_tiers`),
    Time-based/Scheduled Pricing (via `validity`), Regional Pricing
    (via `region`), Dynamic Pricing (a rule with no static condition,
    intended for application-layer stock/demand-driven activation),
    or Membership Pricing (via `membership_tier_code` -- a plain
    string parameter, never a Loyalty module import, per this phase's
    Step 1 resolution).
    """

    id: uuid.UUID
    rule_type: PricingRuleType
    discount: DiscountValue
    status: PricingRuleStatus = PricingRuleStatus.DRAFT
    validity: PriceValidityPeriod | None = None
    region: RegionCode | None = None
    quantity_tiers: tuple[QuantityTier, ...] = ()
    membership_tier_code: str | None = None
    priority: int = 100  # lower runs first; see domain/services.py::PriceCalculationEngine

    def __post_init__(self) -> None:
        if self.rule_type == PricingRuleType.QUANTITY_DISCOUNT and not self.quantity_tiers:
            raise ValidationFailed("A QUANTITY_DISCOUNT rule requires at least one quantity tier.")
        if self.rule_type == PricingRuleType.TIME_BASED and self.validity is None:
            raise ValidationFailed("A TIME_BASED rule requires a validity period.")
        if self.rule_type == PricingRuleType.REGIONAL and self.region is None:
            raise ValidationFailed("A REGIONAL rule requires a region.")
        if self.rule_type == PricingRuleType.MEMBERSHIP and not self.membership_tier_code:
            raise ValidationFailed("A MEMBERSHIP rule requires a membership_tier_code.")

    def tier_for_quantity(self, quantity: int) -> QuantityTier | None:
        """Returns the highest-minimum tier the given quantity qualifies for -- pure lookup, no I/O."""
        qualifying = [t for t in self.quantity_tiers if quantity >= t.minimum_quantity]
        return max(qualifying, key=lambda t: t.minimum_quantity) if qualifying else None

    def is_active_at(self, at: datetime) -> bool:
        if self.status != PricingRuleStatus.ACTIVE:
            return False
        return self.validity is None or self.validity.is_active_at(at)

    def activate(self) -> PricingRuleActivated:
        if self.status == PricingRuleStatus.ARCHIVED:
            raise InvalidPricingRuleLifecycleTransition("An archived rule cannot be activated.")
        self.status = PricingRuleStatus.ACTIVE
        return PricingRuleActivated(pricing_rule_id=self.id)

    def archive(self) -> PricingRuleArchived:
        if self.status == PricingRuleStatus.ARCHIVED:
            raise InvalidPricingRuleLifecycleTransition("This rule is already archived.")
        self.status = PricingRuleStatus.ARCHIVED
        return PricingRuleArchived(pricing_rule_id=self.id)


@dataclass(slots=True)
class Campaign:
    """Aggregate root -- Flash Sale / Campaign Pricing: a time-bounded promotional discount applying to one or more targets."""

    id: uuid.UUID
    campaign_type: CampaignType
    name: str
    discount: DiscountValue
    validity: PriceValidityPeriod
    status: CampaignStatus = CampaignStatus.DRAFT
    stacking_mode: StackingMode = StackingMode.EXCLUSIVE
    targets: dict[uuid.UUID, CampaignTarget] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValidationFailed("Campaign name must not be empty.")

    def add_target(self, target: CampaignTarget) -> None:
        self.targets[target.id] = target

    def applies_to(self, target_type: str, target_id: uuid.UUID) -> bool:
        return any(t.target_type == target_type and t.target_id == target_id for t in self.targets.values())

    def is_active_at(self, at: datetime) -> bool:
        return self.status == CampaignStatus.ACTIVE and self.validity.is_active_at(at)

    def assert_active_at(self, at: datetime) -> None:
        if not self.is_active_at(at):
            raise CampaignNotActive(f"Campaign '{self.name}' is not active at {at.isoformat()}.")

    def activate(self) -> CampaignActivated:
        if self.status in (CampaignStatus.ENDED, CampaignStatus.CANCELLED):
            raise InvalidCampaignLifecycleTransition(f"Cannot activate a campaign that is already {self.status.value}.")
        self.status = CampaignStatus.ACTIVE
        return CampaignActivated(campaign_id=self.id)

    def end(self) -> CampaignEnded:
        if self.status not in (CampaignStatus.ACTIVE, CampaignStatus.SCHEDULED):
            raise InvalidCampaignLifecycleTransition("Only an active or scheduled campaign can be ended.")
        self.status = CampaignStatus.ENDED
        return CampaignEnded(campaign_id=self.id)

    def cancel(self) -> CampaignCancelled:
        if self.status == CampaignStatus.ENDED:
            raise InvalidCampaignLifecycleTransition("An ended campaign cannot be cancelled.")
        self.status = CampaignStatus.CANCELLED
        return CampaignCancelled(campaign_id=self.id)


@dataclass(slots=True)
class Coupon:
    """Aggregate root -- Coupon Pricing / Promo Pricing: a code-redeemed (COUPON) or auto-applied (PROMO) discount with usage limits."""

    id: uuid.UUID
    code: CouponCode
    coupon_type: CouponType
    discount: DiscountValue
    status: CouponStatus = CouponStatus.DRAFT
    validity: PriceValidityPeriod | None = None
    max_redemptions: int | None = None  # None means unlimited
    stacking_mode: StackingMode = StackingMode.EXCLUSIVE
    redemptions: dict[uuid.UUID, CouponRedemption] = field(default_factory=dict)

    @property
    def redemption_count(self) -> int:
        return len(self.redemptions)

    def assert_redeemable(self, at: datetime) -> None:
        if self.status == CouponStatus.EXHAUSTED or (
            self.max_redemptions is not None and self.redemption_count >= self.max_redemptions
        ):
            raise CouponExhausted(f"Coupon '{self.code.value}' has reached its redemption limit.")
        if self.status != CouponStatus.ACTIVE:
            raise CouponNotActive(f"Coupon '{self.code.value}' is not active.")
        if self.validity is not None and not self.validity.is_active_at(at):
            raise CouponExpired(f"Coupon '{self.code.value}' is expired.")

    def redeem(self, redeemed_by: uuid.UUID, order_reference: str, at: datetime) -> CouponRedeemed:
        self.assert_redeemable(at)
        redemption = CouponRedemption(id=uuid.uuid4(), redeemed_by=redeemed_by, order_reference=order_reference, redeemed_at=at)
        self.redemptions[redemption.id] = redemption
        if self.max_redemptions is not None and self.redemption_count >= self.max_redemptions:
            self.status = CouponStatus.EXHAUSTED
        return CouponRedeemed(coupon_id=self.id, redeemed_by=redeemed_by, order_reference=order_reference)

    def activate(self) -> None:
        if self.status == CouponStatus.REVOKED:
            raise InvalidCouponLifecycleTransition("A revoked coupon cannot be activated.")
        self.status = CouponStatus.ACTIVE

    def revoke(self) -> CouponRevoked:
        if self.status == CouponStatus.REVOKED:
            raise InvalidCouponLifecycleTransition("This coupon is already revoked.")
        self.status = CouponStatus.REVOKED
        return CouponRevoked(coupon_id=self.id)


@dataclass(slots=True)
class PriceSnapshot:
    """
    Aggregate root -- Price Lock / Price Snapshot: an immutable frozen
    price for one product variant, held for a bounded window so a
    downstream caller (e.g. a future Cart/Ordering module, referenced
    only by an opaque `token`) can guarantee the price won't change
    mid-transaction. `consume()` is one-way -- a consumed snapshot can
    never be released or re-consumed.
    """

    id: uuid.UUID
    token: PriceSnapshotToken
    product_variant_id: uuid.UUID
    locked_price: Money
    expires_at: datetime
    status: PriceSnapshotStatus = PriceSnapshotStatus.LOCKED

    def assert_valid_at(self, at: datetime) -> None:
        if self.status != PriceSnapshotStatus.LOCKED:
            raise PriceSnapshotAlreadyConsumed(f"This price snapshot is already {self.status.value}.")
        if at >= self.expires_at:
            raise PriceSnapshotExpired("This price snapshot has expired.")

    def consume(self, at: datetime) -> PriceSnapshotConsumed:
        self.assert_valid_at(at)
        self.status = PriceSnapshotStatus.CONSUMED
        return PriceSnapshotConsumed(snapshot_id=self.id)

    def release(self) -> PriceSnapshotReleased:
        if self.status != PriceSnapshotStatus.LOCKED:
            raise PriceSnapshotAlreadyConsumed(f"Cannot release a snapshot that is already {self.status.value}.")
        self.status = PriceSnapshotStatus.RELEASED
        return PriceSnapshotReleased(snapshot_id=self.id)
