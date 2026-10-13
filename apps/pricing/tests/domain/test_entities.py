from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import pytest

from apps.pricing.domain.entities import CampaignTarget, CouponRedemption, DiscountLine, PriceHistoryEntry, PriceListEntry
from apps.pricing.domain.value_objects import Money
from common.exceptions import ValidationFailed

pytestmark = pytest.mark.unit


class TestPriceListEntry:
    def test_valid_construction(self):
        entry = PriceListEntry(id=uuid.uuid4(), product_variant_id=uuid.uuid4(), base_price=Money(amount=Decimal("100.00"), currency="UZS"))
        assert entry.base_price.amount == Decimal("100.00")

    def test_sale_price_above_base_raises(self):
        with pytest.raises(ValidationFailed):
            PriceListEntry(id=uuid.uuid4(), product_variant_id=uuid.uuid4(), base_price=Money(amount=Decimal("100.00"), currency="UZS"), sale_price=Money(amount=Decimal("150.00"), currency="UZS"))

    def test_sale_price_equal_to_base_is_valid(self):
        PriceListEntry(id=uuid.uuid4(), product_variant_id=uuid.uuid4(), base_price=Money(amount=Decimal("100.00"), currency="UZS"), sale_price=Money(amount=Decimal("100.00"), currency="UZS"))

    def test_compare_at_below_base_raises(self):
        with pytest.raises(ValidationFailed):
            PriceListEntry(id=uuid.uuid4(), product_variant_id=uuid.uuid4(), base_price=Money(amount=Decimal("100.00"), currency="UZS"), compare_at_price=Money(amount=Decimal("50.00"), currency="UZS"))

    def test_compare_at_equal_to_base_is_valid(self):
        PriceListEntry(id=uuid.uuid4(), product_variant_id=uuid.uuid4(), base_price=Money(amount=Decimal("100.00"), currency="UZS"), compare_at_price=Money(amount=Decimal("100.00"), currency="UZS"))

    def test_default_optional_prices_are_none(self):
        entry = PriceListEntry(id=uuid.uuid4(), product_variant_id=uuid.uuid4(), base_price=Money(amount=Decimal("100.00"), currency="UZS"))
        assert entry.cost_price is None
        assert entry.sale_price is None
        assert entry.compare_at_price is None


class TestCampaignTarget:
    def test_construction(self):
        target = CampaignTarget(id=uuid.uuid4(), target_type="variant", target_id=uuid.uuid4())
        assert target.target_type == "variant"


class TestPriceHistoryEntry:
    def test_construction_with_null_old_amount(self):
        entry = PriceHistoryEntry(id=uuid.uuid4(), product_variant_id=uuid.uuid4(), price_type="base", old_amount=None, new_amount=Money(amount=Decimal("50.00"), currency="UZS"), reason="manual", changed_at=datetime.utcnow())
        assert entry.old_amount is None

    def test_construction_with_old_amount(self):
        entry = PriceHistoryEntry(
            id=uuid.uuid4(), product_variant_id=uuid.uuid4(), price_type="base",
            old_amount=Money(amount=Decimal("40.00"), currency="UZS"), new_amount=Money(amount=Decimal("50.00"), currency="UZS"),
            reason="rule_applied", changed_at=datetime.utcnow(),
        )
        assert entry.old_amount.amount == Decimal("40.00")


class TestCouponRedemption:
    def test_construction(self):
        redemption = CouponRedemption(id=uuid.uuid4(), redeemed_by=uuid.uuid4(), order_reference="ORDER-001", redeemed_at=datetime.utcnow())
        assert redemption.order_reference == "ORDER-001"


class TestDiscountLine:
    def test_construction(self):
        line = DiscountLine(id=uuid.uuid4(), source_type="coupon", source_id=uuid.uuid4(), label="10% off", amount_deducted=Money(amount=Decimal("10.00"), currency="UZS"), stacking_mode="stackable")
        assert line.label == "10% off"

    def test_source_id_can_be_null(self):
        """A rare case (e.g. a synthetic/manual discount with no persisted source) -- source_id is Optional on the entity."""
        line = DiscountLine(id=uuid.uuid4(), source_type="pricing_rule", source_id=None, label="manual", amount_deducted=Money(amount=Decimal("5.00"), currency="UZS"), stacking_mode="stackable")
        assert line.source_id is None
