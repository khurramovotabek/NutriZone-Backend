from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from apps.pricing.domain.value_objects import (
    CouponCode,
    DiscountValue,
    MarginPercentage,
    Money,
    Percentage,
    PriceListCode,
    PriceSnapshotToken,
    PriceValidityPeriod,
    QuantityTier,
    RegionCode,
    TaxRate,
)
from common.exceptions import ValidationFailed

pytestmark = pytest.mark.unit


class TestMoney:
    """Money is the Shared Kernel re-export -- verified here for Pricing's own usage patterns, not re-testing its own module's test suite."""

    def test_construction(self):
        money = Money(amount=Decimal("100.00"), currency="UZS")
        assert money.amount == Decimal("100.00")
        assert money.currency == "UZS"

    def test_equality(self):
        assert Money(amount=Decimal("50.00"), currency="UZS") == Money(amount=Decimal("50.00"), currency="UZS")

    def test_immutability(self):
        money = Money(amount=Decimal("50.00"), currency="UZS")
        with pytest.raises(Exception):
            money.amount = Decimal("60.00")  # type: ignore[misc]


class TestPercentage:
    def test_valid_construction(self):
        assert Percentage(value=Decimal("50.00")).value == Decimal("50.00")

    def test_boundary_zero_is_valid(self):
        Percentage(value=Decimal("0"))

    def test_boundary_hundred_is_valid(self):
        Percentage(value=Decimal("100"))

    def test_rejects_negative(self):
        with pytest.raises(ValidationFailed):
            Percentage(value=Decimal("-1"))

    def test_rejects_above_hundred(self):
        with pytest.raises(ValidationFailed):
            Percentage(value=Decimal("100.01"))

    def test_as_fraction(self):
        assert Percentage(value=Decimal("25")).as_fraction() == Decimal("0.25")

    def test_apply_to_money(self):
        result = Percentage(value=Decimal("10")).apply_to(Money(amount=Decimal("200.00"), currency="UZS"))
        assert result.amount == Decimal("20.00")

    def test_immutability(self):
        pct = Percentage(value=Decimal("10"))
        with pytest.raises(Exception):
            pct.value = Decimal("20")  # type: ignore[misc]


class TestDiscountValue:
    def test_percentage_type_requires_percentage(self):
        with pytest.raises(ValidationFailed):
            DiscountValue(value_type="percentage")

    def test_fixed_amount_type_requires_fixed_amount(self):
        with pytest.raises(ValidationFailed):
            DiscountValue(value_type="fixed_amount")

    def test_valid_percentage_discount(self):
        DiscountValue(value_type="percentage", percentage=Percentage(value=Decimal("15")))

    def test_valid_fixed_amount_discount(self):
        DiscountValue(value_type="fixed_amount", fixed_amount=Money(amount=Decimal("10.00"), currency="UZS"))

    def test_apply_percentage_to_price(self):
        discount = DiscountValue(value_type="percentage", percentage=Percentage(value=Decimal("20")))
        result = discount.apply_to(Money(amount=Decimal("100.00"), currency="UZS"))
        assert result.amount == Decimal("80.00")

    def test_apply_fixed_amount_to_price(self):
        discount = DiscountValue(value_type="fixed_amount", fixed_amount=Money(amount=Decimal("30.00"), currency="UZS"))
        result = discount.apply_to(Money(amount=Decimal("100.00"), currency="UZS"))
        assert result.amount == Decimal("70.00")

    def test_apply_floors_at_zero_never_negative(self):
        discount = DiscountValue(value_type="fixed_amount", fixed_amount=Money(amount=Decimal("150.00"), currency="UZS"))
        result = discount.apply_to(Money(amount=Decimal("100.00"), currency="UZS"))
        assert result.amount == Decimal("0.00")


class TestMarginPercentage:
    def test_construction(self):
        assert MarginPercentage(value=Decimal("25.50")).value == Decimal("25.50")

    def test_can_represent_negative_margin(self):
        """Unlike Percentage, MarginPercentage has no 0-100 bound -- a loss-leader price legitimately produces a negative margin."""
        assert MarginPercentage(value=Decimal("-10.00")).value == Decimal("-10.00")


