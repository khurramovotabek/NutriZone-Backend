"""
Pricing domain value objects.

`Money` is imported from the Shared Kernel (`shared.value_objects.
money`), never redefined -- Domain Architecture Specification §5
approves exactly two Shared Kernel items, and Money is one of them,
explicitly anticipated for Pricing's use (see `common/utils/money.py`'s
own docstring). Every other value object here is this module's own,
following the same "small, deliberate duplication over cross-module
coupling" principle already established by every prior module (e.g.
`apps.store.domain.value_objects.GeoCoordinate` vs. `apps.geo`'s own).
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from shared.value_objects.money import DEFAULT_CURRENCY, Money  # noqa: F401 -- re-exported for convenience; Shared Kernel, not redefined
from common.exceptions import ValidationFailed

_PRICE_LIST_CODE_RE = re.compile(r"^[A-Z0-9]{2,20}(?:-[A-Z0-9]{2,20})*$")
_COUPON_CODE_RE = re.compile(r"^[A-Z0-9]{4,24}$")
_REGION_CODE_RE = re.compile(r"^[A-Z]{2}(?:-[A-Z0-9]{1,8})?$")


def _code_value_object(name: str, pattern: re.Pattern, example: str):
    @dataclass(frozen=True, slots=True)
    class _Code:
        value: str

        def __post_init__(self) -> None:
            if not pattern.match(self.value):
                raise ValidationFailed(f"{name} must match the format '{example}'.", details={"fields": [{"field": name.lower().replace(' ', '_'), "code": "INVALID_FORMAT"}]})

        def __str__(self) -> str:
            return self.value

    _Code.__name__ = name.replace(" ", "")
    _Code.__qualname__ = _Code.__name__
    return _Code


PriceListCode = _code_value_object("PriceListCode", _PRICE_LIST_CODE_RE, "DEFAULT-UZS")
CouponCode = _code_value_object("CouponCode", _COUPON_CODE_RE, "SAVE20NOW")
RegionCode = _code_value_object("RegionCode", _REGION_CODE_RE, "UZ or UZ-TASH")


@dataclass(frozen=True, slots=True)
class Percentage:
    """A 0-100 percentage, stored as Decimal for exact arithmetic (never float) -- backs discount percentages, margin percentages, and tax rates alike."""

    value: Decimal

    def __post_init__(self) -> None:
        if self.value < 0 or self.value > 100:
            raise ValidationFailed("Percentage must be between 0 and 100.", details={"fields": [{"field": "percentage", "code": "OUT_OF_RANGE"}]})

    def as_fraction(self) -> Decimal:
        return self.value / Decimal(100)

    def apply_to(self, money: Money) -> Money:
        return Money(amount=(money.amount * self.as_fraction()).quantize(Decimal("0.01")), currency=money.currency)


@dataclass(frozen=True, slots=True)
class DiscountValue:
    """A discount expressed as either a percentage or a fixed amount -- exactly one of `percentage`/`fixed_amount` is populated, matching its declared `value_type`."""

    value_type: str  # DiscountValueType.value
    percentage: Percentage | None = None
    fixed_amount: Money | None = None

    def __post_init__(self) -> None:
        from apps.pricing.domain.enums import DiscountValueType

        if self.value_type == DiscountValueType.PERCENTAGE.value and self.percentage is None:
            raise ValidationFailed("A PERCENTAGE discount requires a percentage value.")
        if self.value_type == DiscountValueType.FIXED_AMOUNT.value and self.fixed_amount is None:
            raise ValidationFailed("A FIXED_AMOUNT discount requires a fixed_amount value.")

    def apply_to(self, price: Money) -> Money:
        from apps.pricing.domain.enums import DiscountValueType

        if self.value_type == DiscountValueType.PERCENTAGE.value:
            discount_amount = self.percentage.apply_to(price)
        else:
            discount_amount = self.fixed_amount
        remaining = price.amount - discount_amount.amount
        floored = remaining if remaining > 0 else Decimal("0.00")
        return Money(amount=floored, currency=price.currency)


@dataclass(frozen=True, slots=True)
class MarginPercentage:
    """Read-only, computed -- never constructed directly by a caller other than `domain/services.py::MarginCalculator`."""

    value: Decimal


@dataclass(frozen=True, slots=True)
class TaxRate:
    rate: Percentage
    mode: str  # TaxMode.value

    def apply_to(self, price: Money) -> Money:
        from apps.pricing.domain.enums import TaxMode

        if self.mode == TaxMode.EXCLUSIVE.value:
            tax_amount = self.rate.apply_to(price)
            return Money(amount=price.amount + tax_amount.amount, currency=price.currency)
        return price  # INCLUSIVE: the tax is already baked into the given price; nothing to add


@dataclass(frozen=True, slots=True)
class PriceValidityPeriod:
    """Backs Time-based Pricing / Scheduled Price Changes / Campaign windows."""

    starts_at: datetime
    ends_at: datetime | None = None  # None means open-ended

    def __post_init__(self) -> None:
        if self.ends_at is not None and self.ends_at <= self.starts_at:
            raise ValidationFailed("ends_at must be after starts_at.", details={"fields": [{"field": "ends_at", "code": "BEFORE_START"}]})

    def is_active_at(self, at: datetime) -> bool:
        if at < self.starts_at:
            return False
        return self.ends_at is None or at < self.ends_at


@dataclass(frozen=True, slots=True)
class QuantityTier:
    """One break-point of a Quantity Discount schedule -- 'buy N+ units, get this discount'."""

    minimum_quantity: int
    discount: DiscountValue

    def __post_init__(self) -> None:
        if self.minimum_quantity < 1:
            raise ValidationFailed("minimum_quantity must be at least 1.")


@dataclass(frozen=True, slots=True)
class PriceSnapshotToken:
    """An opaque, unique reference for one Price Lock/Snapshot -- what a caller (e.g. a future Cart module) holds onto to redeem a locked price later."""

    value: uuid.UUID

    def __str__(self) -> str:
        return str(self.value)
