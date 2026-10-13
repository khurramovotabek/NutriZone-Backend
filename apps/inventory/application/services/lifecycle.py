"""
Inventory lifecycle Application Services: CreateInventory,
UpdateInventory, ArchiveInventory, RestoreInventory.
"""
from __future__ import annotations

import uuid

from django.db import transaction

from apps.inventory.application.ports import InventoryRepository
from apps.inventory.application.services._shared import InventoryServiceContext
from apps.inventory.domain.aggregates import Inventory
from apps.inventory.domain.value_objects import InventoryCode, StockThreshold
from common.exceptions import ResourceNotFound


class CreateInventory:
    def __init__(self, repo: InventoryRepository, ctx: InventoryServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, code: str, product_variant_id: uuid.UUID, is_batch_tracked: bool = False, is_serial_tracked: bool = False) -> Inventory:
        with self._ctx.timer("inventory_create_duration"):
            if self._repo.code_exists(code):
                from common.exceptions import ConflictError

                raise ConflictError(f"Inventory code '{code}' already exists.")
            if self._repo.get_by_product_variant(product_variant_id) is not None:
                from common.exceptions import ConflictError

                raise ConflictError(f"An inventory record already exists for product variant '{product_variant_id}'.")

            inventory = Inventory(id=uuid.uuid4(), code=InventoryCode(code), product_variant_id=product_variant_id, is_batch_tracked=is_batch_tracked, is_serial_tracked=is_serial_tracked)
            saved = self._repo.save(inventory)

            from apps.inventory.domain.events import InventoryCreated

            self._ctx.stage_events([("InventoryCreated", InventoryCreated(inventory_id=saved.id, code=code, product_variant_id=product_variant_id).to_payload())])
            self._ctx.audit().created(entity_type="Inventory", entity_id=str(saved.id), after={"code": code, "product_variant_id": str(product_variant_id)})
            self._ctx.invalidate_inventory_cache()
            self._ctx.metric("inventory_items_created_total")
            return saved


class UpdateInventory:
    def __init__(self, repo: InventoryRepository, ctx: InventoryServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, inventory_id: uuid.UUID, low_stock_at: int | None = None, reorder_at: int | None = None, overstock_at: int | None = None) -> Inventory:
        inventory = self._repo.get_by_id(inventory_id)
        if inventory is None:
            raise ResourceNotFound("Inventory not found.")

        threshold = None
        if low_stock_at is not None and reorder_at is not None:
            threshold = StockThreshold(low_stock_at=low_stock_at, reorder_at=reorder_at, overstock_at=overstock_at)

        event = inventory.update(threshold=threshold)
        saved = self._repo.save(inventory)

        self._ctx.stage_events([("InventoryUpdated", event.to_payload())])
        self._ctx.audit().updated(entity_type="Inventory", entity_id=str(inventory_id), before=event.before, after=event.after)
        self._ctx.invalidate_inventory_cache()
        self._ctx.metric("inventory_items_updated_total")
        return saved


class ArchiveInventory:
    def __init__(self, repo: InventoryRepository, ctx: InventoryServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, inventory_id: uuid.UUID) -> Inventory:
        inventory = self._repo.get_by_id(inventory_id)
        if inventory is None:
            raise ResourceNotFound("Inventory not found.")

        event = inventory.archive()
        saved = self._repo.save(inventory)

        self._ctx.stage_events([("InventoryArchivedEvent", event.to_payload())])
        self._ctx.audit().updated(entity_type="Inventory", entity_id=str(inventory_id), before={}, after={"status": "archived"})
        self._ctx.invalidate_inventory_cache()
        return saved


class RestoreInventory:
    def __init__(self, repo: InventoryRepository, ctx: InventoryServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, inventory_id: uuid.UUID) -> Inventory:
        inventory = self._repo.get_by_id(inventory_id)
        if inventory is None:
            raise ResourceNotFound("Inventory not found.")

        event = inventory.restore()
        saved = self._repo.save(inventory)

        self._ctx.stage_events([("InventoryRestored", event.to_payload())])
        self._ctx.audit().updated(entity_type="Inventory", entity_id=str(inventory_id), before={}, after={"status": "active"})
        self._ctx.invalidate_inventory_cache()
        return saved
