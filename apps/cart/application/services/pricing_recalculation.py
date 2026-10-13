"""
Phase 02H's Cart -> Pricing pricing-recalculation integration.

## The confirmed gap this closes

Reconnaissance found that `apps.pricing.application.services.queries.
CalculatePrice` already fully, correctly implements coupon
eligibility validation (`Coupon.assert_redeemable()`), campaign
targeting, pricing-rule application, and deterministic stacking
resolution (`PriceCalculationEngine`, itself already correct for
EXCLUSIVE/BEST_OF/STACKABLE modes) -- but nothing in `apps/cart`
ever called it. `Cart.apply_coupon_reference()` only records a
`coupon_id`; `AttachPriceSnapshot` only records whatever
`unit_amount` its caller supplies. No automated process connected
the two, meaning a coupon "applied" to a cart never actually changed
any item's price. This module is the missing integration, not a new
pricing algorithm -- every calculation already existed and is reused
verbatim.

## Price list resolution -- a disclosed design decision, not a
## discovered convention

`Cart` has no `price_list_id` field, only `currency`, and no
"default price list" convention was found anywhere in the repository.
This module resolves the price list via `f"DEFAULT-{cart.currency}"`,
matching `PriceListCode`'s own documented example ("DEFAULT-UZS") --
a reasonable, evidence-adjacent default given no other mechanism
exists, but explicitly a decision made in this phase, not a
pre-existing rule that was merely being followed.

## Coupon resolution

`Cart.coupon_ids` stores coupon IDs, not codes, but `CalculatePrice`
takes a `coupon_code`. This module bridges the two via
`CouponRepository.get_by_id()` (Pricing's own, already-existing
method) before calling `CalculatePrice` -- no new coupon lookup
mechanism was introduced.

## Full chain per item

`CalculatePrice.execute(...)` -> `PriceCalculationResult.final_price`
-> `LockPrice.execute(...)` (Pricing's own existing price-snapshot
creation service) -> `AttachPriceSnapshot.execute(...)` (Cart's own
existing reference-recording service). Every step already existed;
this module is the orchestration that was missing.
"""
from __future__ import annotations

import uuid

from django.db import transaction

from apps.cart.application.ports import CartRepository
from apps.cart.application.services._shared import CartServiceContext
from apps.cart.domain.aggregates import Cart
from common.exceptions import ResourceNotFound


class RecalculateCartPricing:
    """Wraps Pricing's own CalculatePrice/LockPrice services (never a duplicate calculation) to recompute and re-attach every item's authoritative price, reflecting whichever coupon(s)/campaigns currently apply."""

    def __init__(self, repo: CartRepository, ctx: CartServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, cart_id: uuid.UUID) -> Cart:
        from apps.cart.infrastructure.composition import build_attach_price_snapshot
        from apps.pricing.infrastructure.composition import (
            build_calculate_price, build_coupon_repository, build_lock_price, build_price_list_repository,
        )

        cart = self._repo.get_by_id(cart_id)
        if cart is None:
            raise ResourceNotFound("Cart not found.")

        price_list = build_price_list_repository().get_by_code(f"DEFAULT-{cart.currency}")
        if price_list is None:
            # No configured price list for this currency -- nothing to
            # recalculate against; leave existing prices untouched
            # rather than fail the whole cart on a missing reference
            # table, matching this phase's own "do not invent
            # unrelated business behavior" discipline.
            return cart

        coupon_code = None
        if cart.coupon_ids:
            coupon = build_coupon_repository().get_by_id(next(iter(cart.coupon_ids)))
            coupon_code = coupon.code.value if coupon is not None else None

        calculate_price = build_calculate_price()
        lock_price = build_lock_price()
        attach_price_snapshot = build_attach_price_snapshot(self._ctx.actor_id)

        for item in list(cart.items.values()):
            result = calculate_price.execute(
                price_list_id=price_list.id, product_variant_id=item.product_variant_id,
                quantity=item.quantity.value, coupon_code=coupon_code,
            )
            snapshot = lock_price.execute(product_variant_id=item.product_variant_id, locked_amount=result.final_price.amount, currency=result.final_price.currency)
            attach_price_snapshot.execute(cart_id=cart.id, item_id=item.id, price_snapshot_id=snapshot.id, unit_amount=result.final_price.amount, currency=result.final_price.currency)

        return self._repo.get_by_id(cart_id)
