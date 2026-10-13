"""
Pricing domain entities (non-root members of an aggregate).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from apps.pricing.domain.value_objects import DiscountValue, Money


@dataclass(slots=True)
class PriceListEntry:
    """Non-root entity, owned by PriceList -- one product variant's Base/Cost/Sale/Compare-at prices within that list."""

    id: uuid.UUID
    product_variant_id: uuid.UUID
    base_price: Money
    cost_price: Money | None = None
    sale_price: Money | None = None
    compare_at_price: Money | None = None

    def __post_init__(self) -> None:
        from common.exceptions import ValidationFailed

        if self.sale_price is not None and self.sale_price.amount > self.base_price.amount:
            raise ValidationFailed("sale_price must not exceed base_price.", details={"fields": [{"field": "sale_price", "code": "ABOVE_BASE_PRICE"}]})
        if self.compare_at_price is not None and self.compare_at_price.amount < self.base_price.amount:
            raise ValidationFailed("compare_at_price must be at or above base_price (it represents a pre-discount reference price).", details={"fields": [{"field": "compare_at_price", "code": "BELOW_BASE_PRICE"}]})


@dataclass(slots=True)
class CampaignTarget:
    """Non-root entity, owned by Campaign -- one product variant (or category, bundle) the campaign's discount applies to."""

    id: uuid.UUID
    target_type: str  # "variant" | "category" | "bundle"
    target_id: uuid.UUID


@dataclass(slots=True)
class PriceHistoryEntry:
    """Non-root entity, owned by PriceList (per entry) -- an append-only record of a price change, backing the 'Pricing History' capability."""

    id: uuid.UUID
    product_variant_id: uuid.UUID
    price_type: str  # PriceType.value
    old_amount: Money | None
    new_amount: Money
    reason: str  # PriceChangeReason.value
    changed_at: datetime


@dataclass(slots=True)
class CouponRedemption:
    """Non-root entity, owned by Coupon -- one redemption record. `redeemed_by`/`order_reference` are opaque cross-module references (customer/order IDs), never types imported from Identity/Ordering."""

    id: uuid.UUID
    redeemed_by: uuid.UUID
    order_reference: str
    redeemed_at: datetime


@dataclass(slots=True)
class DiscountLine:
    """
    Non-root entity -- one applied discount within a
    `PriceCalculationResult` (domain/services.py). This is the
    line-item breakdown output of `PriceCalculationEngine`, not
    persisted state of its own; it exists so a price preview/receipt
    can show *why* the final price is what it is, not just the number.
    """

    id: uuid.UUID
    source_type: str  # DiscountSourceType.value
    source_id: uuid.UUID | None
    label: str
    amount_deducted: Money
    stacking_mode: str  # StackingMode.value
