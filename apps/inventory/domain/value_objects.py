"""
Inventory domain value objects.

`ShelfCoordinate`/`BinCoordinate` are this module's own lightweight
location references, not imports from `apps.store.domain` -- the same
modular-monolith isolation rule already documented in `apps.store.
domain.value_objects`'s module docstring (Store's own `GeoCoordinate`/
`Timezone` vs. Geo's). `InventoryLocation` composes them with a
warehouse/shelf ID reference (by ID only, per the platform-wide
cross-module reference rule).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from common.exceptions import ValidationFailed

_INVENTORY_CODE_RE = re.compile(r"^[A-Z0-9]{3,20}$")
_BATCH_NUMBER_RE = re.compile(r"^[A-Z0-9]{3,32}(?:-[A-Z0-9]{1,16})*$")
_LOT_NUMBER_RE = re.compile(r"^[A-Z0-9]{3,32}$")
_SERIAL_NUMBER_RE = re.compile(r"^[A-Za-z0-9]{4,64}$")
_RESERVATION_NUMBER_RE = re.compile(r"^RSV-[A-Z0-9]{6,20}$")
_MOVEMENT_REFERENCE_RE = re.compile(r"^[A-Z]{2,6}-[A-Z0-9]{4,24}$")


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


InventoryCode = _code_value_object("InventoryCode", _INVENTORY_CODE_RE, "WHEY2KG001")
BatchNumber = _code_value_object("BatchNumber", _BATCH_NUMBER_RE, "BATCH-2026-001")
LotNumber = _code_value_object("LotNumber", _LOT_NUMBER_RE, "LOT20260101")
SerialNumber = _code_value_object("SerialNumber", _SERIAL_NUMBER_RE, "SN00012345")
ReservationNumber = _code_value_object("ReservationNumber", _RESERVATION_NUMBER_RE, "RSV-ABC123")
MovementReference = _code_value_object("MovementReference", _MOVEMENT_REFERENCE_RE, "PO-2026001")


@dataclass(frozen=True, slots=True)
class StockQuantity:
    """A non-negative quantity -- the single structural rule ('stock can never become negative') enforced once, here, rather than re-checked ad hoc at every call site that handles a quantity."""

    value: int

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValidationFailed("Stock quantity must not be negative.", details={"fields": [{"field": "quantity", "code": "NEGATIVE"}]})

    def __add__(self, other: "StockQuantity") -> "StockQuantity":
        return StockQuantity(self.value + other.value)

    def __sub__(self, other: "StockQuantity") -> "StockQuantity":
        return StockQuantity(self.value - other.value)  # raises ValidationFailed via __post_init__ if it would go negative

    def __ge__(self, other: "StockQuantity") -> bool:
        return self.value >= other.value

    def __gt__(self, other: "StockQuantity") -> bool:
        return self.value > other.value

    def is_zero(self) -> bool:
        return self.value == 0


@dataclass(frozen=True, slots=True)
class ReservedQuantity:
    """Distinct type from StockQuantity so a call site can't accidentally pass a raw available-stock figure where a reservation figure is expected -- the type system enforces the distinction MIC §6 asks domain rules to enforce."""

    value: int

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValidationFailed("Reserved quantity must not be negative.")


@dataclass(frozen=True, slots=True)
class AvailableQuantity:
    value: int

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValidationFailed("Available quantity must not be negative.")


@dataclass(frozen=True, slots=True)
class ExpirationDate:
    value: date

    def is_expired(self, as_of: date) -> bool:
        return as_of >= self.value


@dataclass(frozen=True, slots=True)
class ManufactureDate:
    value: date


@dataclass(frozen=True, slots=True)
class ShelfCoordinate:
    """This module's own lightweight shelf reference -- see module docstring."""

    aisle: str
    shelf: str

    def __post_init__(self) -> None:
        if not self.aisle or not self.shelf:
            raise ValidationFailed("Both aisle and shelf must be provided.")


@dataclass(frozen=True, slots=True)
class BinCoordinate:
    aisle: str
    shelf: str
    bin: str

    def __post_init__(self) -> None:
        if not self.aisle or not self.shelf or not self.bin:
            raise ValidationFailed("Aisle, shelf, and bin must all be provided.")


@dataclass(frozen=True, slots=True)
class InventoryLocation:
    """Composes a cross-module warehouse/shelf ID reference with an optional precise coordinate -- the ID is the source of truth for 'which warehouse/shelf', the coordinate is descriptive detail for physical pick/put-away workflows."""

    warehouse_id: object  # uuid.UUID, kept loosely typed to avoid importing uuid at module scope redundantly
    shelf_id: object | None = None
    coordinate: BinCoordinate | None = None


@dataclass(frozen=True, slots=True)
class StockThreshold:
    """Reorder-point configuration -- `low_stock_at` triggers InventoryHealthStatus.LOW_STOCK, `reorder_at` is the actionable trigger point, `overstock_at` flags excess inventory."""

    low_stock_at: int
    reorder_at: int
    overstock_at: int | None = None

    def __post_init__(self) -> None:
        if self.low_stock_at < 0 or self.reorder_at < 0:
            raise ValidationFailed("Stock thresholds must not be negative.")
        if self.reorder_at > self.low_stock_at:
            raise ValidationFailed("reorder_at must not exceed low_stock_at (reorder should trigger at or before the low-stock warning).")
        if self.overstock_at is not None and self.overstock_at <= self.low_stock_at:
            raise ValidationFailed("overstock_at must be greater than low_stock_at.")


@dataclass(frozen=True, slots=True)
class SnapshotVersion:
    value: int

    def __post_init__(self) -> None:
        if self.value < 1:
            raise ValidationFailed("Snapshot version must be at least 1.")

    def next(self) -> "SnapshotVersion":
        return SnapshotVersion(self.value + 1)
