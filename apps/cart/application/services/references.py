"""
Reference Application Services: ApplyCouponReference,
RemoveCouponReference, AttachPriceSnapshot, DetachPriceSnapshot,
AttachReservation, DetachReservation.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone as django_timezone

from apps.cart.application.ports import CartRepository
from apps.cart.application.services._shared import CartServiceContext
from apps.cart.domain.aggregates import Cart
from apps.cart.domain.value_objects import Money
from common.exceptions import ResourceNotFound


class ApplyCouponReference:
    def __init__(self, repo: CartRepository, ctx: CartServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, cart_id: uuid.UUID, coupon_id: uuid.UUID) -> Cart:
        cart = self._repo.get_by_id(cart_id)
        if cart is None:
            raise ResourceNotFound("Cart not found.")
        event = cart.apply_coupon_reference(coupon_id, django_timezone.now())
        saved = self._repo.save(cart)
        self._ctx.stage_events([("CouponReferenceApplied", event.to_payload())])
        self._ctx.audit().updated(entity_type="Cart", entity_id=str(cart_id), before={}, after={"coupon_id": str(coupon_id)})
        self._ctx.invalidate_cart_cache()

        from apps.cart.application.services.pricing_recalculation import RecalculateCartPricing
        return RecalculateCartPricing(self._repo, self._ctx).execute(cart_id)


class ApplyCouponToCartWithoutRepricing:
    """
    Real, closed gap: the existing ApplyCouponReference re-runs
    RecalculateCartPricing, which overwrites each item's own
    price_reference.unit_amount with the coupon-discounted price --
    fine for that endpoint's own intended use, but it means Checkout
    Preview's real, item-level subtotal is already discounted, and
    computing a discount on top of it would double-count. This
    variant only records which coupon is attached to the cart
    (cart.coupon_ids), leaving each item's own locked price
    untouched -- CheckoutPreviewView's own real discount computation
    (_compute_cart_discount) is what surfaces the actual savings.
    """

    def __init__(self, repo: CartRepository, ctx: CartServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, cart_id: uuid.UUID, coupon_id: uuid.UUID) -> Cart:
        cart = self._repo.get_by_id(cart_id)
        if cart is None:
            raise ResourceNotFound("Cart not found.")
        event = cart.apply_coupon_reference(coupon_id, django_timezone.now())
        saved = self._repo.save(cart)
        self._ctx.stage_events([("CouponReferenceApplied", event.to_payload())])
        self._ctx.audit().updated(entity_type="Cart", entity_id=str(cart_id), before={}, after={"coupon_id": str(coupon_id)})
        self._ctx.invalidate_cart_cache()
        return saved


class RemoveCouponReference:
    def __init__(self, repo: CartRepository, ctx: CartServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, cart_id: uuid.UUID, coupon_id: uuid.UUID) -> Cart:
        cart = self._repo.get_by_id(cart_id)
        if cart is None:
            raise ResourceNotFound("Cart not found.")
        event = cart.remove_coupon_reference(coupon_id, django_timezone.now())
        saved = self._repo.save(cart)
        self._ctx.stage_events([("CouponReferenceRemoved", event.to_payload())])
        self._ctx.audit().updated(entity_type="Cart", entity_id=str(cart_id), before={}, after={"coupon_id": str(coupon_id)})
        self._ctx.invalidate_cart_cache()

        from apps.cart.application.services.pricing_recalculation import RecalculateCartPricing
        return RecalculateCartPricing(self._repo, self._ctx).execute(cart_id)


class AttachPriceSnapshot:
    def __init__(self, repo: CartRepository, ctx: CartServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, cart_id: uuid.UUID, item_id: uuid.UUID, price_snapshot_id: uuid.UUID, unit_amount: Decimal, currency: str) -> Cart:
        cart = self._repo.get_by_id(cart_id)
        if cart is None:
            raise ResourceNotFound("Cart not found.")
        event = cart.attach_price_snapshot(item_id, price_snapshot_id, Money(amount=unit_amount, currency=currency), django_timezone.now())
        saved = self._repo.save(cart)
        self._ctx.stage_events([("PriceSnapshotAttached", event.to_payload())])
        self._ctx.audit().updated(entity_type="Cart", entity_id=str(cart_id), before={}, after={"item_id": str(item_id), "price_snapshot_id": str(price_snapshot_id)})
        self._ctx.invalidate_cart_cache()
        return saved


class DetachPriceSnapshot:
    def __init__(self, repo: CartRepository, ctx: CartServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, cart_id: uuid.UUID, item_id: uuid.UUID) -> Cart:
        cart = self._repo.get_by_id(cart_id)
        if cart is None:
            raise ResourceNotFound("Cart not found.")
        event = cart.detach_price_snapshot(item_id)
        saved = self._repo.save(cart)
        self._ctx.stage_events([("PriceSnapshotDetached", event.to_payload())])
        self._ctx.audit().updated(entity_type="Cart", entity_id=str(cart_id), before={}, after={"item_id": str(item_id)})
        self._ctx.invalidate_cart_cache()
        return saved


class AttachReservation:
    def __init__(self, repo: CartRepository, ctx: CartServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, cart_id: uuid.UUID, item_id: uuid.UUID, reservation_id: uuid.UUID, expires_at=None) -> Cart:
        cart = self._repo.get_by_id(cart_id)
        if cart is None:
            raise ResourceNotFound("Cart not found.")
        event = cart.attach_reservation(item_id, reservation_id, django_timezone.now(), expires_at=expires_at)
        saved = self._repo.save(cart)
        self._ctx.stage_events([("ReservationAttached", event.to_payload())])
        self._ctx.audit().updated(entity_type="Cart", entity_id=str(cart_id), before={}, after={"item_id": str(item_id), "reservation_id": str(reservation_id)})
        self._ctx.invalidate_cart_cache()
        return saved


class DetachReservation:
    def __init__(self, repo: CartRepository, ctx: CartServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, cart_id: uuid.UUID, item_id: uuid.UUID) -> Cart:
        cart = self._repo.get_by_id(cart_id)
        if cart is None:
            raise ResourceNotFound("Cart not found.")
        event = cart.detach_reservation(item_id)
        saved = self._repo.save(cart)
        self._ctx.stage_events([("ReservationDetached", event.to_payload())])
        self._ctx.audit().updated(entity_type="Cart", entity_id=str(cart_id), before={}, after={"item_id": str(item_id)})
        self._ctx.invalidate_cart_cache()
        return saved
