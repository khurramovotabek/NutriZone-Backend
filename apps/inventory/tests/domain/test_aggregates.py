from __future__ import annotations

import uuid
from datetime import date, datetime

import pytest

from apps.inventory.domain.aggregates import (
    Batch,
    CycleCount,
    Inventory,
    InventoryAdjustment,
    InventoryMovement,
    InventorySnapshot,
    PhysicalInventory,
    Reservation,
    ShelfInventory,
    WarehouseInventory,
)
from apps.inventory.domain.entities import ReservationItem, SerialItem, StockSnapshot
from apps.inventory.domain.enums import AdjustmentReason, MovementType, StockStatus
from apps.inventory.domain.exceptions import (
    BatchExpired,
    DuplicateSerial,
    InsufficientStock,
    InvalidCycleCountLifecycleTransition,
    InvalidInventoryLifecycleTransition,
    InvalidMovement,
    InvalidPhysicalInventoryLifecycleTransition,
    InvalidReservationLifecycleTransition,
    NegativeStock,
    ReservationExpired,
)
from apps.inventory.domain.value_objects import (
    BatchNumber,
    ExpirationDate,
    InventoryCode,
    ManufactureDate,
    MovementReference,
    ReservationNumber,
    SerialNumber,
    SnapshotVersion,
    StockQuantity,
)
from common.exceptions import ValidationFailed

pytestmark = pytest.mark.unit


def _now() -> datetime:
    return datetime.utcnow()


def _bare_warehouse_inventory() -> WarehouseInventory:
    return WarehouseInventory(id=uuid.uuid4(), inventory_id=uuid.uuid4(), warehouse_id=uuid.uuid4())


class TestInventoryAggregate:
    def test_serial_tracked_requires_batch_tracked(self):
        with pytest.raises(ValidationFailed):
            Inventory(id=uuid.uuid4(), code=InventoryCode("WHEY001"), product_variant_id=uuid.uuid4(), is_batch_tracked=False, is_serial_tracked=True)

    def test_valid_construction(self):
        Inventory(id=uuid.uuid4(), code=InventoryCode("WHEY001"), product_variant_id=uuid.uuid4(), is_batch_tracked=True, is_serial_tracked=True)

    def test_archive_and_restore_round_trip(self):
        inventory = Inventory(id=uuid.uuid4(), code=InventoryCode("WHEY002"), product_variant_id=uuid.uuid4())
        archived_event = inventory.archive()
        assert inventory.status.value == "archived"
        assert archived_event.inventory_id == inventory.id

        restored_event = inventory.restore()
        assert inventory.status.value == "active"
        assert restored_event.inventory_id == inventory.id

    def test_double_archive_raises(self):
        inventory = Inventory(id=uuid.uuid4(), code=InventoryCode("WHEY003"), product_variant_id=uuid.uuid4())
        inventory.archive()
        with pytest.raises(InvalidInventoryLifecycleTransition):
            inventory.archive()

    def test_restore_non_archived_raises(self):
        inventory = Inventory(id=uuid.uuid4(), code=InventoryCode("WHEY004"), product_variant_id=uuid.uuid4())
        with pytest.raises(InvalidInventoryLifecycleTransition):
            inventory.restore()

    def test_assert_active_raises_when_archived(self):
        from apps.inventory.domain.exceptions import InventoryArchived

        inventory = Inventory(id=uuid.uuid4(), code=InventoryCode("WHEY005"), product_variant_id=uuid.uuid4())
        inventory.archive()
        with pytest.raises(InventoryArchived):
            inventory.assert_active()

    def test_raise_alert(self):
        inventory = Inventory(id=uuid.uuid4(), code=InventoryCode("WHEY006"), product_variant_id=uuid.uuid4())
        alert = inventory.raise_alert("low_stock", _now())
        assert alert.id in inventory.alerts