class TestTaxRate:
    def test_exclusive_mode_adds_tax(self):
        tax = TaxRate(rate=Percentage(value=Decimal("15")), mode="exclusive")
        result = tax.apply_to(Money(amount=Decimal("100.00"), currency="UZS"))
        assert result.amount == Decimal("115.00")

    def test_inclusive_mode_leaves_price_unchanged(self):
        tax = TaxRate(rate=Percentage(value=Decimal("15")), mode="inclusive")
        result = tax.apply_to(Money(amount=Decimal("100.00"), currency="UZS"))
        assert result.amount == Decimal("100.00")


class TestPriceValidityPeriod:
    def test_valid_construction(self):
        PriceValidityPeriod(starts_at=datetime(2026, 1, 1), ends_at=datetime(2026, 6, 1))

    def test_open_ended_is_valid(self):
        PriceValidityPeriod(starts_at=datetime(2026, 1, 1))

    def test_rejects_ends_before_starts(self):
        with pytest.raises(ValidationFailed):
            PriceValidityPeriod(starts_at=datetime(2026, 6, 1), ends_at=datetime(2026, 1, 1))

    def test_rejects_ends_equal_starts(self):
        moment = datetime(2026, 1, 1)
        with pytest.raises(ValidationFailed):
            PriceValidityPeriod(starts_at=moment, ends_at=moment)

    def test_is_active_at_within_window(self):
        period = PriceValidityPeriod(starts_at=datetime(2026, 1, 1), ends_at=datetime(2026, 6, 1))
        assert period.is_active_at(datetime(2026, 3, 1)) is True

    def test_is_active_at_before_window(self):
        period = PriceValidityPeriod(starts_at=datetime(2026, 1, 1), ends_at=datetime(2026, 6, 1))
        assert period.is_active_at(datetime(2025, 12, 31)) is False

    def test_is_active_at_boundary_end_is_exclusive(self):
        period = PriceValidityPeriod(starts_at=datetime(2026, 1, 1), ends_at=datetime(2026, 6, 1))
        assert period.is_active_at(datetime(2026, 6, 1)) is False

    def test_is_active_open_ended_never_expires(self):
        period = PriceValidityPeriod(starts_at=datetime(2026, 1, 1))
        assert period.is_active_at(datetime(2099, 1, 1)) is True


class TestQuantityTier:
    def test_valid_construction(self):
        tier = QuantityTier(minimum_quantity=10, discount=DiscountValue(value_type="percentage", percentage=Percentage(value=Decimal("5"))))
        assert tier.minimum_quantity == 10

    def test_rejects_zero_minimum(self):
        with pytest.raises(ValidationFailed):
            QuantityTier(minimum_quantity=0, discount=DiscountValue(value_type="percentage", percentage=Percentage(value=Decimal("5"))))


class TestPriceSnapshotToken:
    def test_string_representation(self):
        token_id = uuid.uuid4()
        assert str(PriceSnapshotToken(token_id)) == str(token_id)


class TestCodeValueObjects:
    def test_price_list_code_valid(self):
        assert PriceListCode("DEFAULT-UZS").value == "DEFAULT-UZS"

    def test_price_list_code_rejects_lowercase(self):
        with pytest.raises(ValidationFailed):
            PriceListCode("default-uzs")

    def test_coupon_code_valid(self):
        assert CouponCode("SAVE20NOW").value == "SAVE20NOW"

    def test_coupon_code_rejects_too_short(self):
        with pytest.raises(ValidationFailed):
            CouponCode("AB")

    def test_region_code_valid_country_only(self):
        assert RegionCode("UZ").value == "UZ"

    def test_region_code_valid_with_subregion(self):
        assert RegionCode("UZ-TASH").value == "UZ-TASH"

    def test_region_code_rejects_invalid_format(self):
        with pytest.raises(ValidationFailed):
            RegionCode("uzbekistan")
