"""
Cart domain value objects.

`Money` is imported from the Shared Kernel (`shared.value_objects.
money`), never redefined -- matching every prior module's practice.
`RegionCode`/`ChannelCode` are this module's own lightweight value
objects, not imports from `apps.geo.domain`/`apps.store.domain` -- the
same accepted, documented "small deliberate duplication over cross-
module coupling" principle established since Store's Phase 1.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from shared.value_objects.money import Money  # noqa: F401 -- re-exported for convenience; Shared Kernel, not redefined
from common.exceptions import ValidationFailed

_CART_CODE_RE = re.compile(r"^[A-Z0-9]{6,24}$")
_CURRENCY_CODE_RE = re.compile(r"^[A-Z]{3}$")
_REGION_CODE_RE = re.compile(r"^[A-Z]{2}(?:-[A-Z0-9]{1,8})?$")
_CHANNEL_CODE_RE = re.compile(r"^[a-z0-9_]{2,32}$")


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


CartCode = _code_value_object("CartCode", _CART_CODE_RE, "A1B2C3D4E5")
CurrencyCode = _code_value_object("CurrencyCode", _CURRENCY_CODE_RE, "UZS")
RegionCode = _code_value_object("RegionCode", _REGION_CODE_RE, "UZ or UZ-TASH")
ChannelCode = _code_value_object("ChannelCode", _CHANNEL_CODE_RE, "web_storefront")


@dataclass(frozen=True, slots=True)
class CartToken:
    """An opaque, unique access token for a guest cart -- what a browser/mobile client holds (e.g. in a cookie) to reference its cart without an authenticated identity."""

    value: uuid.UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class CartVersion:
    """Optimistic-locking version counter -- incremented on every mutating Cart operation."""

    value: int

    def __post_init__(self) -> None:
        if self.value < 1:
            raise ValidationFailed("Cart version must be at least 1.")

    def next(self) -> "CartVersion":
        return CartVersion(self.value + 1)


@dataclass(frozen=True, slots=True)
class Quantity:
    """A non-negative item quantity -- the single structural rule ('quantity can never be negative') enforced once, here."""

    value: int

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValidationFailed("Quantity must not be negative.", details={"fields": [{"field": "quantity", "code": "NEGATIVE"}]})

    def __add__(self, other: "Quantity") -> "Quantity":
        return Quantity(self.value + other.value)

    def is_zero(self) -> bool:
        return self.value == 0


@dataclass(frozen=True, slots=True)
class CartNote:
    text: str

    def __post_init__(self) -> None:
        if len(self.text) > 1000:
            raise ValidationFailed("Cart note must not exceed 1000 characters.", details={"fields": [{"field": "note", "code": "TOO_LONG"}]})


@dataclass(frozen=True, slots=True)
class GiftMessage:
    """Distinct from CartNote -- a gift message is customer-facing (printed on a packing slip), a note is internal/operational. Kept as separate types so a future serializer can never accidentally expose one as the other."""

    text: str

    def __post_init__(self) -> None:
        if len(self.text) > 500:
            raise ValidationFailed("Gift message must not exceed 500 characters.", details={"fields": [{"field": "gift_message", "code": "TOO_LONG"}]})


@dataclass(frozen=True, slots=True)
class EstimatedAmount:
    """Wraps a Money estimate with an explicit 'is this final or provisional' flag -- backs Shipping/Tax Estimate References, which are always provisional until a later module (Ordering) confirms them."""

    amount: Money
    is_final: bool = False


@dataclass(frozen=True, slots=True)
class ExpirationPeriod:
    """A duration (not an absolute timestamp) -- backs 'Cart Expiration' by letting the policy/service compute an absolute expiry from whatever 'now' the caller supplies, rather than baking in a clock dependency."""

    duration: timedelta

    def __post_init__(self) -> None:
        if self.duration.total_seconds() <= 0:
            raise ValidationFailed("Expiration period must be a positive duration.")

    def expires_from(self, reference: datetime) -> datetime:
        return reference + self.duration


@dataclass(frozen=True, slots=True)
class SnapshotToken:
    """An opaque reference for one Cart Snapshot -- same shape/rationale as `apps.pricing.domain.value_objects.PriceSnapshotToken`."""

    value: uuid.UUID

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class MergeResult:
    """Summarizes the outcome of a guest-cart-into-authenticated-cart merge -- returned by `Cart.merge_guest_cart()` so the caller (and any UI) can report exactly what happened, not just that it succeeded."""

    items_merged: int
    items_replaced: int
    items_skipped: int
    strategy_used: str  # MergeStrategy.value
