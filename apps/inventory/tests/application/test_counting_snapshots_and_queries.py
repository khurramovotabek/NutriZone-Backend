from __future__ import annotations

import uuid

import pytest

from apps.inventory.application.services._shared import InventoryServiceContext
from apps.inventory.application.services.counting import (
    CompleteCycleCount, CompletePhysicalInventory, StartCycleCount, StartPhysicalInventory,
)
from apps.inventory.application.services.queries import AdminListInventory, GetInventory, ListInventory
from apps.inventory.application.services.snapshots_and_ledger import CreateSnapshot, RebuildLedger
from apps.inventory.domain.aggregates import Inventory, WarehouseInventory
from apps.inventory.domain.enums import InventoryStatus
from apps.inventory.domain.value_objects import InventoryCode
from apps.inventory.tests.application.fakes import (
    FakeCycleCountRepository, FakeInventoryRepository, FakeLedgerRepository, FakePhysicalInventoryRepository,
    FakeSnapshotRepository, FakeWarehouseInventoryRepository, collect_events,
)
from common.exceptions import ResourceNotFound

pytestmark = pytest.mark.django_db


def _ctx():
    events: list = []
    return InventoryServiceContext(stage_events=collect_events(events), actor_id=uuid.uuid4()), events


class TestCycleCountServices:
    def test_start_and_complete(self):
        repo = FakeCycleCountRepository()
        wi_repo = FakeWarehouseInventoryRepository()
        ctx, events = _ctx()

        cycle_count = StartCycleCount(repo, ctx).execute(uuid.uuid4())
        assert cycle_count.status.value == "in_progress"

        completed = CompleteCycleCount(repo, wi_repo, ctx).execute(cycle_count_id=cycle_count.id, counted_quantities={uuid.uuid4(): 10})
        assert completed.status.value == "completed"
        event_types = [e[0] for e in events]
        assert "CycleCountStarted" in event_types
        assert "CycleCountCompleted" in event_types

    def test_complete_missing_cycle_count_raises(self):
        ctx, _ = _ctx()
        with pytest.raises(ResourceNotFound):
            CompleteCycleCount(FakeCycleCountRepository(), FakeWarehouseInventoryRepository(), ctx).execute(cycle_count_id=uuid.uuid4(), counted_quantities={})


class TestPhysicalInventoryServices:
    def test_start_and_complete(self):
        repo = FakePhysicalInventoryRepository()
        wi_repo = FakeWarehouseInventoryRepository()
        ctx, events = _ctx()

        physical_inventory = StartPhysicalInventory(repo, ctx).execute(uuid.uuid4())
        assert physical_inventory.status.value == "in_progress"

        completed = CompletePhysicalInventory(repo, wi_repo, ctx).execute(physical_inventory_id=physical_inventory.id, counted_quantities={uuid.uuid4(): 5})
        assert completed.status.value == "completed"
        event_types = [e[0] for e in events]
        assert "PhysicalInventoryStarted" in event_types
        assert "PhysicalInventoryCompleted" in event_types


class TestSnapshotAndLedgerServices:
    def test_create_snapshot(self):
        snapshot_repo = FakeSnapshotRepository()
        wi_repo = FakeWarehouseInventoryRepository()
        wi = WarehouseInventory(id=uuid.uuid4(), inventory_id=uuid.uuid4(), warehouse_id=uuid.uuid4())
        wi_repo.save(wi)
        ctx, events = _ctx()

        snapshot = CreateSnapshot(snapshot_repo, wi_repo, ctx).execute([wi.id])
        assert snapshot.version.value == 1
        assert snapshot.status.value == "completed"
        assert any(e[0] == "InventorySnapshotCreated" for e in events)

    def test_create_snapshot_versions_increment(self):
        snapshot_repo = FakeSnapshotRepository()
        wi_repo = FakeWarehouseInventoryRepository()
        ctx, _ = _ctx()

        first = CreateSnapshot(snapshot_repo, wi_repo, ctx).execute([])
        second = CreateSnapshot(snapshot_repo, wi_repo, ctx).execute([])
        assert second.version.value == first.version.value + 1

    def test_rebuild_ledger_verifies_balance(self):
        ledger_repo = FakeLedgerRepository()
        wi_id = uuid.uuid4()
        ledger_repo.entries = [
            {"warehouse_inventory_id": wi_id, "stock_status": "available", "quantity_delta": 10, "balance_after": 10},
            {"warehouse_inventory_id": wi_id, "stock_status": "available", "quantity_delta": -3, "balance_after": 7},
        ]
        ctx, _ = _ctx()

        is_balanced = RebuildLedger(ledger_repo, ctx).execute(wi_id, "available")
        assert is_balanced is True

    def test_rebuild_ledger_detects_corruption(self):
        ledger_repo = FakeLedgerRepository()
        wi_id = uuid.uuid4()
        ledger_repo.entries = [
            {"warehouse_inventory_id": wi_id, "stock_status": "available", "quantity_delta": 10, "balance_after": 999},
        ]
        ctx, _ = _ctx()

        is_balanced = RebuildLedger(ledger_repo, ctx).execute(wi_id, "available")
        assert is_balanced is False


class TestQueryServices:
    def test_get_inventory_returns_active_only(self):
        repo = FakeInventoryRepository()
        inventory = Inventory(id=uuid.uuid4(), code=InventoryCode("WHEY005"), product_variant_id=uuid.uuid4(), status=InventoryStatus.ARCHIVED)
        repo.save(inventory)
        with pytest.raises(ResourceNotFound):
            GetInventory(repo).execute("WHEY005")

    def test_get_inventory_returns_active(self):
        repo = FakeInventoryRepository()
        inventory = Inventory(id=uuid.uuid4(), code=InventoryCode("WHEY006"), product_variant_id=uuid.uuid4())
        repo.save(inventory)
        found = GetInventory(repo).execute("WHEY006")
        assert found.id == inventory.id

    def test_list_inventory_filters_active(self):
        repo = FakeInventoryRepository()
        repo.save(Inventory(id=uuid.uuid4(), code=InventoryCode("WHEY007"), product_variant_id=uuid.uuid4()))
        results, total = ListInventory(repo).execute()
        assert total == 1

    def test_admin_list_inventory_returns_all_statuses(self):
        repo = FakeInventoryRepository()
        repo.save(Inventory(id=uuid.uuid4(), code=InventoryCode("WHEY008"), product_variant_id=uuid.uuid4(), status=InventoryStatus.ARCHIVED))
        results, total = AdminListInventory(repo).execute()
        assert total == 1
