from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone as django_timezone

from apps.inventory.application.services._shared import InventoryServiceContext
from apps.inventory.application.services.batch_and_serial import CreateBatch, RegisterSerial
from apps.inventory.application.services.reservations import CancelReservation, CreateReservation, ExpireReservation
from apps.inventory.domain.aggregates import Inventory, WarehouseInventory
from apps.inventory.domain.exceptions import DuplicateBatch, DuplicateSerial, InventoryEntityNotFound
from apps.inventory.domain.value_objects import InventoryCode
from apps.inventory.tests.application.fakes import (
    FakeBatchRepository, FakeInventoryRepository, FakeReservationRepository, FakeSerialRepository,
    FakeWarehouseInventoryRepository, collect_events,
)
from common.exceptions import ResourceNotFound

pytestmark = pytest.mark.django_db


def _ctx():
    events: list = []
    return InventoryServiceContext(stage_events=collect_events(events), actor_id=uuid.uuid4()), events


class TestCreateBatch:
    def test_creates_batch(self):
        inventory_repo = FakeInventoryRepository()
        inventory = Inventory(id=uuid.uuid4(), code=InventoryCode("WHEY001"), product_variant_id=uuid.uuid4())
        inventory_repo.save(inventory)
        batch_repo = FakeBatchRepository()
        ctx, events = _ctx()

        batch = CreateBatch(batch_repo, inventory_repo, ctx).execute(inventory_id=inventory.id, batch_number="BATCH-001")
        assert batch.batch_number.value == "BATCH-001"
        assert any(e[0] == "BatchCreated" for e in events)

    def test_unknown_inventory_raises(self):
        ctx, _ = _ctx()
        with pytest.raises(InventoryEntityNotFound):
            CreateBatch(FakeBatchRepository(), FakeInventoryRepository(), ctx).execute(inventory_id=uuid.uuid4(), batch_number="BATCH-001")

    def test_duplicate_batch_number_raises(self):
        inventory_repo = FakeInventoryRepository()
        inventory = Inventory(id=uuid.uuid4(), code=InventoryCode("WHEY002"), product_variant_id=uuid.uuid4())
        inventory_repo.save(inventory)
        batch_repo = FakeBatchRepository()
        ctx, _ = _ctx()

        CreateBatch(batch_repo, inventory_repo, ctx).execute(inventory_id=inventory.id, batch_number="BATCH-002")
        with pytest.raises(DuplicateBatch):
            CreateBatch(batch_repo, inventory_repo, ctx).execute(inventory_id=inventory.id, batch_number="BATCH-002")


class TestRegisterSerial:
    def test_registers_serial(self):
        inventory_repo = FakeInventoryRepository()
        inventory = Inventory(id=uuid.uuid4(), code=InventoryCode("WHEY003"), product_variant_id=uuid.uuid4())
        inventory_repo.save(inventory)
        batch_repo = FakeBatchRepository()
        ctx, events = _ctx()
        batch = CreateBatch(batch_repo, inventory_repo, ctx).execute(inventory_id=inventory.id, batch_number="BATCH-003")

        serial_repo = FakeSerialRepository()
        updated = RegisterSerial(batch_repo, serial_repo, ctx).execute(batch_id=batch.id, serial_number="SN00012345")
        assert len(updated.serials) == 1
        assert any(e[0] == "SerialRegistered" for e in events)

    def test_duplicate_serial_raises(self):
        serial_repo = FakeSerialRepository()
        serial_repo.numbers.add("SN00012345")
        inventory_repo = FakeInventoryRepository()
        inventory = Inventory(id=uuid.uuid4(), code=InventoryCode("WHEY004"), product_variant_id=uuid.uuid4())
        inventory_repo.save(inventory)
        batch_repo = FakeBatchRepository()
        ctx, _ = _ctx()
        batch = CreateBatch(batch_repo, inventory_repo, ctx).execute(inventory_id=inventory.id, batch_number="BATCH-004")

        with pytest.raises(DuplicateSerial):
            RegisterSerial(batch_repo, serial_repo, ctx).execute(batch_id=batch.id, serial_number="SN00012345")


class TestReservationServices:
    def _warehouse_inventory_with_stock(self, repo: FakeWarehouseInventoryRepository, available: int) -> WarehouseInventory:
        import datetime

        from apps.inventory.domain.value_objects import StockQuantity

        wi = WarehouseInventory(id=uuid.uuid4(), inventory_id=uuid.uuid4(), warehouse_id=uuid.uuid4())
        wi.receive(StockQuantity(available), "PO-001", datetime.datetime.utcnow())
        wi.confirm_incoming(StockQuantity(available), "PO-001", datetime.datetime.utcnow())
        repo.save(wi)
        return wi

    def test_create_reservation(self):
        wi_repo = FakeWarehouseInventoryRepository()
        wi = self._warehouse_inventory_with_stock(wi_repo, 10)
        reservation_repo = FakeReservationRepository()
        ctx, events = _ctx()

        reservation = CreateReservation(reservation_repo, wi_repo, ctx).execute(
            reservation_number="RSV-ABC123", owner_type="user", owner_id=uuid.uuid4(), warehouse_inventory_id=wi.id, quantity=4,
        )
        assert reservation.total_quantity() == 4
        assert wi_repo.get_by_id(wi.id).available_quantity == 6
        assert any(e[0] == "ReservationCreated" for e in events)

    def test_cancel_reservation_releases_stock(self):
        wi_repo = FakeWarehouseInventoryRepository()
        wi = self._warehouse_inventory_with_stock(wi_repo, 10)
        reservation_repo = FakeReservationRepository()
        ctx, events = _ctx()

        reservation = CreateReservation(reservation_repo, wi_repo, ctx).execute(
            reservation_number="RSV-DEF456", owner_type="user", owner_id=uuid.uuid4(), warehouse_inventory_id=wi.id, quantity=4,
        )
        CancelReservation(reservation_repo, wi_repo, ctx).execute(reservation.id)

        assert wi_repo.get_by_id(wi.id).available_quantity == 10
        assert any(e[0] == "ReservationCancelled" for e in events)

    def test_expire_reservation_before_expiry_raises(self):
        wi_repo = FakeWarehouseInventoryRepository()
        wi = self._warehouse_inventory_with_stock(wi_repo, 10)
        reservation_repo = FakeReservationRepository()
        ctx, _ = _ctx()

        reservation = CreateReservation(reservation_repo, wi_repo, ctx).execute(
            reservation_number="RSV-GHI789", owner_type="user", owner_id=uuid.uuid4(), warehouse_inventory_id=wi.id, quantity=4, expires_in_minutes=60,
        )
        with pytest.raises(Exception):
            ExpireReservation(reservation_repo, wi_repo, ctx).execute(reservation.id)

    def test_cancel_missing_reservation_raises(self):
        ctx, _ = _ctx()
        with pytest.raises(ResourceNotFound):
            CancelReservation(FakeReservationRepository(), FakeWarehouseInventoryRepository(), ctx).execute(uuid.uuid4())
