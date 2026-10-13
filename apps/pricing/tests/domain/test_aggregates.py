from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from apps.pricing.domain.aggregates import Campaign, Coupon, PriceList, PriceSnapshot, PricingRule
from apps.pricing.domain.entities import CampaignTarget
from apps.pricing.domain.enums import CampaignType, CouponType, PricingRuleType, StackingMode
from apps.pricing.domain.exceptions import (
    CampaignNotActive, CouponExhausted, CouponExpired, CouponNotActive,
    InvalidCampaignLifecycleTransition, InvalidCouponLifecycleTransition, InvalidPriceListLifecycleTransition,
    InvalidPricingRuleLifecycleTransition, PriceListArchived, PriceSnapshotAlreadyConsumed, PriceSnapshotExpired,
)
from apps.pricing.domain.value_objects import (
    CouponCode, DiscountValue, Money, Percentage, PriceListCode, PriceSnapshotToken, PriceValidityPeriod,
    QuantityTier, RegionCode,
)
from common.exceptions import ValidationFailed

pytestmark = pytest.mark.unit


def _percentage_discount(value: str = "10") -> DiscountValue:
    return DiscountValue(value_type="percentage", percentage=Percentage(value=Decimal(value)))


def _bare_price_list() -> PriceList:
    return PriceList(id=uuid.uuid4(), code=PriceListCode("DEFAULT-UZS"), name="Default", currency="UZS")


class TestPriceList:
    def test_set_price_creates_entry(self):
        price_list = _bare_price_list()
        variant_id = uuid.uuid4()
        event = price_list.set_price(variant_id, Money(amount=Decimal("100.00"), currency="UZS"))
        assert len(price_list.entries) == 1
        assert event.new_amount == "100.00"
        assert event.old_amount is None

    def test_set_price_appends_history_unconditionally(self):
        price_list = _bare_price_list()
        variant_id = uuid.uuid4()
        price_list.set_price(variant_id, Money(amount=Decimal("100.00"), currency="UZS"))
        assert len(price_list.history) == 1

    def test_set_price_twice_updates_entry_not_duplicates(self):
        price_list = _bare_price_list()
        variant_id = uuid.uuid4()
        price_list.set_price(variant_id, Money(amount=Decimal("100.00"), currency="UZS"))
        event = price_list.set_price(variant_id, Money(amount=Decimal("120.00"), currency="UZS"))
        assert len(price_list.entries) == 1
        assert event.old_amount == "100.00"
        assert event.new_amount == "120.00"
        assert len(price_list.history) == 2

    def test_set_price_on_archived_list_raises(self):
        price_list = _bare_price_list()
        price_list.archive()
        with pytest.raises(PriceListArchived):
            price_list.set_price(uuid.uuid4(), Money(amount=Decimal("100.00"), currency="UZS"))

    def test_activate_archived_raises(self):
        price_list = _bare_price_list()
        price_list.archive()
        with pytest.raises(InvalidPriceListLifecycleTransition):
            price_list.activate()

    def test_archive_twice_raises(self):
        price_list = _bare_price_list()
        price_list.archive()
        with pytest.raises(InvalidPriceListLifecycleTransition):
            price_list.archive()

    def test_entry_for_variant_public_accessor(self):
        price_list = _bare_price_list()
        variant_id = uuid.uuid4()
        price_list.set_price(variant_id, Money(amount=Decimal("100.00"), currency="UZS"))
        assert price_list.entry_for_variant(variant_id) is not None
        assert price_list.entry_for_variant(uuid.uuid4()) is None

    def test_empty_name_raises(self):
        with pytest.raises(ValidationFailed):
            PriceList(id=uuid.uuid4(), code=PriceListCode("X"), name="", currency="UZS")


