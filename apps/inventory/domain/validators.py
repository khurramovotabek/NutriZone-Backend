"""
Inventory domain (business) validators -- thin, intention-revealing
wrappers over the value objects' own constructor validation, matching
the pattern established by every prior module's domain/validators.py.
"""
from __future__ import annotations

from apps.inventory.domain.value_objects import (
    BatchNumber,
    ExpirationDate,
    InventoryCode,
    ManufactureDate,
    ReservationNumber,
    SerialNumber,
    StockQuantity,
    StockThreshold,
)


def InventoryValidator(code: str) -> InventoryCode:  # noqa: N802 - matches this module's brief's naming
    return InventoryCode(code)


def StockValidator(value: int) -> StockQuantity:  # noqa: N802
    return StockQuantity(value)


def ReservationValidator(number: str) -> ReservationNumber:  # noqa: N802
    return ReservationNumber(number)


def MovementValidator(source_id, destination_id, movement_type: str) -> None:  # noqa: N802
    from apps.inventory.domain.exceptions import InvalidMovement

    if movement_type == "transfer" and (source_id is None or destination_id is None):
        raise InvalidMovement("A transfer movement requires both a source and a destination.")


def AdjustmentValidator(quantity_delta: int) -> None:  # noqa: N802
    from common.exceptions import ValidationFailed

    if quantity_delta == 0:
        raise ValidationFailed("An adjustment must have a non-zero quantity delta.")


def BatchValidator(batch_number: str) -> BatchNumber:  # noqa: N802
    return BatchNumber(batch_number)


def SerialValidator(serial_number: str) -> SerialNumber:  # noqa: N802
    return SerialNumber(serial_number)


def ExpirationValidator(manufacture_date, expiration_date) -> None:  # noqa: N802
    from common.exceptions import ValidationFailed

    if manufacture_date and expiration_date and expiration_date <= manufacture_date:
        raise ValidationFailed("expiration_date must be after manufacture_date.")


def ThresholdValidator(low_stock_at: int, reorder_at: int, overstock_at: int | None = None) -> StockThreshold:  # noqa: N802
    return StockThreshold(low_stock_at=low_stock_at, reorder_at=reorder_at, overstock_at=overstock_at)


def WarehouseValidator(warehouse_id) -> None:  # noqa: N802
    """Structural presence check only -- existence of the referenced Warehouse in `apps.store` is an Application Service concern (a cross-module repository lookup), not something this pure validator can resolve."""
    from common.exceptions import ValidationFailed

    if warehouse_id is None:
        raise ValidationFailed("A warehouse_id is required.", details={"fields": [{"field": "warehouse_id", "code": "REQUIRED"}]})


def ShelfValidator(shelf_id) -> None:  # noqa: N802
    from common.exceptions import ValidationFailed

    if shelf_id is None:
        raise ValidationFailed("A shelf_id is required.", details={"fields": [{"field": "shelf_id", "code": "REQUIRED"}]})
