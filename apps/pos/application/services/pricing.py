"""
POS Phase 7 -- Authoritative Pricing Integration.

`ResolveLineItemPrice` is a pure, read-only query -- it never touches
`SaleRepository`, never constructs or mutates a `Sale`. Matches
`SearchProduct`'s own certified precedent exactly: identification and
pricing resolution both remain strictly separate from Sale mutation,
which continues to happen only through the existing, unmodified
`AddLineItem` (Section 22 of this phase's own brief -- Pricing must
never call Sale mutation directly, and this service structurally
cannot).

**Never duplicates any Pricing algorithm.** Every discount rule,
campaign, coupon, and quantity-tier calculation happens inside
Pricing's own certified `CalculatePrice` Application Service,
reached exclusively through the `PricingResolver` Port. This file
contains zero pricing logic of its own.

**Preserves `AddLineItem`'s existing, frozen contract exactly**
(Section 7, Option A of this phase's own brief): the caller uses this
service's returned `Money` to supply `unit_price_amount`/
`unit_price_currency` to the existing, unmodified `AddLineItem` call
-- two genuinely separate operations, never combined into one.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from apps.pos.application.ports import PricingResolver
from shared.value_objects.money import Money


class ResolveLineItemPrice:
    def __init__(self, pricing_resolver: PricingResolver) -> None:
        self._pricing_resolver = pricing_resolver

    def execute(self, price_list_id: uuid.UUID, variant_id: uuid.UUID, quantity: int = 1, at: datetime | None = None, coupon_code: str | None = None, region: str | None = None, membership_tier_code: str | None = None) -> Money:
        return self._pricing_resolver.calculate_price(price_list_id=price_list_id, variant_id=variant_id, quantity=quantity, at=at, coupon_code=coupon_code, region=region, membership_tier_code=membership_tier_code)
