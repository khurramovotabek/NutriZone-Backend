"""
Pricing domain exceptions.
"""
from __future__ import annotations

from common.exceptions import BusinessRuleViolation, ConflictError, ValidationFailed


class InvalidPriceConfiguration(ValidationFailed):
    code = "INVALID_PRICE_CONFIGURATION"


class DuplicatePriceListEntry(ConflictError):
    code = "DUPLICATE_PRICE_LIST_ENTRY"


class DuplicateCouponCode(ConflictError):
    code = "DUPLICATE_COUPON_CODE"


class CouponExpired(BusinessRuleViolation):
    code = "COUPON_EXPIRED"


class CouponExhausted(BusinessRuleViolation):
    code = "COUPON_EXHAUSTED"


class CouponNotActive(BusinessRuleViolation):
    code = "COUPON_NOT_ACTIVE"


class CampaignNotActive(BusinessRuleViolation):
    code = "CAMPAIGN_NOT_ACTIVE"


class CampaignSchedulingConflict(ConflictError):
    code = "CAMPAIGN_SCHEDULING_CONFLICT"


class InvalidDiscountStack(BusinessRuleViolation):
    """Raised when an EXCLUSIVE discount is combined with any other discount -- the one stacking violation that can never be silently resolved by priority ordering alone."""

    code = "INVALID_DISCOUNT_STACK"


class PriceListArchived(ConflictError):
    code = "PRICE_LIST_ARCHIVED"


class InvalidPriceListLifecycleTransition(ConflictError):
    code = "INVALID_PRICE_LIST_LIFECYCLE_TRANSITION"


class InvalidPricingRuleLifecycleTransition(ConflictError):
    code = "INVALID_PRICING_RULE_LIFECYCLE_TRANSITION"


class InvalidCampaignLifecycleTransition(ConflictError):
    code = "INVALID_CAMPAIGN_LIFECYCLE_TRANSITION"


class InvalidCouponLifecycleTransition(ConflictError):
    code = "INVALID_COUPON_LIFECYCLE_TRANSITION"


class PriceSnapshotExpired(BusinessRuleViolation):
    code = "PRICE_SNAPSHOT_EXPIRED"


class PriceSnapshotAlreadyConsumed(ConflictError):
    code = "PRICE_SNAPSHOT_ALREADY_CONSUMED"


class NegativeMargin(BusinessRuleViolation):
    """Raised when a sale price would fall below cost price and the caller has not explicitly allowed a loss-leader price -- see domain/services.py::MarginCalculator."""

    code = "NEGATIVE_MARGIN"


class PricingEntityNotFound(ValidationFailed):
    code = "PRICING_ENTITY_NOT_FOUND"
