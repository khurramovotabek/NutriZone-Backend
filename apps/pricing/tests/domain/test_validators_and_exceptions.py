from __future__ import annotations

from decimal import Decimal

import pytest

from apps.pricing.domain import exceptions as exc
from apps.pricing.domain.validators import (
    CouponCodeValidator,
    DiscountPercentageValidator,
    MarginValidator,
    PriceListValidator,
    PriceValidator,
    RegionValidator,
    ValidityPeriodValidator,
)
from apps.pricing.domain.value_objects import Money
from common.exceptions import DomainException, ValidationFailed

pytestmark = pytest.mark.unit


def test_price_list_validator():
    code, name = PriceListValidator("DEFAULT-UZS", "Default")
    assert code.value == "DEFAULT-UZS"


def test_price_list_validator_rejects_empty_name():
    with pytest.raises(ValidationFailed):
        PriceListValidator("DEFAULT-UZS", "")


def test_price_validator():
    money = PriceValidator(Decimal("50.00"), "UZS")
    assert money.amount == Decimal("50.00")


def test_discount_percentage_validator():
    assert DiscountPercentageValidator(Decimal("15")).value == Decimal("15")


def test_discount_percentage_validator_rejects_out_of_range():
    with pytest.raises(ValidationFailed):
        DiscountPercentageValidator(Decimal("150"))


def test_coupon_code_validator():
    assert CouponCodeValidator("SAVE20NOW").value == "SAVE20NOW"


def test_region_validator():
    assert RegionValidator("UZ").value == "UZ"


def test_margin_validator_passes_for_healthy_margin():
    MarginValidator(Money(amount=Decimal("60.00"), currency="UZS"), Money(amount=Decimal("100.00"), currency="UZS"))


def test_margin_validator_raises_for_loss():
    with pytest.raises(exc.NegativeMargin):
        MarginValidator(Money(amount=Decimal("120.00"), currency="UZS"), Money(amount=Decimal("100.00"), currency="UZS"))


def test_validity_period_validator():
    import datetime

    period = ValidityPeriodValidator(datetime.datetime(2026, 1, 1), datetime.datetime(2026, 6, 1))
    assert period.starts_at == datetime.datetime(2026, 1, 1)


@pytest.mark.parametrize(
    "exception_cls",
    [
        exc.InvalidPriceConfiguration, exc.DuplicatePriceListEntry, exc.DuplicateCouponCode, exc.CouponExpired,
        exc.CouponExhausted, exc.CouponNotActive, exc.CampaignNotActive, exc.CampaignSchedulingConflict,
        exc.InvalidDiscountStack, exc.PriceListArchived, exc.InvalidPriceListLifecycleTransition,
        exc.InvalidPricingRuleLifecycleTransition, exc.InvalidCampaignLifecycleTransition,
        exc.InvalidCouponLifecycleTransition, exc.PriceSnapshotExpired,
        exc.PriceSnapshotAlreadyConsumed, exc.NegativeMargin, exc.PricingEntityNotFound,
    ],
)
def test_every_exception_subclasses_domain_exception(exception_cls):
    assert issubclass(exception_cls, DomainException)
    instance = exception_cls("test message")
    assert instance.message == "test message"
    assert instance.code


def test_exception_count_matches_source_exactly():
    """A direct, self-verifying count -- if a new exception is added to domain/exceptions.py without a corresponding test above, this fails loudly rather than silently under-covering."""
    import inspect

    from apps.pricing.domain import exceptions as exceptions_module

    defined = [name for name, obj in inspect.getmembers(exceptions_module, inspect.isclass) if issubclass(obj, DomainException) and obj is not DomainException and obj.__module__ == exceptions_module.__name__]
    assert len(defined) == 18