class TestWarehouseInventoryBucketTransitions:
    """Verifies the structural invariants documented in aggregates.py: each method only reads from its designated source bucket."""

    def test_receive_increases_incoming_only(self):
        wi = _bare_warehouse_inventory()
        wi.receive(StockQuantity(10), "PO-001", _now())
        assert wi.get_quantity(StockStatus.INCOMING) == 10
        assert wi.available_quantity == 0

    def test_confirm_incoming_moves_incoming_to_available(self):
        wi = _bare_warehouse_inventory()
        wi.receive(StockQuantity(10), "PO-001", _now())
        wi.confirm_incoming(StockQuantity(10), "PO-001", _now())
        assert wi.get_quantity(StockStatus.INCOMING) == 0
        assert wi.available_quantity == 10

    def test_confirm_more_than_incoming_raises(self):
        wi = _bare_warehouse_inventory()
        wi.receive(StockQuantity(5), "PO-001", _now())
        with pytest.raises(InsufficientStock):
            wi.confirm_incoming(StockQuantity(10), "PO-001", _now())

    def test_reserve_moves_available_to_reserved(self):
        wi = _bare_warehouse_inventory()
        wi.receive(StockQuantity(10), "PO-001", _now())
        wi.confirm_incoming(StockQuantity(10), "PO-001", _now())
        wi.reserve(StockQuantity(4), "RSV-001", _now())
        assert wi.available_quantity == 6
        assert wi.reserved_quantity == 4

    def test_reserve_more_than_available_raises(self):
        wi = _bare_warehouse_inventory()
        with pytest.raises(InsufficientStock):
            wi.reserve(StockQuantity(1), "RSV-001", _now())

    def test_damaged_stock_cannot_be_reserved_structurally(self):
        """'Damaged stock cannot be reserved' -- reserve() only ever reads AVAILABLE, so damaging stock first and then attempting to reserve past the reduced available amount correctly fails."""
        wi = _bare_warehouse_inventory()
        wi.receive(StockQuantity(10), "PO-001", _now())
        wi.confirm_incoming(StockQuantity(10), "PO-001", _now())
        wi.mark_damaged(StockQuantity(10), "DMG-001", _now())
        assert wi.available_quantity == 0
        with pytest.raises(InsufficientStock):
            wi.reserve(StockQuantity(1), "RSV-001", _now())

    def test_sell_only_from_reserved(self):
        wi = _bare_warehouse_inventory()
        wi.receive(StockQuantity(10), "PO-001", _now())
        wi.confirm_incoming(StockQuantity(10), "PO-001", _now())
        wi.reserve(StockQuantity(5), "RSV-001", _now())
        wi.sell(StockQuantity(5), "SALE-001", _now())
        assert wi.reserved_quantity == 0

    def test_incoming_stock_cannot_be_sold_structurally(self):
        """'Incoming stock cannot be sold' -- sell() only reads RESERVED, which is unreachable from INCOMING without first confirming to AVAILABLE and then reserving."""
        wi = _bare_warehouse_inventory()
        wi.receive(StockQuantity(10), "PO-001", _now())
        with pytest.raises(InsufficientStock):
            wi.sell(StockQuantity(5), "SALE-001", _now())

    def test_quarantine_stock_cannot_be_transferred_structurally(self):
        """'Quarantine stock cannot be transferred' -- transfer_out() only reads AVAILABLE."""
        wi = _bare_warehouse_inventory()
        wi.receive(StockQuantity(10), "PO-001", _now())
        wi.confirm_incoming(StockQuantity(10), "PO-001", _now())
        wi.quarantine(StockQuantity(10), "QA-001", _now())
        assert wi.get_quantity(StockStatus.QUARANTINE) == 10
        with pytest.raises(InsufficientStock):
            wi.transfer_out(StockQuantity(1), "TRF-001", _now())

    def test_expired_stock_cannot_become_available_structurally(self):
        """'Expired stock cannot become available' -- no method transitions stock out of EXPIRED."""
        wi = _bare_warehouse_inventory()
        wi.receive(StockQuantity(10), "PO-001", _now())
        wi.confirm_incoming(StockQuantity(10), "PO-001", _now())
        wi.mark_expired(StockQuantity(10), "EXP-001", _now())
        assert wi.get_quantity(StockStatus.EXPIRED) == 10
        assert not hasattr(wi, "unexpire")  # no such method exists on the aggregate at all

    def test_transfer_out_and_receive_transfer_in(self):
        source = _bare_warehouse_inventory()
        destination = _bare_warehouse_inventory()
        source.receive(StockQuantity(10), "PO-001", _now())
        source.confirm_incoming(StockQuantity(10), "PO-001", _now())
        source.transfer_out(StockQuantity(4), "TRF-001", _now())
        destination.receive_transfer_in(StockQuantity(4), "TRF-001", _now())
        assert source.available_quantity == 6
        assert destination.available_quantity == 4

    def test_receive_return_lands_in_returned_bucket(self):
        wi = _bare_warehouse_inventory()
        wi.receive_return(StockQuantity(3), "RET-001", _now())
        assert wi.get_quantity(StockStatus.RETURNED) == 3
        assert wi.available_quantity == 0

    def test_adjust_never_goes_negative(self):
        wi = _bare_warehouse_inventory()
        with pytest.raises(NegativeStock):
            wi.adjust(StockStatus.AVAILABLE, -5, "ADJ-001", _now())

    def test_adjust_positive_delta(self):
        wi = _bare_warehouse_inventory()
        wi.adjust(StockStatus.AVAILABLE, 20, "ADJ-001", _now())
        assert wi.available_quantity == 20

    def test_transaction_and_ledger_returned_by_every_method(self):
        wi = _bare_warehouse_inventory()
        transaction, ledger = wi.receive(StockQuantity(10), "PO-001", _now())
        assert transaction.quantity == 10
        assert ledger.quantity_delta == 10
        assert ledger.balance_after == 10


