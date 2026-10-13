"""
Inventory Count Application Services: StartCycleCount,
CompleteCycleCount, StartPhysicalInventory, CompletePhysicalInventory.
"""
from __future__ import annotations

import uuid

from django.db import transaction

from apps.inventory.application.ports import CycleCountRepository, PhysicalInventoryRepository, WarehouseInventoryRepository
from apps.inventory.application.services._shared import InventoryServiceContext
from apps.inventory.domain.aggregates import CycleCount, PhysicalInventory
from common.exceptions import ResourceNotFound


class StartCycleCount:
    def __init__(self, repo: CycleCountRepository, ctx: InventoryServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, warehouse_id: uuid.UUID) -> CycleCount:
        cycle_count = CycleCount(id=uuid.uuid4(), warehouse_id=warehouse_id)
        event = cycle_count.start()
        saved = self._repo.save(cycle_count)

        self._ctx.stage_events([("CycleCountStarted", event.to_payload())])
        self._ctx.audit().created(entity_type="CycleCount", entity_id=str(saved.id), after={"warehouse_id": str(warehouse_id)})
        self._ctx.metric("cycle_counts_started_total")
        return saved


class CompleteCycleCount:
    def __init__(self, repo: CycleCountRepository, warehouse_inventory_repo: WarehouseInventoryRepository, ctx: InventoryServiceContext) -> None:
        self._repo = repo
        self._warehouse_inventory_repo = warehouse_inventory_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, cycle_count_id: uuid.UUID, counted_quantities: dict[uuid.UUID, int]) -> CycleCount:
        cycle_count = self._repo.get_by_id(cycle_count_id)
        if cycle_count is None:
            raise ResourceNotFound("Cycle count not found.")

        for inventory_id, quantity in counted_quantities.items():
            cycle_count.record_count(inventory_id, quantity)

        expected = {inv_id: wi.available_quantity for inv_id, wi in ((i, self._warehouse_inventory_repo.get_by_inventory_and_warehouse(i, cycle_count.warehouse_id)) for i in counted_quantities) if wi is not None}
        event = cycle_count.complete(expected)
        saved = self._repo.save(cycle_count)

        self._ctx.stage_events([("CycleCountCompleted", event.to_payload())])
        self._ctx.audit().updated(entity_type="CycleCount", entity_id=str(cycle_count_id), before={}, after={"discrepancy_count": event.discrepancy_count})
        self._ctx.metric("cycle_counts_completed_total")
        return saved


class StartPhysicalInventory:
    def __init__(self, repo: PhysicalInventoryRepository, ctx: InventoryServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, warehouse_id: uuid.UUID) -> PhysicalInventory:
        physical_inventory = PhysicalInventory(id=uuid.uuid4(), warehouse_id=warehouse_id)
        event = physical_inventory.start()
        saved = self._repo.save(physical_inventory)

        self._ctx.stage_events([("PhysicalInventoryStarted", event.to_payload())])
        self._ctx.audit().created(entity_type="PhysicalInventory", entity_id=str(saved.id), after={"warehouse_id": str(warehouse_id)})
        self._ctx.metric("physical_inventories_started_total")
        return saved


class CompletePhysicalInventory:
    def __init__(self, repo: PhysicalInventoryRepository, warehouse_inventory_repo: WarehouseInventoryRepository, ctx: InventoryServiceContext) -> None:
        self._repo = repo
        self._warehouse_inventory_repo = warehouse_inventory_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, physical_inventory_id: uuid.UUID, counted_quantities: dict[uuid.UUID, int]) -> PhysicalInventory:
        physical_inventory = self._repo.get_by_id(physical_inventory_id)
        if physical_inventory is None:
            raise ResourceNotFound("Physical inventory not found.")

        for inventory_id, quantity in counted_quantities.items():
            physical_inventory.record_count(inventory_id, quantity)

        expected = {inv_id: wi.available_quantity for inv_id, wi in ((i, self._warehouse_inventory_repo.get_by_inventory_and_warehouse(i, physical_inventory.warehouse_id)) for i in counted_quantities) if wi is not None}
        event = physical_inventory.complete(expected)
        saved = self._repo.save(physical_inventory)

        self._ctx.stage_events([("PhysicalInventoryCompleted", event.to_payload())])
        self._ctx.audit().updated(entity_type="PhysicalInventory", entity_id=str(physical_inventory_id), before={}, after={"discrepancy_count": event.discrepancy_count})
        self._ctx.metric("physical_inventories_completed_total")
        return saved
