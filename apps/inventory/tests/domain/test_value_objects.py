from __future__ import annotations

from datetime import date

import pytest

from apps.inventory.domain.value_objects import (
    AvailableQuantity,
    BatchNumber,
    ExpirationDate,
    InventoryCode,
    InventoryLocation,
    ManufactureDate,
    MovementReference,
    ReservationNumber,
    ReservedQuantity,
    SerialNumber,
    ShelfCoordinate,
    SnapshotVersion,
    StockQuantity,
    StockThreshold,
)
from common.exceptions import ValidationFailed

pytestmark = pytest.mark.unit


class TestStockQuantity:
    def test_valid_non_negative(self):
        assert StockQuantity(10).value == 10

    def test_zero_is_valid(self):
        assert StockQuantity(0).is_zero() is True

    def test_rejects_negative(self):
        with pytest.raises(ValidationFailed):
            StockQuantity(-1)

    def test_addition(self):
        assert (StockQuantity(5) + StockQuantity(3)).value == 8

    def test_subtraction_within_bounds(self):
        assert (StockQuantity(5) - StockQuantity(3)).value == 2

    def test_subtraction_below_zero_raises(self):
        with pytest.raises(ValidationFailed):
            StockQuantity(3) - StockQuantity(5)

    def test_comparison_operators(self):
        assert StockQuantity(5) >= StockQuantity(5)
        assert StockQuantity(6) > StockQuantity(5)


class TestReservedAndAvailableQuantity:
    def test_reserved_quantity_rejects_negative(self):
        with pytest.raises(ValidationFailed):
            ReservedQuantity(-1)

    def test_available_quantity_rejects_negative(self):
        with pytest.raises(ValidationFailed):
            AvailableQuantity(-1)


class TestExpirationDate:
    def test_is_expired_true(self):
        assert ExpirationDate(date(2026, 1, 1)).is_expired(date(2026, 1, 1)) is True

    def test_is_expired_false(self):
        assert ExpirationDate(date(2026, 6, 1)).is_expired(date(2026, 1, 1)) is False


class TestCodeValueObjects:
    def test_inventory_code_valid(self):
        assert InventoryCode("WHEY2KG001").value == "WHEY2KG001"

    def test_inventory_code_rejects_lowercase(self):
        with pytest.raises(ValidationFailed):
            InventoryCode("whey2kg")

    def test_batch_number_valid(self):
        assert BatchNumber("BATCH-2026-001").value == "BATCH-2026-001"

    def test_serial_number_valid(self):
        assert SerialNumber("SN00012345").value == "SN00012345"

    def test_reservation_number_valid(self):
        assert ReservationNumber("RSV-ABC123").value == "RSV-ABC123"

    def test_reservation_number_rejects_missing_prefix(self):
        with pytest.raises(ValidationFailed):
            ReservationNumber("ABC123")

    def test_movement_reference_valid(self):
        assert MovementReference("PO-2026001").value == "PO-2026001"


class TestShelfCoordinate:
    def test_valid(self):
        ShelfCoordinate(aisle="A1", shelf="B2")

    def test_rejects_empty_aisle(self):
        with pytest.raises(ValidationFailed):
            ShelfCoordinate(aisle="", shelf="B2")


class TestInventoryLocation:
    def test_valid_with_warehouse_only(self):
        import uuid

        InventoryLocation(warehouse_id=uuid.uuid4())


class TestStockThreshold:
    def test_valid(self):
        StockThreshold(low_stock_at=10, reorder_at=5, overstock_at=100)

    def test_rejects_negative(self):
        with pytest.raises(ValidationFailed):
            StockThreshold(low_stock_at=-1, reorder_at=5)

    def test_rejects_reorder_above_low_stock(self):
        with pytest.raises(ValidationFailed):
            StockThreshold(low_stock_at=5, reorder_at=10)

    def test_rejects_overstock_below_low_stock(self):
        with pytest.raises(ValidationFailed):
            StockThreshold(low_stock_at=10, reorder_at=5, overstock_at=5)


class TestSnapshotVersion:
    def test_valid(self):
        assert SnapshotVersion(1).value == 1

    def test_rejects_zero(self):
        with pytest.raises(ValidationFailed):
            SnapshotVersion(0)

    def test_next_increments(self):
        assert SnapshotVersion(1).next().value == 2


class TestManufactureDate:
    def test_construction(self):
        assert ManufactureDate(date(2026, 1, 1)).value == date(2026, 1, 1)