class TestShelfInventoryAggregate:
    def test_add_and_remove(self):
        shelf_inv = ShelfInventory(id=uuid.uuid4(), warehouse_inventory_id=uuid.uuid4(), shelf_id=uuid.uuid4())
        shelf_inv.add(StockQuantity(10))
        assert shelf_inv.quantity.value == 10
        shelf_inv.remove(StockQuantity(4))
        assert shelf_inv.quantity.value == 6

    def test_remove_below_zero_raises(self):
        shelf_inv = ShelfInventory(id=uuid.uuid4(), warehouse_inventory_id=uuid.uuid4(), shelf_id=uuid.uuid4())
        with pytest.raises(ValidationFailed):
            shelf_inv.remove(StockQuantity(1))


class TestReservationAggregate:
    def _reservation(self) -> Reservation:
        return Reservation(id=uuid.uuid4(), reservation_number=ReservationNumber("RSV-ABC123"), owner_type="user", owner_id=uuid.uuid4(), warehouse_inventory_id=uuid.uuid4())

    def test_add_item_while_pending(self):
        reservation = self._reservation()
        reservation.add_item(ReservationItem(id=uuid.uuid4(), quantity=StockQuantity(5)))
        assert reservation.total_quantity() == 5

    def test_confirm_then_add_item_raises(self):
        reservation = self._reservation()
        reservation.confirm()
        with pytest.raises(InvalidReservationLifecycleTransition):
            reservation.add_item(ReservationItem(id=uuid.uuid4(), quantity=StockQuantity(5)))

    def test_cancel_cancelled_raises(self):
        reservation = self._reservation()
        reservation.cancel()
        with pytest.raises(InvalidReservationLifecycleTransition):
            reservation.cancel()

    def test_expire_before_expiry_time_raises(self):
        from datetime import timedelta

        reservation = self._reservation()
        reservation.expires_at = _now() + timedelta(hours=1)
        with pytest.raises(ReservationExpired):
            reservation.expire(_now())

    def test_expire_after_expiry_time_succeeds(self):
        from datetime import timedelta

        reservation = self._reservation()
        reservation.expires_at = _now() - timedelta(minutes=1)
        event = reservation.expire(_now())
        assert reservation.status.value == "expired"
        assert event.reservation_id == reservation.id


