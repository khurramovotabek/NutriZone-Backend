from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from apps.cart.domain.value_objects import (
    CartCode,
    CartNote,
    CartToken,
    CartVersion,
    ChannelCode,
    CurrencyCode,
    EstimatedAmount,
    ExpirationPeriod,
    GiftMessage,
    MergeResult,
    Money,
    Quantity,
    RegionCode,
    SnapshotToken,
)
from common.exceptions import ValidationFailed

pytestmark = pytest.mark.unit


class TestMoney:
    """Money is the Shared Kernel re-export -- verified here for Cart's own usage, not re-testing its own module's suite."""

    def test_construction(self):
        assert Money(amount=Decimal("10.00"), currency="UZS").amount == Decimal("10.00")

    def test_equality(self):
        assert Money(amount=Decimal("5.00"), currency="UZS") == Money(amount=Decimal("5.00"), currency="UZS")

    def test_immutability(self):
        money = Money(amount=Decimal("5.00"), currency="UZS")
        with pytest.raises(Exception):
            money.amount = Decimal("6.00")  # type: ignore[misc]

    def test_hashable(self):
        """Money is a frozen dataclass -- must be hashable to be usable as a dict key/set member."""
        {Money(amount=Decimal("5.00"), currency="UZS")}


class TestQuantity:
    def test_valid_construction(self):
        assert Quantity(5).value == 5

    def test_zero_is_valid(self):
        assert Quantity(0).is_zero() is True

    def test_rejects_negative(self):
        with pytest.raises(ValidationFailed):
            Quantity(-1)

    def test_addition(self):
        assert (Quantity(2) + Quantity(3)).value == 5

    def test_equality(self):
        assert Quantity(4) == Quantity(4)

    def test_immutability(self):
        qty = Quantity(4)
        with pytest.raises(Exception):
            qty.value = 5  # type: ignore[misc]

    def test_hashable(self):
        {Quantity(1), Quantity(2)}


class TestCartCode:
    def test_valid_construction(self):
        assert CartCode("A1B2C3D4E5").value == "A1B2C3D4E5"

    def test_rejects_lowercase(self):
        with pytest.raises(ValidationFailed):
            CartCode("a1b2c3")

    def test_rejects_too_short(self):
        with pytest.raises(ValidationFailed):
            CartCode("AB")

    def test_string_conversion(self):
        assert str(CartCode("A1B2C3D4E5")) == "A1B2C3D4E5"

    def test_equality(self):
        assert CartCode("A1B2C3D4E5") == CartCode("A1B2C3D4E5")


class TestCartToken:
    def test_construction(self):
        token_id = uuid.uuid4()
        assert CartToken(token_id).value == token_id

    def test_string_conversion(self):
        token_id = uuid.uuid4()
        assert str(CartToken(token_id)) == str(token_id)

    def test_equality(self):
        token_id = uuid.uuid4()
        assert CartToken(token_id) == CartToken(token_id)


class TestCartVersion:
    def test_valid_construction(self):
        assert CartVersion(1).value == 1

    def test_rejects_zero(self):
        with pytest.raises(ValidationFailed):
            CartVersion(0)

    def test_next_increments(self):
        assert CartVersion(1).next().value == 2

    def test_next_does_not_mutate_original(self):
        """Immutability check via behavior: calling .next() must not change the original instance."""
        original = CartVersion(1)
        original.next()
        assert original.value == 1


class TestCurrencyRegionChannelCodes:
    def test_currency_code_valid(self):
        assert CurrencyCode("UZS").value == "UZS"

    def test_currency_code_rejects_wrong_length(self):
        with pytest.raises(ValidationFailed):
            CurrencyCode("US")

    def test_region_code_valid_country_only(self):
        assert RegionCode("UZ").value == "UZ"

    def test_region_code_valid_with_subregion(self):
        assert RegionCode("UZ-TASH").value == "UZ-TASH"

    def test_channel_code_valid(self):
        assert ChannelCode("web_storefront").value == "web_storefront"

    def test_channel_code_rejects_uppercase(self):
        with pytest.raises(ValidationFailed):
            ChannelCode("WEB_STOREFRONT")


class TestCartNoteAndGiftMessage:
    """Distinct types -- verified here that they remain independently constructible/validated, per Phase 1's explicit 'never accidentally exposed as one another' design intent."""

    def test_cart_note_valid(self):
        assert CartNote("Please deliver after 6pm").text == "Please deliver after 6pm"

    def test_cart_note_rejects_too_long(self):
        with pytest.raises(ValidationFailed):
            CartNote("x" * 1001)

    def test_cart_note_boundary_length_valid(self):
        CartNote("x" * 1000)

    def test_gift_message_valid(self):
        assert GiftMessage("Happy Birthday!").text == "Happy Birthday!"

    def test_gift_message_rejects_too_long(self):
        with pytest.raises(ValidationFailed):
            GiftMessage("x" * 501)

    def test_gift_message_boundary_length_valid(self):
        GiftMessage("x" * 500)

    def test_note_and_gift_message_are_distinct_types(self):
        assert CartNote is not GiftMessage
        assert type(CartNote("x")) is not type(GiftMessage("x"))


class TestEstimatedAmount:
    def test_construction_defaults_not_final(self):
        estimate = EstimatedAmount(amount=Money(amount=Decimal("10.00"), currency="UZS"))
        assert estimate.is_final is False

    def test_construction_explicit_final(self):
        estimate = EstimatedAmount(amount=Money(amount=Decimal("10.00"), currency="UZS"), is_final=True)
        assert estimate.is_final is True


class TestExpirationPeriod:
    def test_valid_construction(self):
        ExpirationPeriod(timedelta(days=7))

    def test_rejects_non_positive_duration(self):
        with pytest.raises(ValidationFailed):
            ExpirationPeriod(timedelta(seconds=0))

    def test_rejects_negative_duration(self):
        with pytest.raises(ValidationFailed):
            ExpirationPeriod(timedelta(seconds=-1))

    def test_expires_from_computes_absolute_time(self):
        reference = datetime(2026, 1, 1)
        period = ExpirationPeriod(timedelta(days=7))
        assert period.expires_from(reference) == datetime(2026, 1, 8)


class TestSnapshotToken:
    def test_string_conversion(self):
        token_id = uuid.uuid4()
        assert str(SnapshotToken(token_id)) == str(token_id)


class TestMergeResult:
    def test_construction(self):
        result = MergeResult(items_merged=2, items_replaced=0, items_skipped=1, strategy_used="sum_quantities")
        assert result.items_merged == 2

    def test_immutability(self):
        result = MergeResult(items_merged=2, items_replaced=0, items_skipped=1, strategy_used="sum_quantities")
        with pytest.raises(Exception):
            result.items_merged = 5  # type: ignore[misc]
