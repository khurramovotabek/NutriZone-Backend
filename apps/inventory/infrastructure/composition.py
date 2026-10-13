"""
Composition root for the `inventory` module's interfaces layer.

Wires concrete `infrastructure/` implementations into `application/
services/` constructors -- matching every prior module's composition
root exactly. No service locator: every `build_*()` factory explicitly
constructs and returns one fully-wired object. No direct repository
instantiation is permitted outside this file, per this phase's
explicit instruction.
"""
from __future__ import annotations

import uuid

from apps.inventory.application.selectors import InventorySelector as ApplicationInventorySelector
from apps.inventory.application.services._shared import InventoryServiceContext
from apps.inventory.application.services.branch_transfers import TransferStockBetweenBranches
from apps.inventory.application.services.batch_and_serial import (
    CreateBatch, DeactivateSerial, DeleteBatch, RegisterSerial, UpdateBatch,
)
from apps.inventory.application.services.counting import (
    CompleteCycleCount, CompletePhysicalInventory, StartCycleCount, StartPhysicalInventory,
)
from apps.inventory.application.services.lifecycle import ArchiveInventory, CreateInventory, RestoreInventory, UpdateInventory
from apps.inventory.application.services.queries import AdminListInventory, GetInventory, ListInventory, SearchInventory
from apps.inventory.application.services.reservations import CancelReservation, CreateReservation, ExpireReservation
from apps.inventory.application.services.snapshots_and_ledger import CreateSnapshot, RebuildLedger, RestoreSnapshot
from apps.inventory.application.services.stock_operations import (
    AdjustStock, ConfirmIncomingStock, DamageStock, ExpireStock, ReceiveStock, ReleaseReservation, ReserveStock, TransferStock,
)
from apps.inventory.infrastructure import models as orm
from apps.inventory.infrastructure.repositories import (
    DjangoAdjustmentRepository, DjangoBatchRepository, DjangoCycleCountRepository, DjangoInventoryRepository,
    DjangoLedgerRepository, DjangoMovementRepository, DjangoPhysicalInventoryRepository, DjangoReservationRepository,
    DjangoSerialRepository, DjangoShelfInventoryRepository, DjangoSnapshotRepository, DjangoStockTransferRepository,
    DjangoWarehouseInventoryRepository,
)
from apps.inventory.infrastructure.selectors import DjangoInventorySearchBackend
from core.outbox import stage_event


def stage_inventory_events(events: list[tuple[str, dict]]) -> None:
    """The `stage_events` callable every Inventory Application Service is constructed with -- the concrete Outbox-aware implementation, kept out of `application/` per Clean Architecture."""
    for event_type, payload in events:
        stage_event(orm.InventoryOutboxEvent, event_type, payload)


def build_inventory_service_context(actor_id: uuid.UUID | None = None) -> InventoryServiceContext:
    return InventoryServiceContext(stage_events=stage_inventory_events, actor_id=actor_id)


# --- Repositories (also directly exposed for read-only reference-data
# lookups the future Interfaces layer needs, so no view ever
# instantiates one directly -- the fix already applied pre-emptively
# in Store's Phase 2, applied identically here). ---------------------

def build_inventory_repository() -> DjangoInventoryRepository:
    return DjangoInventoryRepository()


def build_warehouse_inventory_repository() -> DjangoWarehouseInventoryRepository:
    return DjangoWarehouseInventoryRepository()


def build_shelf_inventory_repository() -> DjangoShelfInventoryRepository:
    return DjangoShelfInventoryRepository()


def build_reservation_repository() -> DjangoReservationRepository:
    return DjangoReservationRepository()


def build_movement_repository() -> DjangoMovementRepository:
    return DjangoMovementRepository()


def build_adjustment_repository() -> DjangoAdjustmentRepository:
    return DjangoAdjustmentRepository()


def build_ledger_repository() -> DjangoLedgerRepository:
    return DjangoLedgerRepository()


def build_batch_repository() -> DjangoBatchRepository:
    return DjangoBatchRepository()


def build_serial_repository() -> DjangoSerialRepository:
    return DjangoSerialRepository()


def build_snapshot_repository() -> DjangoSnapshotRepository:
    return DjangoSnapshotRepository()


def build_cycle_count_repository() -> DjangoCycleCountRepository:
    return DjangoCycleCountRepository()


def build_physical_inventory_repository() -> DjangoPhysicalInventoryRepository:
    return DjangoPhysicalInventoryRepository()


def build_inventory_selector() -> ApplicationInventorySelector:
    return ApplicationInventorySelector(DjangoInventorySearchBackend())


# --- Lifecycle -----------------------------------------------------------

def build_create_inventory(actor_id=None) -> CreateInventory:
    return CreateInventory(DjangoInventoryRepository(), build_inventory_service_context(actor_id))


def build_update_inventory(actor_id=None) -> UpdateInventory:
    return UpdateInventory(DjangoInventoryRepository(), build_inventory_service_context(actor_id))


def build_archive_inventory(actor_id=None) -> ArchiveInventory:
    return ArchiveInventory(DjangoInventoryRepository(), build_inventory_service_context(actor_id))


def build_restore_inventory(actor_id=None) -> RestoreInventory:
    return RestoreInventory(DjangoInventoryRepository(), build_inventory_service_context(actor_id))


# --- Stock operations --------------------------------------------------

def build_receive_stock(actor_id=None) -> ReceiveStock:
    return ReceiveStock(DjangoWarehouseInventoryRepository(), build_inventory_service_context(actor_id))


def build_confirm_incoming_stock(actor_id=None) -> ConfirmIncomingStock:
    return ConfirmIncomingStock(DjangoWarehouseInventoryRepository(), build_inventory_service_context(actor_id))