class TestInventoryMovementAggregate:
    def test_transfer_requires_both_endpoints(self):
        with pytest.raises(InvalidMovement):
            InventoryMovement(id=uuid.uuid4(), movement_type=MovementType.TRANSFER, reference=MovementReference("TRF-0001"), source_warehouse_inventory_id=uuid.uuid4(), destination_warehouse_inventory_id=None)

    def test_valid_transfer_construction(self):
        InventoryMovement(id=uuid.uuid4(), movement_type=MovementType.TRANSFER, reference=MovementReference("TRF-0002"), source_warehouse_inventory_id=uuid.uuid4(), destination_warehouse_inventory_id=uuid.uuid4())

    def test_receive_movement_does_not_require_endpoints(self):
        InventoryMovement(id=uuid.uuid4(), movement_type=MovementType.RECEIVE, reference=MovementReference("REC-0001"))

    def test_total_quantity(self):
        from apps.inventory.domain.entities import MovementItem

        movement = InventoryMovement(id=uuid.uuid4(), movement_type=MovementType.RECEIVE, reference=MovementReference("REC-0002"))
        movement.add_item(MovementItem(id=uuid.uuid4(), quantity=StockQuantity(5)))
        movement.add_item(MovementItem(id=uuid.uuid4(), quantity=StockQuantity(3)))
        assert movement.total_quantity() == 8


class TestInventoryAdjustmentAggregate:
    def test_zero_delta_raises(self):
        with pytest.raises(ValidationFailed):
            InventoryAdjustment(id=uuid.uuid4(), warehouse_inventory_id=uuid.uuid4(), reason=AdjustmentReason.MANUAL, quantity_delta=0, reference="ADJ-001")

    def test_valid_construction(self):
        InventoryAdjustment(id=uuid.uuid4(), warehouse_inventory_id=uuid.uuid4(), reason=AdjustmentReason.FOUND, quantity_delta=5, reference="ADJ-002")


class TestBatchAggregate:
    def test_expiration_before_manufacture_raises(self):
        with pytest.raises(ValidationFailed):
            Batch(id=uuid.uuid4(), inventory_id=uuid.uuid4(), batch_number=BatchNumber("BATCH-001"), manufacture_date=ManufactureDate(date(2026, 6, 1)), expiration_date=ExpirationDate(date(2026, 1, 1)))

    def test_valid_construction(self):
        Batch(id=uuid.uuid4(), inventory_id=uuid.uuid4(), batch_number=BatchNumber("BATCH-002"), manufacture_date=ManufactureDate(date(2026, 1, 1)), expiration_date=ExpirationDate(date(2026, 6, 1)))

    def test_assert_not_expired_raises_when_past_expiration(self):
        batch = Batch(id=uuid.uuid4(), inventory_id=uuid.uuid4(), batch_number=BatchNumber("BATCH-003"), expiration_date=ExpirationDate(date(2026, 1, 1)))
        with pytest.raises(BatchExpired):
            batch.assert_not_expired(date(2026, 1, 1))

    def test_mark_expired_before_expiration_date_raises(self):
        batch = Batch(id=uuid.uuid4(), inventory_id=uuid.uuid4(), batch_number=BatchNumber("BATCH-004"), expiration_date=ExpirationDate(date(2026, 6, 1)))
        with pytest.raises(ValidationFailed):
            batch.mark_expired(date(2026, 1, 1))

    def test_mark_expired_succeeds_after_expiration(self):
        batch = Batch(id=uuid.uuid4(), inventory_id=uuid.uuid4(), batch_number=BatchNumber("BATCH-005"), expiration_date=ExpirationDate(date(2026, 1, 1)))
        batch.mark_expired(date(2026, 1, 1))
        assert batch.status.value == "expired"

    def test_register_serial(self):
        batch = Batch(id=uuid.uuid4(), inventory_id=uuid.uuid4(), batch_number=BatchNumber("BATCH-006"))
        serial = SerialItem(id=uuid.uuid4(), serial_number=SerialNumber("SN00012345"))
        event = batch.register_serial(serial)
        assert serial.id in batch.serials
        assert event.serial_number == "SN00012345"

    def test_register_duplicate_serial_raises(self):
        batch = Batch(id=uuid.uuid4(), inventory_id=uuid.uuid4(), batch_number=BatchNumber("BATCH-007"))
        batch.register_serial(SerialItem(id=uuid.uuid4(), serial_number=SerialNumber("SN00012345")))
        with pytest.raises(DuplicateSerial):
            batch.register_serial(SerialItem(id=uuid.uuid4(), serial_number=SerialNumber("SN00012345")))