class TestPricingRule:
    def test_quantity_discount_requires_tiers(self):
        with pytest.raises(ValidationFailed):
            PricingRule(id=uuid.uuid4(), rule_type=PricingRuleType.QUANTITY_DISCOUNT, discount=_percentage_discount())

    def test_time_based_requires_validity(self):
        with pytest.raises(ValidationFailed):
            PricingRule(id=uuid.uuid4(), rule_type=PricingRuleType.TIME_BASED, discount=_percentage_discount())

    def test_regional_requires_region(self):
        with pytest.raises(ValidationFailed):
            PricingRule(id=uuid.uuid4(), rule_type=PricingRuleType.REGIONAL, discount=_percentage_discount())

    def test_membership_requires_tier_code(self):
        with pytest.raises(ValidationFailed):
            PricingRule(id=uuid.uuid4(), rule_type=PricingRuleType.MEMBERSHIP, discount=_percentage_discount())

    def test_tier_for_quantity_returns_highest_qualifying(self):
        tiers = (
            QuantityTier(minimum_quantity=5, discount=_percentage_discount("5")),
            QuantityTier(minimum_quantity=10, discount=_percentage_discount("10")),
        )
        rule = PricingRule(id=uuid.uuid4(), rule_type=PricingRuleType.QUANTITY_DISCOUNT, discount=_percentage_discount(), quantity_tiers=tiers)
        tier = rule.tier_for_quantity(12)
        assert tier.minimum_quantity == 10

    def test_tier_for_quantity_below_all_tiers_returns_none(self):
        tiers = (QuantityTier(minimum_quantity=10, discount=_percentage_discount()),)
        rule = PricingRule(id=uuid.uuid4(), rule_type=PricingRuleType.QUANTITY_DISCOUNT, discount=_percentage_discount(), quantity_tiers=tiers)
        assert rule.tier_for_quantity(5) is None

    def test_archive_activated_rule_then_activate_raises(self):
        rule = PricingRule(id=uuid.uuid4(), rule_type=PricingRuleType.DYNAMIC, discount=_percentage_discount())
        rule.activate()
        rule.archive()
        with pytest.raises(InvalidPricingRuleLifecycleTransition):
            rule.activate()

    def test_is_active_at_requires_active_status(self):
        rule = PricingRule(id=uuid.uuid4(), rule_type=PricingRuleType.DYNAMIC, discount=_percentage_discount())
        assert rule.is_active_at(datetime.utcnow()) is False
        rule.activate()
        assert rule.is_active_at(datetime.utcnow()) is True


class TestCampaign:
    def _campaign(self, starts_delta=-1, ends_delta=1) -> Campaign:
        now = datetime.utcnow()
        return Campaign(
            id=uuid.uuid4(), campaign_type=CampaignType.FLASH_SALE, name="Flash Sale", discount=_percentage_discount(),
            validity=PriceValidityPeriod(starts_at=now + timedelta(hours=starts_delta), ends_at=now + timedelta(hours=ends_delta)),
        )

    def test_empty_name_raises(self):
        with pytest.raises(ValidationFailed):
            Campaign(id=uuid.uuid4(), campaign_type=CampaignType.CAMPAIGN, name="", discount=_percentage_discount(), validity=PriceValidityPeriod(starts_at=datetime.utcnow()))

    def test_add_target_and_applies_to(self):
        campaign = self._campaign()
        variant_id = uuid.uuid4()
        campaign.add_target(CampaignTarget(id=uuid.uuid4(), target_type="variant", target_id=variant_id))
        assert campaign.applies_to("variant", variant_id) is True
        assert campaign.applies_to("variant", uuid.uuid4()) is False

    def test_assert_active_at_raises_when_not_active_status(self):
        campaign = self._campaign()
        with pytest.raises(CampaignNotActive):
            campaign.assert_active_at(datetime.utcnow())

    def test_assert_active_at_passes_when_active_and_in_window(self):
        campaign = self._campaign()
        campaign.activate()
        campaign.assert_active_at(datetime.utcnow())

    def test_end_ended_campaign_raises(self):
        campaign = self._campaign()
        campaign.activate()
        campaign.end()
        with pytest.raises(InvalidCampaignLifecycleTransition):
            campaign.end()

    def test_cancel_ended_campaign_raises(self):
        campaign = self._campaign()
        campaign.activate()
        campaign.end()
        with pytest.raises(InvalidCampaignLifecycleTransition):
            campaign.cancel()

    def test_activate_cancelled_campaign_raises(self):
        campaign = self._campaign()
        campaign.cancel()
        with pytest.raises(InvalidCampaignLifecycleTransition):
            campaign.activate()


