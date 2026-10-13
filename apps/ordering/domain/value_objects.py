"""
Ordering domain value objects.

`Money` is imported from the Shared Kernel (`shared.value_objects.
money`), never redefined. `AddressSnapshot` is a deliberate, frozen
COPY of address data at order time -- Order never references a live
`geo.Address` by ID for its shipping/billing address, because an
order's address must remain exactly what it was at checkout even if
the customer's saved address later changes or is deleted. This is
different from every other cross-module reference in this module
(which are ID-only) precisely because address correctness at a fixed
point in time is a real business requirement, not an implementation
convenience.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from shared.value_objects.money import Money  # noqa: F401 -- re-exported for convenience; Shared Kernel, not redefined
from common.exceptions import ValidationFailed

_ORDER_NUMBER_RE = re.compile(r"^ORD-[A-Z0-9]{6,20}$")
_TRACKING_NUMBER_RE = re.compile(r"^[A-Z0-9]{6,32}$")
_RETURN_NUMBER_RE = re.compile(r"^RET-[A-Z0-9]{6,20}$")


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


OrderNumber = _code_value_object("OrderNumber", _ORDER_NUMBER_RE, "ORD-A1B2C3")
TrackingNumber = _code_value_object("TrackingNumber", _TRACKING_NUMBER_RE, "1Z999AA10123456784")
ReturnNumber = _code_value_object("ReturnNumber", _RETURN_NUMBER_RE, "RET-A1B2C3")


@dataclass(frozen=True, slots=True)
class OrderVersion:
    """Optimistic-locking version counter -- incremented on every mutating Order operation, same rationale as `apps.cart.domain.value_objects.CartVersion`."""

    value: int

    def __post_init__(self) -> None:
        if self.value < 1:
            raise ValidationFailed("Order version must be at least 1.")

    def next(self) -> "OrderVersion":
        return OrderVersion(self.value + 1)


@dataclass(frozen=True, slots=True)
class OrderNote:
    text: str

    def __post_init__(self) -> None:
        if len(self.text) > 1000:
            raise ValidationFailed("Order note must not exceed 1000 characters.")


@dataclass(frozen=True, slots=True)
class CustomerComment:
    """Distinct from OrderNote -- a customer-authored comment on the order (e.g. left at checkout), vs. an internal operational note. Kept as separate types for the same 'never accidentally exposed as one another' reason as Cart's CartNote/GiftMessage."""

    text: str

    def __post_init__(self) -> None:
        if len(self.text) > 1000:
            raise ValidationFailed("Customer comment must not exceed 1000 characters.")


@dataclass(frozen=True, slots=True)
class AddressSnapshot:
    """A frozen, point-in-time copy of a shipping/billing address -- see module docstring for why this is a value object copy, not an ID reference to `geo.Address`."""

    recipient_name: str
    line1: str
    city: str
    country_code: str
    line2: str | None = None
    region: str | None = None
    postal_code: str | None = None
    phone: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    def __post_init__(self) -> None:
        if not self.recipient_name.strip():
            raise ValidationFailed("Address recipient_name must not be empty.")
        if not self.line1.strip():
            raise ValidationFailed("Address line1 must not be empty.")
        if not self.city.strip():
            raise ValidationFailed("Address city must not be empty.")
        if len(self.country_code) != 2 or not self.country_code.isupper():
            raise ValidationFailed("Address country_code must be a 2-letter uppercase ISO code.")
        if self.latitude is not None and not (-90.0 <= self.latitude <= 90.0):
            raise ValidationFailed("Address latitude must be between -90 and 90.")
        if self.longitude is not None and not (-180.0 <= self.longitude <= 180.0):
            raise ValidationFailed("Address longitude must be between -180 and 180.")


@dataclass(frozen=True, slots=True)
class OrderTotal:
    """The composite breakdown of an order's monetary total -- every component is Money, in the same currency as the order itself (enforced by `__post_init__`, not left to the caller to get right)."""

    subtotal: Money
    discount_total: Money
    tax_total: Money
    shipping_total: Money
    grand_total: Money

    def __post_init__(self) -> None:
        currencies = {self.subtotal.currency, self.discount_total.currency, self.tax_total.currency, self.shipping_total.currency, self.grand_total.currency}
        if len(currencies) > 1:
            raise ValidationFailed(f"All OrderTotal components must share one currency; found {sorted(currencies)}.")

    @staticmethod
    def compute(subtotal: Money, discount_total: Money, tax_total: Money, shipping_total: Money) -> "OrderTotal":
        grand = subtotal.amount - discount_total.amount + tax_total.amount + shipping_total.amount
        return OrderTotal(subtotal=subtotal, discount_total=discount_total, tax_total=tax_total, shipping_total=shipping_total, grand_total=Money(amount=grand, currency=subtotal.currency))


@dataclass(frozen=True, slots=True)
class ReturnWindow:
    """A duration (not an absolute timestamp) -- same shape/rationale as `apps.cart.domain.value_objects.ExpirationPeriod`: lets the policy compute an absolute return-eligibility deadline from whatever 'now' (here, delivery time) the caller supplies."""

    duration: timedelta

    def __post_init__(self) -> None:
        if self.duration.total_seconds() <= 0:
            raise ValidationFailed("Return window must be a positive duration.")

    def eligible_until(self, delivered_at: datetime) -> datetime:
        return delivered_at + self.duration

    def is_within_window(self, delivered_at: datetime, at: datetime) -> bool:
        return at <= self.eligible_until(delivered_at)


@dataclass(frozen=True, slots=True)
class DeliveryWindow:
    """A promised delivery time range, e.g. 'between Tuesday 9am and 1pm' -- distinct from EstimatedDelivery (a single best-guess point estimate)."""

    starts_at: datetime
    ends_at: datetime

    def __post_init__(self) -> None:
        if self.ends_at <= self.starts_at:
            raise ValidationFailed("DeliveryWindow ends_at must be after starts_at.")


@dataclass(frozen=True, slots=True)
class EstimatedDelivery:
    estimated_at: datetime
    is_final: bool = False
