"""
Snapshot & Ledger Application Services: CreateSnapshot, RestoreSnapshot,
RebuildLedger.
"""
from __future__ import annotations

import uuid

from django.db import transaction
from django.utils import timezone as django_timezone

from apps.inventory.application.ports import LedgerRepository, SnapshotRepository, WarehouseInventoryRepository
from apps.inventory.application.services._shared import InventoryServiceContext
from apps.inventory.domain.aggregates import InventorySnapshot
from apps.inventory.domain.entities import StockSnapshot
from apps.inventory.domain.enums import StockStatus
from apps.inventory.domain.services import LedgerPolicy, SnapshotPolicy
from apps.inventory.domain.value_objects import SnapshotVersion
from common.exceptions import ResourceNotFound


class CreateSnapshot:
    def __init__(self, snapshot_repo: SnapshotRepository, warehouse_inventory_repo: WarehouseInventoryRepository, ctx: InventoryServiceContext) -> None:
        self._snapshot_repo = snapshot_repo
        self._warehouse_inventory_repo = warehouse_inventory_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, warehouse_inventory_ids: list[uuid.UUID]) -> InventorySnapshot:
        latest_version = self._snapshot_repo.get_latest_version()
        new_version = SnapshotVersion(latest_version + 1)
        SnapshotPolicy.assert_monotonic_version(new_version.value, latest_version)

        snapshot = InventorySnapshot(id=uuid.uuid4(), version=new_version)
        for wi_id in warehouse_inventory_ids:
            wi = self._warehouse_inventory_repo.get_by_id(wi_id)
            if wi is None:
                continue
            snapshot.add_item(StockSnapshot(id=uuid.uuid4(), inventory_id=wi.inventory_id, quantities_by_status={s.value: wi.get_quantity(s) for s in StockStatus}))

        event = snapshot.complete(django_timezone.now())
        saved = self._snapshot_repo.save(snapshot)

        self._ctx.stage_events([("InventorySnapshotCreated", event.to_payload())])
        self._ctx.audit().created(entity_type="InventorySnapshot", entity_id=str(saved.id), after={"version": new_version.value, "item_count": len(snapshot.items)})
        self._ctx.metric("inventory_snapshots_created_total")
        return saved


class RestoreSnapshot:
    """Restores WarehouseInventory quantities from a completed snapshot -- an explicitly destructive, staff-only administrative action (overwrites current live balances), never invoked by a normal stock-operation flow."""

    def __init__(self, snapshot_repo: SnapshotRepository, warehouse_inventory_repo: WarehouseInventoryRepository, ctx: InventoryServiceContext) -> None:
        self._snapshot_repo = snapshot_repo
        self._warehouse_inventory_repo = warehouse_inventory_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, snapshot_id: uuid.UUID, warehouse_id: uuid.UUID) -> int:
        snapshot = self._snapshot_repo.get_by_id(snapshot_id)
        if snapshot is None:
            raise ResourceNotFound("Snapshot not found.")

        restored_count = 0
        for item in snapshot.items.values():
            wi = self._warehouse_inventory_repo.get_by_inventory_and_warehouse(item.inventory_id, warehouse_id)
            if wi is None:
                continue
            for status_value, quantity in item.quantities_by_status.items():
                wi.quantities[StockStatus(status_value)] = quantity
            self._warehouse_inventory_repo.save(wi)
            restored_count += 1

        self._ctx.audit().updated(entity_type="InventorySnapshot", entity_id=str(snapshot_id), before={}, after={"restored_count": restored_count, "warehouse_id": str(warehouse_id)})
        self._ctx.invalidate_inventory_cache()
        self._ctx.metric("inventory_snapshots_restored_total")
        return restored_count


class RebuildLedger:
    """
    Verifies (and, in the event of drift, reports) that a
    WarehouseInventory's recorded balance matches what replaying its
    full `InventoryLedger` entry history produces -- the "ledger
    balancing" domain rule, exercised as an explicit, on-demand
    reconciliation operation rather than only checked implicitly on
    every write.
    """

    def __init__(self, ledger_repo: LedgerRepository, ctx: InventoryServiceContext) -> None:
        self._ledger_repo = ledger_repo
        self._ctx = ctx

    def execute(self, warehouse_inventory_id: uuid.UUID, stock_status: str) -> bool:
        entries = self._ledger_repo.list_entries(warehouse_inventory_id, stock_status=stock_status)
        deltas = [e["quantity_delta"] for e in entries]
        claimed_balance = self._ledger_repo.get_latest_balance(warehouse_inventory_id, stock_status)

        is_balanced = LedgerPolicy.verify_balance(deltas, claimed_balance)
        self._ctx.metric("ledger_rebuild_checks_total", result="balanced" if is_balanced else "corrupted")
        return is_balanced
