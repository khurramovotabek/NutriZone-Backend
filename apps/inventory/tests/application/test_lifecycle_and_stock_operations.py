from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from apps.inventory.application.services._shared import InventoryServiceContext
from apps.inventory.application.services.lifecycle import ArchiveInventory, CreateInventory, RestoreInventory, UpdateInventory
from apps.inventory.application.services.stock_operations import (
    AdjustStock, DamageStock, ExpireStock, ReceiveStock, ReleaseReservation, ReserveStock, TransferStock,
)
from apps.inventory.domain.aggregates import Inventory, WarehouseInventory
from apps.inventory.domain.enums import StockStatus
from apps.inventory.domain.exceptions import InsufficientStock
from apps.inventory.domain.value_objects import InventoryCode, StockQuantity
from apps.inventory.tests.application.fakes import FakeInventoryRepository, FakeWarehouseInventoryRepository, collect_events
from common.exceptions import ConflictError, ResourceNotFound

pytestmark = pytest.mark.django_db  # every service uses @transaction.atomic -- same documented rationale as every prior module


def _ctx():
    events: list = []
    return InventoryServiceContext(stage_events=collect_events(events), actor_id=uuid.uuid4()), events


class TestCreateInventory:
    def test_creates_inventory(self):
        repo = FakeInventoryRepository()
        ctx, events = _ctx()
        inventory = CreateInventory(repo, ctx).execute(code="WHEY001", product_variant_id=uuid.uuid4())
        assert inventory.code.value == "WHEY001"
        assert any(e[0] == "InventoryCreated" for e in events)

    def test_duplicate_code_raises(self):
        repo = FakeInventoryRepository()
        ctx, _ = _ctx()
        CreateInventory(repo, ctx).execute(code="WHEY001", product_variant_id=uuid.uuid4())
        with pytest.raises(ConflictError):
            CreateInventory(repo, ctx).execute(code="WHEY001", product_variant_id=uuid.uuid4())

    def test_duplicate_product_variant_raises(self):
        repo = FakeInventoryRepository()
        ctx, _ = _ctx()
        variant_id = uuid.uuid4()
        CreateInventory(repo, ctx).execute(code="WHEY001", product_variant_id=variant_id)
        with pytest.raises(ConflictError):
            CreateInventory(repo, ctx).execute(code="WHEY002", product_variant_id=variant_id)


class TestUpdateArchiveRestoreInventory:
    def test_update_sets_threshold(self):
        repo = FakeInventoryRepository()
        inventory = Inventory(id=uuid.uuid4(), code=InventoryCode("WHEY002"), product_variant_id=uuid.uuid4())
        repo.save(inventory)
        ctx, _ = _ctx()

        updated = UpdateInventory(repo, ctx).execute(inventory_id=inventory.id, low_stock_at=10, reorder_at=5)
        assert updated.threshold.low_stock_at == 10

    def test_archive_restore_round_trip(self):
        repo = FakeInventoryRepository()
        inventory = Inventory(id=uuid.uuid4(), code=InventoryCode("WHEY003"), product_variant_id=uuid.uuid4())
        repo.save(inventory)
        ctx, events = _ctx()

        archived = ArchiveInventory(repo, ctx).execute(inventory.id)
        assert archived.status.value == "archived"

        restored = RestoreInventory(repo, ctx).execute(inventory.id)
        assert restored.status.value == "active"
        event_types = [e[0] for e in events]
        assert "InventoryArchivedEvent" in event_types
        assert "InventoryRestored" in event_types

    def test_update_missing_inventory_raises(self):
        repo = FakeInventoryRepository()
        ctx, _ = _ctx()
        with pytest.raises(ResourceNotFound):
            UpdateInventory(repo, ctx).execute(inventory_id=uuid.uuid4())


class TestStockOperations:
    def _wi(self, repo: FakeWarehouseInventoryRepository) -> WarehouseInventory:
        wi = WarehouseInventory(id=uuid.uuid4(), inventory_id=uuid.uuid4(), warehouse_id=uuid.uuid4())
        repo.save(wi)
        return wi

    def _confirm_incoming(self, repo: FakeWarehouseInventoryRepository, warehouse_inventory_id, quantity: int) -> None:
        """Test helper: loads, confirms incoming->available, and saves -- used by tests that need AVAILABLE stock to already exist before exercising the operation under test."""
        wi = repo.get_by_id(warehouse_inventory_id)
        wi.confirm_incoming(StockQuantity(quantity), "PO-001", datetime.utcnow())
        repo.save(wi)

    def test_receive_stock(self):
        repo = FakeWarehouseInventoryRepository()
        wi = self._wi(repo)
        ctx, events = _ctx()

        updated = ReceiveStock(repo, ctx).execute(warehouse_inventory_id=wi.id, quantity=10, reference="PO-001")
        assert updated.get_quantity(StockStatus.INCOMING) == 10
        assert any(e[0] == "StockReceived" for e in events)

    def test_reserve_stock_insufficient_raises(self):
        repo = FakeWarehouseInventoryRepository()
        wi = self._wi(repo)
        ctx, _ = _ctx()
        with pytest.raises(InsufficientStock):
            ReserveStock(repo, ctx).execute(warehouse_inventory_id=wi.id, quantity=5, reference="RSV-001")

    def test_reserve_then_release(self):
        repo = FakeWarehouseInventoryRepository()
        wi = self._wi(repo)
        ctx, _ = _ctx()

        ReceiveStock(repo, ctx).execute(warehouse_inventory_id=wi.id, quantity=10, reference="PO-001")
        self._confirm_incoming(repo, wi.id, 10)

        ReserveStock(repo, ctx).execute(warehouse_inventory_id=wi.id, quantity=4, reference="RSV-001")
        released = ReleaseReservation(repo, ctx).execute(warehouse_inventory_id=wi.id, quantity=4, reference="RSV-001")
        assert released.available_quantity == 10
        assert released.reserved_quantity == 0

    def test_transfer_requires_distinct_warehouses(self):
        repo = FakeWarehouseInventoryRepository()
        wi = self._wi(repo)
        ctx, _ = _ctx()
        with pytest.raises(Exception):
            TransferStock(repo, ctx).execute(source_warehouse_inventory_id=wi.id, destination_warehouse_inventory_id=wi.id, quantity=1, reference="TRF-001")

    def test_adjust_stock_reason_mismatch_raises(self):
        repo = FakeWarehouseInventoryRepository()
        wi = self._wi(repo)
        ctx, _ = _ctx()
        with pytest.raises(Exception):
            AdjustStock(repo, ctx).execute(warehouse_inventory_id=wi.id, stock_status="available", quantity_delta=5, reason="damage", reference="ADJ-001")

    def test_damage_and_expire_stock(self):
        repo = FakeWarehouseInventoryRepository()
        wi = self._wi(repo)
        ctx, events = _ctx()

        ReceiveStock(repo, ctx).execute(warehouse_inventory_id=wi.id, quantity=10, reference="PO-001")
        self._confirm_incoming(repo, wi.id, 10)

        damaged = DamageStock(repo, ctx).execute(warehouse_inventory_id=wi.id, quantity=3, reference="DMG-001")
        assert damaged.get_quantity(StockStatus.DAMAGED) == 3

        ExpireStock(repo, ctx).execute(warehouse_inventory_id=wi.id, quantity=2, reference="EXP-001")
        event_types = [e[0] for e in events]
        assert "StockDamaged" in event_types
        assert "StockExpired" in event_types
