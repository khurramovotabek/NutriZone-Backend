from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.pricing.application.services._shared import PricingServiceContext
from apps.pricing.application.services.coupons_bundles_snapshots import (
    ConsumePriceSnapshot, CreateCoupon, LockPrice, RedeemCoupon,
    ReleasePriceSnapshot, RevokeCoupon,
)
from apps.pricing.tests.application.fakes import (
    FakeCouponRepository, FakePriceSnapshotRepository, collect_events,
)
from common.exceptions import ConflictError, ResourceNotFound

pytestmark = pytest.mark.django_db


def _ctx():
    events: list = []
    return PricingServiceContext(stage_events=collect_events(events), actor_id=uuid.uuid4()), events


class TestCoupon:
    def test_create_coupon(self):
        repo = FakeCouponRepository()
        ctx, events = _ctx()
        coupon = CreateCoupon(repo, ctx).execute(code="SAVE20NOW", coupon_type="coupon", discount_value_type="percentage", discount_percentage=Decimal("20"))
        assert coupon.code.value == "SAVE20NOW"
        assert any(e[0] == "CouponCreated" for e in events)

    def test_duplicate_code_raises(self):
        repo = FakeCouponRepository()
        ctx, _ = _ctx()
        CreateCoupon(repo, ctx).execute(code="SAVE20NOW", coupon_type="coupon", discount_value_type="percentage", discount_percentage=Decimal("20"))
        with pytest.raises(ConflictError):
            CreateCoupon(repo, ctx).execute(code="SAVE20NOW", coupon_type="coupon", discount_value_type="percentage", discount_percentage=Decimal("10"))

    def test_redeem_requires_activation_first(self):
        repo = FakeCouponRepository()
        ctx, _ = _ctx()
        CreateCoupon(repo, ctx).execute(code="NEEDSACT", coupon_type="coupon", discount_value_type="percentage", discount_percentage=Decimal("10"))
        with pytest.raises(Exception):
            RedeemCoupon(repo, ctx).execute(code="NEEDSACT", redeemed_by=uuid.uuid4(), order_reference="ORDER-001")

    def test_redeem_after_manual_activation(self):
        repo = FakeCouponRepository()
        ctx, events = _ctx()
        coupon = CreateCoupon(repo, ctx).execute(code="ACTIVE20", coupon_type="coupon", discount_value_type="percentage", discount_percentage=Decimal("20"))
        coupon.activate()
        repo.save(coupon)

        redeemed = RedeemCoupon(repo, ctx).execute(code="ACTIVE20", redeemed_by=uuid.uuid4(), order_reference="ORDER-001")
        assert redeemed.redemption_count == 1
        assert any(e[0] == "CouponRedeemed" for e in events)

    def test_redeem_missing_coupon_raises(self):
        ctx, _ = _ctx()
        with pytest.raises(ResourceNotFound):
            RedeemCoupon(FakeCouponRepository(), ctx).execute(code="DOESNOTEXIST", redeemed_by=uuid.uuid4(), order_reference="ORDER-001")

    def test_revoke_coupon(self):
        repo = FakeCouponRepository()
        ctx, events = _ctx()
        coupon = CreateCoupon(repo, ctx).execute(code="REVOKEME", coupon_type="promo", discount_value_type="fixed_amount", discount_fixed_amount=Decimal("5.00"))
        revoked = RevokeCoupon(repo, ctx).execute(coupon.id)
        assert revoked.status.value == "revoked"
        assert any(e[0] == "CouponRevoked" for e in events)


class TestPriceSnapshot:
    def test_lock_then_consume(self):
        repo = FakePriceSnapshotRepository()
        ctx, events = _ctx()
        variant_id = uuid.uuid4()
        snapshot = LockPrice(repo, ctx).execute(product_variant_id=variant_id, locked_amount=Decimal("49.99"))
        assert snapshot.status.value == "locked"
        assert any(e[0] == "PriceLocked" for e in events)

        consumed = ConsumePriceSnapshot(repo, ctx).execute(snapshot.id)
        assert consumed.status.value == "consumed"
        assert any(e[0] == "PriceSnapshotConsumed" for e in events)

    def test_lock_then_release(self):
        repo = FakePriceSnapshotRepository()
        ctx, events = _ctx()
        snapshot = LockPrice(repo, ctx).execute(product_variant_id=uuid.uuid4(), locked_amount=Decimal("30.00"))

        released = ReleasePriceSnapshot(repo, ctx).execute(snapshot.id)
        assert released.status.value == "released"
        assert any(e[0] == "PriceSnapshotReleased" for e in events)

    def test_consume_missing_snapshot_raises(self):
        ctx, _ = _ctx()
        with pytest.raises(ResourceNotFound):
            ConsumePriceSnapshot(FakePriceSnapshotRepository(), ctx).execute(uuid.uuid4())

    def test_double_consume_raises(self):
        repo = FakePriceSnapshotRepository()
        ctx, _ = _ctx()
        snapshot = LockPrice(repo, ctx).execute(product_variant_id=uuid.uuid4(), locked_amount=Decimal("30.00"))
        ConsumePriceSnapshot(repo, ctx).execute(snapshot.id)
        with pytest.raises(Exception):
            ConsumePriceSnapshot(repo, ctx).execute(snapshot.id)