def build_reserve_stock(actor_id=None) -> ReserveStock:
    return ReserveStock(DjangoWarehouseInventoryRepository(), build_inventory_service_context(actor_id))


def build_release_reservation(actor_id=None) -> ReleaseReservation:
    return ReleaseReservation(DjangoWarehouseInventoryRepository(), build_inventory_service_context(actor_id))


def build_transfer_stock(actor_id=None) -> TransferStock:
    return TransferStock(DjangoWarehouseInventoryRepository(), build_inventory_service_context(actor_id))


def build_transfer_between_branches(actor_id=None) -> TransferStockBetweenBranches:
    return TransferStockBetweenBranches(DjangoWarehouseInventoryRepository(), DjangoStockTransferRepository(), build_inventory_service_context(actor_id))


def build_adjust_stock(actor_id=None) -> AdjustStock:
    return AdjustStock(DjangoWarehouseInventoryRepository(), build_inventory_service_context(actor_id))


def build_damage_stock(actor_id=None) -> DamageStock:
    return DamageStock(DjangoWarehouseInventoryRepository(), build_inventory_service_context(actor_id))


def build_expire_stock(actor_id=None) -> ExpireStock:
    return ExpireStock(DjangoWarehouseInventoryRepository(), build_inventory_service_context(actor_id))


# --- Batch / Serial ----------------------------------------------------

def build_batch_service(actor_id=None) -> CreateBatch:
    """Named to match this phase's explicit `build_batch_service()` factory list -- returns the primary batch-creation service; UpdateBatch/DeleteBatch have their own dedicated factories below for the remaining CRUD operations."""
    return CreateBatch(DjangoBatchRepository(), DjangoInventoryRepository(), build_inventory_service_context(actor_id))


def build_update_batch(actor_id=None) -> UpdateBatch:
    return UpdateBatch(DjangoBatchRepository(), build_inventory_service_context(actor_id))


def build_delete_batch(actor_id=None) -> DeleteBatch:
    return DeleteBatch(DjangoBatchRepository(), build_inventory_service_context(actor_id))


def build_register_serial(actor_id=None) -> RegisterSerial:
    return RegisterSerial(DjangoBatchRepository(), DjangoSerialRepository(), build_inventory_service_context(actor_id))


def build_deactivate_serial(actor_id=None) -> DeactivateSerial:
    return DeactivateSerial(DjangoBatchRepository(), build_inventory_service_context(actor_id))


# --- Reservations -----------------------------------------------------

def build_create_reservation(actor_id=None) -> CreateReservation:
    return CreateReservation(DjangoReservationRepository(), DjangoWarehouseInventoryRepository(), build_inventory_service_context(actor_id))


def build_cancel_reservation(actor_id=None) -> CancelReservation:
    return CancelReservation(DjangoReservationRepository(), DjangoWarehouseInventoryRepository(), build_inventory_service_context(actor_id))


def build_expire_reservation(actor_id=None) -> ExpireReservation:
    return ExpireReservation(DjangoReservationRepository(), DjangoWarehouseInventoryRepository(), build_inventory_service_context(actor_id))


# --- Counting ------------------------------------------------------------

def build_cycle_count_service(actor_id=None) -> StartCycleCount:
    """Named to match this phase's explicit factory list -- returns the start-service; CompleteCycleCount has its own dedicated factory below."""
    return StartCycleCount(DjangoCycleCountRepository(), build_inventory_service_context(actor_id))


def build_complete_cycle_count(actor_id=None) -> CompleteCycleCount:
    return CompleteCycleCount(DjangoCycleCountRepository(), DjangoWarehouseInventoryRepository(), build_inventory_service_context(actor_id))


def build_physical_inventory_service(actor_id=None) -> StartPhysicalInventory:
    """Named to match this phase's explicit factory list -- returns the start-service; CompletePhysicalInventory has its own dedicated factory below."""
    return StartPhysicalInventory(DjangoPhysicalInventoryRepository(), build_inventory_service_context(actor_id))


def build_complete_physical_inventory(actor_id=None) -> CompletePhysicalInventory:
    return CompletePhysicalInventory(DjangoPhysicalInventoryRepository(), DjangoWarehouseInventoryRepository(), build_inventory_service_context(actor_id))


# --- Snapshots / Ledger -----------------------------------------------

def build_snapshot_service(actor_id=None) -> CreateSnapshot:
    """Named to match this phase's explicit factory list -- returns the create-service; RestoreSnapshot has its own dedicated factory below."""
    return CreateSnapshot(DjangoSnapshotRepository(), DjangoWarehouseInventoryRepository(), build_inventory_service_context(actor_id))


def build_create_snapshot(actor_id=None) -> CreateSnapshot:
    return CreateSnapshot(DjangoSnapshotRepository(), DjangoWarehouseInventoryRepository(), build_inventory_service_context(actor_id))


def build_restore_snapshot(actor_id=None) -> RestoreSnapshot:
    return RestoreSnapshot(DjangoSnapshotRepository(), DjangoWarehouseInventoryRepository(), build_inventory_service_context(actor_id))


def build_rebuild_ledger(actor_id=None) -> RebuildLedger:
    return RebuildLedger(DjangoLedgerRepository(), build_inventory_service_context(actor_id))


# --- Queries --------------------------------------------------------------

def build_get_inventory() -> GetInventory:
    return GetInventory(DjangoInventoryRepository())


def build_list_inventory() -> ListInventory:
    return ListInventory(DjangoInventoryRepository())


def build_admin_list_inventory() -> AdminListInventory:
    return AdminListInventory(DjangoInventoryRepository())


def build_search_inventory() -> SearchInventory:
    return SearchInventory(DjangoInventorySearchBackend())
