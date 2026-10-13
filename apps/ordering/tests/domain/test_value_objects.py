from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from apps.ordering.domain.value_objects import (
    AddressSnapshot,
    CustomerComment,
    DeliveryWindow,
    EstimatedDelivery,
    Money,
    OrderNote,
    OrderNumber,
    OrderTotal,
    OrderVersion,
    ReturnNumber,
    ReturnWindow,
    TrackingNumber,
)
from common.exceptions import ValidationFailed

pytestmark = pytest.mark.unit


class TestMoney:
    def test_construction(self):
        assert Money(amount=Decimal("10.00"), currency="UZS").amount == Decimal("10.00")

    def test_equality(self):
        assert Money(amount=Decimal("5.00"), currency="UZS") == Money(amount=Decimal("5.00"), currency="UZS")

    def test_immutability(self):
        money = Money(amount=Decimal("5.00"), currency="UZS")
        with pytest.raises(Exception):
            money.amount = Decimal("6.00")  # type: ignore[misc]

    def test_hashable(self):
        {Money(amount=Decimal("5.00"), currency="UZS")}


class TestOrderNumber:
    def test_valid_construction(self):
        assert OrderNumber("ORD-A1B2C3").value == "ORD-A1B2C3"

    def test_rejects_missing_prefix(self):
        with pytest.raises(ValidationFailed):
            OrderNumber("A1B2C3")

    def test_rejects_lowercase(self):
        with pytest.raises(ValidationFailed):
            OrderNumber("ord-a1b2c3")

    def test_string_conversion(self):
        assert str(OrderNumber("ORD-A1B2C3")) == "ORD-A1B2C3"

    def test_equality(self):
        assert OrderNumber("ORD-A1B2C3") == OrderNumber("ORD-A1B2C3")

    def test_hashable(self):
        {OrderNumber("ORD-A1B2C3")}


class TestTrackingNumber:
    def test_valid_construction(self):
        assert TrackingNumber("1Z999AA10123456784").value == "1Z999AA10123456784"

    def test_rejects_too_short(self):
        with pytest.raises(ValidationFailed):
            TrackingNumber("AB")


class TestReturnNumber:
    def test_valid_construction(self):
        assert ReturnNumber("RET-A1B2C3").value == "RET-A1B2C3"

    def test_rejects_wrong_prefix(self):
        with pytest.raises(ValidationFailed):
            ReturnNumber("ORD-A1B2C3")


class TestOrderVersion:
    def test_valid_construction(self):
        assert OrderVersion(1).value == 1

    def test_rejects_zero(self):
        with pytest.raises(ValidationFailed):
            OrderVersion(0)

    def test_next_increments(self):
        assert OrderVersion(1).next().value == 2

    def test_next_does_not_mutate_original(self):
        original = OrderVersion(1)
        original.next()
        assert original.value == 1


class TestOrderNoteAndCustomerComment:
    def test_order_note_valid(self):
        assert OrderNote("Handle with care").text == "Handle with care"

    def test_order_note_rejects_too_long(self):
        with pytest.raises(ValidationFailed):
            OrderNote("x" * 1001)

    def test_customer_comment_valid(self):
        assert CustomerComment("Please deliver quickly").text == "Please deliver quickly"

    def test_customer_comment_rejects_too_long(self):
        with pytest.raises(ValidationFailed):
            CustomerComment("x" * 1001)

    def test_distinct_types(self):
        assert OrderNote is not CustomerComment
        assert type(OrderNote("x")) is not type(CustomerComment("x"))