class TestCoupon:
    def _coupon(self, max_redemptions=None) -> Coupon:
        return Coupon(id=uuid.uuid4(), code=CouponCode("SAVE20NOW"), coupon_type=CouponType.COUPON, discount=_percentage_discount("20"), max_redemptions=max_redemptions)

    def test_redeem_requires_active_status(self):
        coupon = self._coupon()
        with pytest.raises(CouponNotActive):
            coupon.redeem(uuid.uuid4(), "ORDER-001", datetime.utcnow())

    def test_redeem_after_activation(self):
        coupon = self._coupon()
        coupon.activate()
        event = coupon.redeem(uuid.uuid4(), "ORDER-001", datetime.utcnow())
        assert coupon.redemption_count == 1
        assert event.order_reference == "ORDER-001"

    def test_redeem_expired_coupon_raises(self):
        coupon = self._coupon()
        coupon.activate()
        coupon.validity = PriceValidityPeriod(starts_at=datetime.utcnow() - timedelta(days=10), ends_at=datetime.utcnow() - timedelta(days=1))
        with pytest.raises(CouponExpired):
            coupon.redeem(uuid.uuid4(), "ORDER-001", datetime.utcnow())

    def test_redeem_exhausts_at_max_redemptions(self):
        coupon = self._coupon(max_redemptions=1)
        coupon.activate()
        coupon.redeem(uuid.uuid4(), "ORDER-001", datetime.utcnow())
        assert coupon.status.value == "exhausted"
        with pytest.raises(CouponExhausted):
            coupon.redeem(uuid.uuid4(), "ORDER-002", datetime.utcnow())

    def test_revoke_then_activate_raises(self):
        coupon = self._coupon()
        coupon.revoke()
        with pytest.raises(InvalidCouponLifecycleTransition):
            coupon.activate()

    def test_revoke_twice_raises(self):
        coupon = self._coupon()
        coupon.revoke()
        with pytest.raises(InvalidCouponLifecycleTransition):
            coupon.revoke()


class TestPriceSnapshot:
    def _snapshot(self, expires_delta_minutes=15) -> PriceSnapshot:
        return PriceSnapshot(
            id=uuid.uuid4(), token=PriceSnapshotToken(uuid.uuid4()), product_variant_id=uuid.uuid4(),
            locked_price=Money(amount=Decimal("99.00"), currency="UZS"), expires_at=datetime.utcnow() + timedelta(minutes=expires_delta_minutes),
        )

    def test_consume_once_succeeds(self):
        snapshot = self._snapshot()
        event = snapshot.consume(datetime.utcnow())
        assert snapshot.status.value == "consumed"
        assert event.snapshot_id == snapshot.id

    def test_consume_twice_raises(self):
        snapshot = self._snapshot()
        snapshot.consume(datetime.utcnow())
        with pytest.raises(PriceSnapshotAlreadyConsumed):
            snapshot.consume(datetime.utcnow())

    def test_consume_after_expiry_raises(self):
        snapshot = self._snapshot(expires_delta_minutes=-5)
        with pytest.raises(PriceSnapshotExpired):
            snapshot.consume(datetime.utcnow())

    def test_release_then_consume_raises(self):
        snapshot = self._snapshot()
        snapshot.release()
        with pytest.raises(PriceSnapshotAlreadyConsumed):
            snapshot.consume(datetime.utcnow())

    def test_release_twice_raises(self):
        snapshot = self._snapshot()
        snapshot.release()
        with pytest.raises(PriceSnapshotAlreadyConsumed):
            snapshot.release()

    def test_consume_then_release_raises(self):
        snapshot = self._snapshot()
        snapshot.consume(datetime.utcnow())
        with pytest.raises(PriceSnapshotAlreadyConsumed):
            snapshot.release()
