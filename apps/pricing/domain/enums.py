"""
Pricing domain enums.

`pricing` IS one of the Domain Architecture Specification's original
bounded contexts (§2.3, confirmed by reading the module's own
placeholder scaffold before any code was written) -- no reconciliation
note is needed for the module's own existence. See domain/README-level
note in this Phase 1 report re: the one real forward-dependency
inconsistency found and resolved (Wallet/Loyalty referenced by
parameter, never by import).
"""
from __future__ import annotations

from common.utils import DomainStrEnum


class PriceListStatus(DomainStrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class PriceType(DomainStrEnum):
    """The five price 'slots' this module's brief names: Base/Cost/Sale/Compare-at/Discount."""

    BASE = "base"
    COST = "cost"
    SALE = "sale"
    COMPARE_AT = "compare_at"
    DISCOUNT = "discount"


class PricingRuleType(DomainStrEnum):
    QUANTITY_DISCOUNT = "quantity_discount"
    TIME_BASED = "time_based"
    REGIONAL = "regional"
    DYNAMIC = "dynamic"
    MEMBERSHIP = "membership"


class PricingRuleStatus(DomainStrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    EXPIRED = "expired"
    ARCHIVED = "archived"


class DiscountValueType(DomainStrEnum):
    PERCENTAGE = "percentage"
    FIXED_AMOUNT = "fixed_amount"


class CampaignType(DomainStrEnum):
    """Flash Sale and Campaign Pricing are the same aggregate shape (time-bounded promotional pricing) -- this discriminator is the only difference the brief calls for two distinct capabilities."""

    FLASH_SALE = "flash_sale"
    CAMPAIGN = "campaign"


class CampaignStatus(DomainStrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    ENDED = "ended"
    CANCELLED = "cancelled"


class CouponStatus(DomainStrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    EXHAUSTED = "exhausted"
    EXPIRED = "expired"
    REVOKED = "revoked"


class CouponType(DomainStrEnum):
    """Coupon Pricing and Promo Pricing -- same aggregate shape (code-redeemed discount), distinguished by whether a code is customer-entered (COUPON) or auto-applied (PROMO)."""

    COUPON = "coupon"
    PROMO = "promo"


class PriceSnapshotStatus(DomainStrEnum):
    LOCKED = "locked"
    RELEASED = "released"
    CONSUMED = "consumed"
    EXPIRED = "expired"


class StackingMode(DomainStrEnum):
    """Deterministic discount-stacking behavior, per this phase's explicit 'Discount Stacking Rules'/'Promotion Priority' requirement."""

    EXCLUSIVE = "exclusive"  # this discount cannot combine with any other
    STACKABLE = "stackable"  # combines additively with other STACKABLE discounts
    BEST_OF = "best_of"  # only the single largest BEST_OF discount applies


class DiscountSourceType(DomainStrEnum):
    """Every kind of thing that can contribute a discount to one price calculation -- the deterministic priority ordering used by PriceCalculationEngine (domain/services.py) is defined over this enum's declaration order."""

    PRICING_RULE = "pricing_rule"
    CAMPAIGN = "campaign"
    COUPON = "coupon"
    MEMBERSHIP = "membership"


class TaxMode(DomainStrEnum):
    INCLUSIVE = "inclusive"
    EXCLUSIVE = "exclusive"


class PriceChangeReason(DomainStrEnum):
    """Backs Pricing History entries."""

    MANUAL = "manual"
    RULE_APPLIED = "rule_applied"
    CAMPAIGN_APPLIED = "campaign_applied"
    SCHEDULED_CHANGE = "scheduled_change"
    COST_UPDATE = "cost_update"