class TestAddressSnapshot:
    def test_valid_construction(self):
        addr = AddressSnapshot(recipient_name="Jane Doe", line1="123 Main St", city="Tashkent", country_code="UZ")
        assert addr.city == "Tashkent"

    def test_rejects_empty_recipient_name(self):
        with pytest.raises(ValidationFailed):
            AddressSnapshot(recipient_name="", line1="123 Main St", city="Tashkent", country_code="UZ")

    def test_rejects_empty_line1(self):
        with pytest.raises(ValidationFailed):
            AddressSnapshot(recipient_name="Jane Doe", line1="", city="Tashkent", country_code="UZ")

    def test_rejects_empty_city(self):
        with pytest.raises(ValidationFailed):
            AddressSnapshot(recipient_name="Jane Doe", line1="123 Main St", city="", country_code="UZ")

    def test_rejects_lowercase_country_code(self):
        with pytest.raises(ValidationFailed):
            AddressSnapshot(recipient_name="Jane Doe", line1="123 Main St", city="Tashkent", country_code="uz")

    def test_rejects_wrong_length_country_code(self):
        with pytest.raises(ValidationFailed):
            AddressSnapshot(recipient_name="Jane Doe", line1="123 Main St", city="Tashkent", country_code="UZB")

    def test_optional_fields_default_none(self):
        addr = AddressSnapshot(recipient_name="Jane Doe", line1="123 Main St", city="Tashkent", country_code="UZ")
        assert addr.line2 is None
        assert addr.region is None


class TestOrderTotal:
    def test_compute_produces_correct_grand_total(self):
        total = OrderTotal.compute(
            subtotal=Money(amount=Decimal("100.00"), currency="UZS"), discount_total=Money(amount=Decimal("10.00"), currency="UZS"),
            tax_total=Money(amount=Decimal("5.00"), currency="UZS"), shipping_total=Money(amount=Decimal("15.00"), currency="UZS"),
        )
        assert total.grand_total.amount == Decimal("110.00")

    def test_rejects_mismatched_currencies(self):
        with pytest.raises(ValidationFailed):
            OrderTotal(
                subtotal=Money(amount=Decimal("100.00"), currency="UZS"), discount_total=Money(amount=Decimal("0.00"), currency="USD"),
                tax_total=Money(amount=Decimal("0.00"), currency="UZS"), shipping_total=Money(amount=Decimal("0.00"), currency="UZS"),
                grand_total=Money(amount=Decimal("100.00"), currency="UZS"),
            )


class TestReturnWindow:
    def test_valid_construction(self):
        ReturnWindow(timedelta(days=14))

    def test_rejects_non_positive_duration(self):
        with pytest.raises(ValidationFailed):
            ReturnWindow(timedelta(seconds=0))

    def test_eligible_until_computes_correctly(self):
        window = ReturnWindow(timedelta(days=14))
        delivered = datetime(2026, 1, 1)
        assert window.eligible_until(delivered) == datetime(2026, 1, 15)

    def test_is_within_window_true(self):
        window = ReturnWindow(timedelta(days=14))
        assert window.is_within_window(datetime(2026, 1, 1), datetime(2026, 1, 10)) is True

    def test_is_within_window_false_after_expiry(self):
        window = ReturnWindow(timedelta(days=14))
        assert window.is_within_window(datetime(2026, 1, 1), datetime(2026, 2, 1)) is False


class TestDeliveryWindow:
    def test_valid_construction(self):
        DeliveryWindow(starts_at=datetime(2026, 1, 1, 9), ends_at=datetime(2026, 1, 1, 13))

    def test_rejects_ends_before_starts(self):
        with pytest.raises(ValidationFailed):
            DeliveryWindow(starts_at=datetime(2026, 1, 1, 13), ends_at=datetime(2026, 1, 1, 9))

    def test_rejects_ends_equal_starts(self):
        moment = datetime(2026, 1, 1, 9)
        with pytest.raises(ValidationFailed):
            DeliveryWindow(starts_at=moment, ends_at=moment)


class TestEstimatedDelivery:
    def test_defaults_not_final(self):
        est = EstimatedDelivery(estimated_at=datetime(2026, 1, 1))
        assert est.is_final is False

    def test_explicit_final(self):
        est = EstimatedDelivery(estimated_at=datetime(2026, 1, 1), is_final=True)
        assert est.is_final is True
