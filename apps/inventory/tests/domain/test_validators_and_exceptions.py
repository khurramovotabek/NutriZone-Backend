from __future__ import annotations

import pytest

from apps.inventory.domain import exceptions as exc
from apps.inventory.domain.validators import (
    AdjustmentValidator,
    BatchValidator,
    ExpirationValidator,
    InventoryValidator,
    MovementValidator,
    ReservationValidator,
    SerialValidator,
    ShelfValidator,
    StockValidator,
    ThresholdValidator,
    WarehouseValidator,
)
from common.exceptions import DomainException, ValidationFailed

pytestmark = pytest.mark.unit


def test_inventory_validator():
    assert InventoryValidator("WHEY001").value == "WHEY001"


def test_stock_validator():
    assert StockValidator(10).value == 10


def test_stock_validator_rejects_negative():
    with pytest.raises(ValidationFailed):
        StockValidator(-1)


def test_reservation_validator():
    assert ReservationValidator("RSV-ABC123").value == "RSV-ABC123"


def test_movement_validator_transfer_requires_endpoints():
    with pytest.raises(exc.InvalidMovement):
        MovementValidator(None, None, "transfer")


def test_movement_validator_passes_for_non_transfer():
    MovementValidator(None, None, "receive")


def test_adjustment_validator_rejects_zero():
    with pytest.raises(ValidationFailed):
        AdjustmentValidator(0)


def test_batch_validator():
    assert BatchValidator("BATCH-001").value == "BATCH-001"


def test_serial_validator():
    assert SerialValidator("SN00012345").value == "SN00012345"


def test_expiration_validator_passes_for_valid_order():
    import datetime

    ExpirationValidator(datetime.date(2026, 1, 1), datetime.date(2026, 6, 1))


def test_expiration_validator_rejects_invalid_order():
    import datetime

    with pytest.raises(ValidationFailed):
        ExpirationValidator(datetime.date(2026, 6, 1), datetime.date(2026, 1, 1))


def test_threshold_validator():
    threshold = ThresholdValidator(10, 5, 100)
    assert threshold.low_stock_at == 10


def test_warehouse_validator_rejects_none():
    with pytest.raises(ValidationFailed):
        WarehouseValidator(None)


def test_shelf_validator_rejects_none():
    with pytest.raises(ValidationFailed):
        ShelfValidator(None)


@pytest.mark.parametrize(
    "exception_cls",
    [
        exc.NegativeStock, exc.InsufficientStock, exc.DuplicateBatch, exc.DuplicateSerial, exc.ReservationExpired,
        exc.ReservationConflict, exc.InvalidMovement, exc.InvalidWarehouse, exc.InvalidShelf, exc.BatchExpired,
        exc.InventoryArchived, exc.LedgerCorrupted, exc.InventoryMismatch, exc.InvalidInventoryLifecycleTransition,
        exc.InvalidReservationLifecycleTransition, exc.InvalidCycleCountLifecycleTransition,
        exc.InvalidPhysicalInventoryLifecycleTransition, exc.DamagedStockCannotBeReserved,
        exc.QuarantineStockCannotBeTransferred, exc.IncomingStockCannotBeSold, exc.ExpiredStockCannotBecomeAvailable,
        exc.InventoryEntityNotFound,
    ],
)
def test_every_exception_subclasses_domain_exception(exception_cls):
    assert issubclass(exception_cls, DomainException)
    instance = exception_cls("test message")
    assert instance.message == "test message"
    assert instance.code
