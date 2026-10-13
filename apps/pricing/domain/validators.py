"""
Pricing domain (business) validators -- thin, intention-revealing
wrappers over the value objects' own constructor validation, matching
the pattern established by every prior module's domain/validators.py.
"""
from __future__ import annotations

from decimal import Decimal

from apps.pricing.domain.value_objects import CouponCode, Money, Percentage, PriceListCode, RegionCode


def PriceListValidator(code: str, name: str) -> tuple[PriceListCode, str]:  # noqa: N802
    from common.exceptions import ValidationFailed

    if not name or not name.strip():
        raise ValidationFailed("Price list name must not be empty.")
    return PriceListCode(code), name


def PriceValidator(amount: Decimal, currency: str) -> Money:  # noqa: N802
    return Money(amount=amount, currency=currency)


def DiscountPercentageValidator(value: Decimal) -> Percentage:  # noqa: N802
    return Percentage(value=value)


def CouponCodeValidator(code: str) -> CouponCode:  # noqa: N802
    return CouponCode(code)


def RegionValidator(code: str) -> RegionCode:  # noqa: N802
    return RegionCode(code)


def MarginValidator(cost_price: Money, sale_price: Money, allow_loss_leader: bool = False) -> None:  # noqa: N802
    from apps.pricing.domain.services import MarginCalculator

    MarginCalculator.assert_non_negative_margin(cost_price, sale_price, allow_loss_leader=allow_loss_leader)


def ValidityPeriodValidator(starts_at, ends_at=None):  # noqa: N802
    from apps.pricing.domain.value_objects import PriceValidityPeriod

    return PriceValidityPeriod(starts_at=starts_at, ends_at=ends_at)
