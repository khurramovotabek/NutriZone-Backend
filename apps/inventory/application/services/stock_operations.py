"""
Stock Operations Application Services: ReceiveStock, ReserveStock,
ReleaseReservation, TransferStock, AdjustStock, DamageStock,
ExpireStock.

Each wraps a `WarehouseInventory` domain method (aggregates.py), then
persists both the mutated aggregate AND the `InventoryTransaction`/
`InventoryLedger` entries that method returned -- the repository is
responsible for writing the ledger entries alongside the updated
balances (see infrastructure/repositories.py, Phase 2).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from django.db import transaction
from django.utils import timezone as django_timezone

from apps.inventory.application.ports import WarehouseInventoryRepository
from apps.inventory.application.services._shared import InventoryServiceContext
from apps.inventory.domain.aggregates import WarehouseInventory
from apps.inventory.domain.enums import StockStatus
from apps.inventory.domain.services import AdjustmentPolicy, MovementPolicy
from apps.inventory.domain.value_objects import StockQuantity
from common.exceptions import ResourceNotFound


def _now() -> datetime:
    return django_timezone.now()


class ConfirmIncomingStock:
    """
    Phase 02F: closes a confirmed gap -- `WarehouseInventory.
    confirm_incoming()` existed on the domain aggregate with zero
    Application Service callers before this phase (confirmed by
    repository-wide search). Moves INCOMING -> AVAILABLE, the only
    path stock takes into AVAILABLE from outside the system, per the
    domain method's own docstring.

    Uses `get_by_id_for_update()` (real `select_for_update()` locking)
    rather than the plain `get_by_id()` every sibling service in this
    file uses -- a deliberate, targeted addition for this specific
    operation, since Step 11 requires proven concurrency safety and
    the shared `save()`'s own `update_or_create()` has no true
    optimistic/pessimistic locking on its own (a pre-existing
    characteristic of every stock operation in this file, disclosed
    in the final report, not silently fixed here since correcting it
    for every sibling operation is outside this phase's own scope).

    Quantity integrity (Step 7) is enforced by the domain method
    itself (`InsufficientStock` if `quantity > incoming`) -- not
    re-implemented here, since duplicating that check at this layer
    would risk the two checks drifting out of sync over time.
    """

    def __init__(self, repo: WarehouseInventoryRepository, ctx: InventoryServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, warehouse_inventory_id: uuid.UUID, quantity: int, reference: str) -> WarehouseInventory:
        with self._ctx.timer("inventory_confirm_incoming_duration"):
            wi = self._repo.get_by_id_for_update(warehouse_inventory_id)
            if wi is None:
                raise ResourceNotFound("Warehouse inventory not found.")

            transaction_entity, ledger_entity = wi.confirm_incoming(StockQuantity(quantity), reference, _now())
            saved = self._repo.save(wi)
            self._repo.persist_transaction_and_ledger(warehouse_inventory_id, transaction_entity, ledger_entity)

            from apps.inventory.domain.events import StockConfirmed

            self._ctx.stage_events([("StockConfirmed", StockConfirmed(warehouse_inventory_id=warehouse_inventory_id, quantity=quantity, reference=reference).to_payload())])
            self._ctx.audit().updated(entity_type="WarehouseInventory", entity_id=str(warehouse_inventory_id), before={}, after={"confirmed": quantity, "reference": reference})
            self._ctx.invalidate_inventory_cache()
            self._ctx.metric("stock_confirmed_total", value=quantity)
            return saved


class ReceiveStock:
    def __init__(self, repo: WarehouseInventoryRepository, ctx: InventoryServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, warehouse_inventory_id: uuid.UUID, quantity: int, reference: str) -> WarehouseInventory:
        with self._ctx.timer("inventory_receive_duration"):
            wi = self._repo.get_by_id(warehouse_inventory_id)
            if wi is None:
                raise ResourceNotFound("Warehouse inventory not found.")

            transaction_entity, ledger_entity = wi.receive(StockQuantity(quantity), reference, _now())
            saved = self._repo.save(wi)
            self._repo.persist_transaction_and_ledger(warehouse_inventory_id, transaction_entity, ledger_entity)

            from apps.inventory.domain.events import StockReceived

            self._ctx.stage_events([("StockReceived", StockReceived(warehouse_inventory_id=warehouse_inventory_id, quantity=quantity, reference=reference).to_payload())])
            self._ctx.audit().updated(entity_type="WarehouseInventory", entity_id=str(warehouse_inventory_id), before={}, after={"received": quantity, "reference": reference})
            self._ctx.invalidate_inventory_cache()
            self._ctx.metric("stock_received_total", value=quantity)
            return saved


class ReserveStock:
    def __init__(self, repo: WarehouseInventoryRepository, ctx: InventoryServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, warehouse_inventory_id: uuid.UUID, quantity: int, reference: str) -> WarehouseInventory:
        wi = self._repo.get_by_id(warehouse_inventory_id)
        if wi is None:
            raise ResourceNotFound("Warehouse inventory not found.")

        transaction_entity, ledger_entity = wi.reserve(StockQuantity(quantity), reference, _now())
        saved = self._repo.save(wi)
        self._repo.persist_transaction_and_ledger(warehouse_inventory_id, transaction_entity, ledger_entity)

        self._ctx.audit().updated(entity_type="WarehouseInventory", entity_id=str(warehouse_inventory_id), before={}, after={"reserved": quantity})
        self._ctx.invalidate_inventory_cache()
        self._ctx.metric("stock_reserved_total", value=quantity)
        return saved


class ReleaseReservation:
    def __init__(self, repo: WarehouseInventoryRepository, ctx: InventoryServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, warehouse_inventory_id: uuid.UUID, quantity: int, reference: str) -> WarehouseInventory:
        wi = self._repo.get_by_id(warehouse_inventory_id)
        if wi is None:
            raise ResourceNotFound("Warehouse inventory not found.")

        transaction_entity, ledger_entity = wi.release_reservation(StockQuantity(quantity), reference, _now())
        saved = self._repo.save(wi)
        self._repo.persist_transaction_and_ledger(warehouse_inventory_id, transaction_entity, ledger_entity)

        self._ctx.audit().updated(entity_type="WarehouseInventory", entity_id=str(warehouse_inventory_id), before={}, after={"released": quantity})
        self._ctx.invalidate_inventory_cache()
        return saved


class TransferStock:
    def __init__(self, repo: WarehouseInventoryRepository, ctx: InventoryServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, source_warehouse_inventory_id: uuid.UUID, destination_warehouse_inventory_id: uuid.UUID, quantity: int, reference: str) -> tuple[WarehouseInventory, WarehouseInventory]:
        MovementPolicy.assert_transfer_has_distinct_endpoints(source_warehouse_inventory_id, destination_warehouse_inventory_id)

        source = self._repo.get_by_id(source_warehouse_inventory_id)
        if source is None:
            raise ResourceNotFound("Source warehouse inventory not found.")
        destination = self._repo.get_by_id(destination_warehouse_inventory_id)
        if destination is None:
            raise ResourceNotFound("Destination warehouse inventory not found.")

        now = _now()
        source_transaction, source_ledger = source.transfer_out(StockQuantity(quantity), reference, now)
        destination_transaction, destination_ledger = destination.receive_transfer_in(StockQuantity(quantity), reference, now)

        saved_source = self._repo.save(source)
        saved_destination = self._repo.save(destination)
        self._repo.persist_transaction_and_ledger(source_warehouse_inventory_id, source_transaction, source_ledger)
        self._repo.persist_transaction_and_ledger(destination_warehouse_inventory_id, destination_transaction, destination_ledger)

        from apps.inventory.domain.events import StockTransferred

        self._ctx.stage_events([("StockTransferred", StockTransferred(source_warehouse_inventory_id=source_warehouse_inventory_id, destination_warehouse_inventory_id=destination_warehouse_inventory_id, quantity=quantity).to_payload())])
        self._ctx.audit().updated(entity_type="WarehouseInventory", entity_id=str(source_warehouse_inventory_id), before={}, after={"transferred_out": quantity, "to": str(destination_warehouse_inventory_id)})
        self._ctx.invalidate_inventory_cache()
        self._ctx.metric("stock_transferred_total", value=quantity)
        return saved_source, saved_destination


class AdjustStock:
    def __init__(self, repo: WarehouseInventoryRepository, ctx: InventoryServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, warehouse_inventory_id: uuid.UUID, stock_status: str, quantity_delta: int, reason: str, reference: str) -> WarehouseInventory:
        AdjustmentPolicy.assert_reason_is_justified(reason, quantity_delta)

        wi = self._repo.get_by_id(warehouse_inventory_id)
        if wi is None:
            raise ResourceNotFound("Warehouse inventory not found.")

        transaction_entity, ledger_entity = wi.adjust(StockStatus(stock_status), quantity_delta, reference, _now())
        saved = self._repo.save(wi)
        self._repo.persist_transaction_and_ledger(warehouse_inventory_id, transaction_entity, ledger_entity)

        from apps.inventory.domain.events import StockAdjusted

        adjustment_id = uuid.uuid4()
        self._ctx.stage_events([("StockAdjusted", StockAdjusted(adjustment_id=adjustment_id, warehouse_inventory_id=warehouse_inventory_id, quantity_delta=quantity_delta, reason=reason).to_payload())])
        self._ctx.audit().updated(entity_type="WarehouseInventory", entity_id=str(warehouse_inventory_id), before={}, after={"adjustment": quantity_delta, "reason": reason})
        self._ctx.invalidate_inventory_cache()
        self._ctx.metric("stock_adjustments_total")
        return saved


class DamageStock:
    def __init__(self, repo: WarehouseInventoryRepository, ctx: InventoryServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, warehouse_inventory_id: uuid.UUID, quantity: int, reference: str) -> WarehouseInventory:
        wi = self._repo.get_by_id(warehouse_inventory_id)
        if wi is None:
            raise ResourceNotFound("Warehouse inventory not found.")

        transaction_entity, ledger_entity = wi.mark_damaged(StockQuantity(quantity), reference, _now())
        saved = self._repo.save(wi)
        self._repo.persist_transaction_and_ledger(warehouse_inventory_id, transaction_entity, ledger_entity)

        from apps.inventory.domain.events import StockDamaged

        self._ctx.stage_events([("StockDamaged", StockDamaged(warehouse_inventory_id=warehouse_inventory_id, quantity=quantity).to_payload())])
        self._ctx.audit().updated(entity_type="WarehouseInventory", entity_id=str(warehouse_inventory_id), before={}, after={"damaged": quantity})
        self._ctx.invalidate_inventory_cache()
        self._ctx.metric("stock_damaged_total", value=quantity)
        return saved


class ExpireStock:
    def __init__(self, repo: WarehouseInventoryRepository, ctx: InventoryServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, warehouse_inventory_id: uuid.UUID, quantity: int, reference: str, batch_id: uuid.UUID | None = None) -> WarehouseInventory:
        wi = self._repo.get_by_id(warehouse_inventory_id)
        if wi is None:
            raise ResourceNotFound("Warehouse inventory not found.")

        transaction_entity, ledger_entity = wi.mark_expired(StockQuantity(quantity), reference, _now())
        saved = self._repo.save(wi)
        self._repo.persist_transaction_and_ledger(warehouse_inventory_id, transaction_entity, ledger_entity)

        from apps.inventory.domain.events import StockExpired

        self._ctx.stage_events([("StockExpired", StockExpired(warehouse_inventory_id=warehouse_inventory_id, quantity=quantity, batch_id=batch_id).to_payload())])
        self._ctx.audit().updated(entity_type="WarehouseInventory", entity_id=str(warehouse_inventory_id), before={}, after={"expired": quantity})
        self._ctx.invalidate_inventory_cache()
        self._ctx.metric("stock_expired_total", value=quantity)
        return saved
