"""
Coupon & PriceSnapshot Application Services:
CreateCoupon, RedeemCoupon, RevokeCoupon, LockPrice,
ConsumePriceSnapshot, ReleasePriceSnapshot.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone as django_timezone

from apps.pricing.application.ports import CouponRepository, PriceListRepository, PriceSnapshotRepository
from apps.pricing.application.services._shared import PricingServiceContext
from apps.pricing.application.services.queries import CalculatePrice
from apps.pricing.domain.aggregates import Coupon, PriceSnapshot
from apps.pricing.domain.enums import CouponType, StackingMode
from apps.pricing.domain.value_objects import CouponCode, DiscountValue, Money, Percentage, PriceSnapshotToken, PriceValidityPeriod
from common.exceptions import ConflictError, ResourceNotFound


class CreateCoupon:
    def __init__(self, repo: CouponRepository, ctx: PricingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, code: str, coupon_type: str, discount_value_type: str, discount_percentage=None, discount_fixed_amount=None, currency: str = "UZS", starts_at=None, ends_at=None, max_redemptions: int | None = None, stacking_mode: str = StackingMode.EXCLUSIVE.value) -> Coupon:
        if self._repo.code_exists(code):
            raise ConflictError(f"Coupon code '{code}' already exists.")

        discount = DiscountValue(
            value_type=discount_value_type, percentage=Percentage(value=discount_percentage) if discount_percentage is not None else None,
            fixed_amount=Money(amount=discount_fixed_amount, currency=currency) if discount_fixed_amount is not None else None,
        )
        coupon = Coupon(
            id=uuid.uuid4(), code=CouponCode(code), coupon_type=CouponType(coupon_type), discount=discount,
            validity=PriceValidityPeriod(starts_at=starts_at, ends_at=ends_at) if starts_at else None,
            max_redemptions=max_redemptions, stacking_mode=StackingMode(stacking_mode),
        )
        saved = self._repo.save(coupon)

        from apps.pricing.domain.events import CouponCreated

        self._ctx.stage_events([("CouponCreated", CouponCreated(coupon_id=saved.id, code=code).to_payload())])
        self._ctx.audit().created(entity_type="Coupon", entity_id=str(saved.id), after={"code": code})
        self._ctx.invalidate_pricing_cache()
        self._ctx.metric("coupons_created_total")
        return saved


class RedeemCoupon:
    def __init__(self, repo: CouponRepository, ctx: PricingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, code: str, redeemed_by: uuid.UUID, order_reference: str) -> Coupon:
        coupon = self._repo.get_by_code(code)
        if coupon is None:
            raise ResourceNotFound("Coupon not found.")

        event = coupon.redeem(redeemed_by, order_reference, django_timezone.now())
        saved = self._repo.save(coupon)

        self._ctx.stage_events([("CouponRedeemed", event.to_payload())])
        self._ctx.audit().updated(entity_type="Coupon", entity_id=str(coupon.id), before={}, after={"redeemed_by": str(redeemed_by), "order_reference": order_reference})
        self._ctx.invalidate_pricing_cache()
        self._ctx.metric("coupons_redeemed_total")
        return saved


class RevokeCoupon:
    def __init__(self, repo: CouponRepository, ctx: PricingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, coupon_id: uuid.UUID) -> Coupon:
        coupon = self._repo.get_by_id(coupon_id)
        if coupon is None:
            raise ResourceNotFound("Coupon not found.")
        event = coupon.revoke()
        saved = self._repo.save(coupon)
        self._ctx.stage_events([("CouponRevoked", event.to_payload())])
        self._ctx.audit().updated(entity_type="Coupon", entity_id=str(coupon_id), before={}, after={"status": "revoked"})
        self._ctx.invalidate_pricing_cache()
        return saved


class LockPrice:
    """Price Lock / Price Snapshot creation."""

    def __init__(self, repo: PriceSnapshotRepository, ctx: PricingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, product_variant_id: uuid.UUID, locked_amount, currency: str = "UZS", ttl_minutes: int = 15) -> PriceSnapshot:
        now = django_timezone.now()
        snapshot = PriceSnapshot(
            id=uuid.uuid4(), token=PriceSnapshotToken(uuid.uuid4()), product_variant_id=product_variant_id,
            locked_price=Money(amount=locked_amount, currency=currency), expires_at=now + timedelta(minutes=ttl_minutes),
        )
        saved = self._repo.save(snapshot)

        from apps.pricing.domain.events import PriceLocked

        self._ctx.stage_events([("PriceLocked", PriceLocked(snapshot_id=saved.id, product_variant_id=product_variant_id, locked_amount=str(locked_amount)).to_payload())])
        self._ctx.audit().created(entity_type="PriceSnapshot", entity_id=str(saved.id), after={"product_variant_id": str(product_variant_id)})
        self._ctx.metric("price_snapshots_locked_total")
        return saved


class IssueVariantPriceSnapshot:
    """
    Phase 09.4: the customer-safe composition this project was
    missing. Reuses two existing, certified services entirely --
    CalculatePrice (resolves the real, server-authoritative amount)
    and LockPrice (the existing, already-certified snapshot
    persistence mechanism, confirmed via direct inspection to
    already exist under this name -- Phase 09.3's search for
    "CreatePriceSnapshot"/"IssuePriceSnapshot" simply missed it).

    Never accepts a client-supplied price: the caller may only supply
    contextual inputs (variant, quantity, coupon code, region). The
    locked amount is always CalculatePrice's own output, never a
    parameter passed through from the request.
    """

    def __init__(self, price_list_repo: PriceListRepository, calculate_price: CalculatePrice, lock_price: LockPrice) -> None:
        self._price_list_repo = price_list_repo
        self._calculate_price = calculate_price
        self._lock_price = lock_price

    def execute(self, product_variant_id: uuid.UUID, quantity: int = 1, coupon_code: str | None = None, region: str | None = None) -> PriceSnapshot:
        price_list = self._price_list_repo.get_active_for_region(region)
        if price_list is None:
            raise ResourceNotFound("No active price list is configured for this region.")

        result = self._calculate_price.execute(price_list_id=price_list.id, product_variant_id=product_variant_id, quantity=quantity, coupon_code=coupon_code, region=region)
        return self._lock_price.execute(product_variant_id=product_variant_id, locked_amount=result.final_price.amount, currency=result.final_price.currency)


class ConsumePriceSnapshot:
    def __init__(self, repo: PriceSnapshotRepository, ctx: PricingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, snapshot_id: uuid.UUID) -> PriceSnapshot:
        snapshot = self._repo.get_by_id(snapshot_id)
        if snapshot is None:
            raise ResourceNotFound("Price snapshot not found.")
        event = snapshot.consume(django_timezone.now())
        saved = self._repo.save(snapshot)
        self._ctx.stage_events([("PriceSnapshotConsumed", event.to_payload())])
        self._ctx.audit().updated(entity_type="PriceSnapshot", entity_id=str(snapshot_id), before={}, after={"status": "consumed"})
        return saved


class ReleasePriceSnapshot:
    def __init__(self, repo: PriceSnapshotRepository, ctx: PricingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, snapshot_id: uuid.UUID) -> PriceSnapshot:
        snapshot = self._repo.get_by_id(snapshot_id)
        if snapshot is None:
            raise ResourceNotFound("Price snapshot not found.")
        event = snapshot.release()
        saved = self._repo.save(snapshot)
        self._ctx.stage_events([("PriceSnapshotReleased", event.to_payload())])
        self._ctx.audit().updated(entity_type="PriceSnapshot", entity_id=str(snapshot_id), before={}, after={"status": "released"})
        return saved