class TestCycleCountAggregate:
    def test_start_from_planned(self):
        cycle_count = CycleCount(id=uuid.uuid4(), warehouse_id=uuid.uuid4())
        event = cycle_count.start()
        assert cycle_count.status.value == "in_progress"
        assert event.warehouse_id == cycle_count.warehouse_id

    def test_start_twice_raises(self):
        cycle_count = CycleCount(id=uuid.uuid4(), warehouse_id=uuid.uuid4())
        cycle_count.start()
        with pytest.raises(InvalidCycleCountLifecycleTransition):
            cycle_count.start()

    def test_record_count_before_start_raises(self):
        cycle_count = CycleCount(id=uuid.uuid4(), warehouse_id=uuid.uuid4())
        with pytest.raises(InvalidCycleCountLifecycleTransition):
            cycle_count.record_count(uuid.uuid4(), 5)

    def test_record_negative_count_raises(self):
        cycle_count = CycleCount(id=uuid.uuid4(), warehouse_id=uuid.uuid4())
        cycle_count.start()
        with pytest.raises(NegativeStock):
            cycle_count.record_count(uuid.uuid4(), -1)

    def test_complete_computes_discrepancies(self):
        cycle_count = CycleCount(id=uuid.uuid4(), warehouse_id=uuid.uuid4())
        cycle_count.start()
        inv_id_match, inv_id_mismatch = uuid.uuid4(), uuid.uuid4()
        cycle_count.record_count(inv_id_match, 10)
        cycle_count.record_count(inv_id_mismatch, 8)
        event = cycle_count.complete({inv_id_match: 10, inv_id_mismatch: 10})
        assert event.discrepancy_count == 1

    def test_cancel_completed_raises(self):
        cycle_count = CycleCount(id=uuid.uuid4(), warehouse_id=uuid.uuid4())
        cycle_count.start()
        cycle_count.complete({})
        with pytest.raises(InvalidCycleCountLifecycleTransition):
            cycle_count.cancel()


class TestPhysicalInventoryAggregate:
    def test_start_and_complete(self):
        physical_inventory = PhysicalInventory(id=uuid.uuid4(), warehouse_id=uuid.uuid4())
        physical_inventory.start()
        assert physical_inventory.status.value == "in_progress"

        inv_id = uuid.uuid4()
        physical_inventory.record_count(inv_id, 5)
        event = physical_inventory.complete({inv_id: 5})
        assert event.discrepancy_count == 0

    def test_start_twice_raises(self):
        physical_inventory = PhysicalInventory(id=uuid.uuid4(), warehouse_id=uuid.uuid4())
        physical_inventory.start()
        with pytest.raises(InvalidPhysicalInventoryLifecycleTransition):
            physical_inventory.start()


class TestInventorySnapshotAggregate:
    def test_add_item_and_complete(self):
        snapshot = InventorySnapshot(id=uuid.uuid4(), version=SnapshotVersion(1))
        snapshot.add_item(StockSnapshot(id=uuid.uuid4(), inventory_id=uuid.uuid4(), quantities_by_status={"available": 10}))
        event = snapshot.complete(_now())
        assert snapshot.status.value == "completed"
        assert event.version == 1

    def test_add_item_after_completion_raises(self):
        snapshot = InventorySnapshot(id=uuid.uuid4(), version=SnapshotVersion(1))
        snapshot.complete(_now())
        with pytest.raises(ValidationFailed):
            snapshot.add_item(StockSnapshot(id=uuid.uuid4(), inventory_id=uuid.uuid4()))

    def test_mark_failed(self):
        snapshot = InventorySnapshot(id=uuid.uuid4(), version=SnapshotVersion(1))
        snapshot.mark_failed()
        assert snapshot.status.value == "failed"
