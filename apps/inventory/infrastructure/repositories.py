"""
Inventory repositories.

Concrete implementations of application/ports.py's Protocols -- maps
ORM rows to domain dataclasses only, never leaks ORM objects outside
this module, matching the pattern established by every prior module.

WarehouseInventoryRepository.save() is the one repository in this
module doing genuinely more than simple field mapping: every domain
method on `WarehouseInventory` (aggregates.py) returns
`(InventoryTransaction, InventoryLedger)` pairs that this repository
must persist alongside the updated balance columns -- the aggregate
itself only holds the *current* quantities in memory, never the
transaction/ledger history, so the repository is where "persist the
ledger entries this operation produced" actually happens. This is
standard Repository-pattern responsibility (translating what the
domain returned into what gets written), not business logic.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from django.db import IntegrityError, transaction

from apps.inventory.domain.aggregates import (
    Batch, CycleCount, Inventory, InventoryAdjustment, InventoryMovement, InventorySnapshot,
    PhysicalInventory, Reservation, ShelfInventory, WarehouseInventory,
)
from apps.inventory.domain.entities import BatchItem, MovementItem, ReservationItem, SerialItem, StockAlert, StockSnapshot
from apps.inventory.domain.enums import (
    AdjustmentReason, BatchStatus, CycleCountStatus, InventorySnapshotStatus, InventoryStatus, MovementType,
    PhysicalInventoryStatus, ReservationStatus, SerialStatus, StockStatus,
)
from apps.inventory.domain.services import BatchCandidate
from apps.inventory.domain.value_objects import (
    BatchNumber, ExpirationDate, InventoryCode, ManufactureDate, MovementReference, ReservationNumber,
    SerialNumber, SnapshotVersion, StockQuantity, StockThreshold,
)
from apps.inventory.infrastructure import models as orm
from common.exceptions import ConflictError

_STATUS_FIELD_MAP = {
    StockStatus.AVAILABLE: "available_quantity",
    StockStatus.RESERVED: "reserved_quantity",
    StockStatus.INCOMING: "incoming_quantity",
    StockStatus.DAMAGED: "damaged_quantity",
    StockStatus.EXPIRED: "expired_quantity",
    StockStatus.QUARANTINE: "quarantine_quantity",
    StockStatus.RETURNED: "returned_quantity",
}


class DjangoInventoryRepository:
    def get_by_id(self, inventory_id: uuid.UUID) -> Inventory | None:
        row = orm.InventoryModel.objects.filter(id=inventory_id).prefetch_related("alerts").first()
        return self._to_domain(row) if row else None

    def get_by_code(self, code: str) -> Inventory | None:
        row = orm.InventoryModel.objects.filter(code=code).first()
        return self._to_domain(row) if row else None

    def get_by_product_variant(self, product_variant_id: uuid.UUID) -> Inventory | None:
        row = orm.InventoryModel.objects.filter(product_variant_id=product_variant_id).first()
        return self._to_domain(row) if row else None

    def save(self, inventory: Inventory) -> Inventory:
        try:
            row, _ = orm.InventoryModel.objects.update_or_create(
                id=inventory.id,
                defaults={
                    "code": inventory.code.value, "product_variant_id": inventory.product_variant_id, "status": inventory.status.value,
                    "is_batch_tracked": inventory.is_batch_tracked, "is_serial_tracked": inventory.is_serial_tracked,
                    "low_stock_at": inventory.threshold.low_stock_at if inventory.threshold else None,
                    "reorder_at": inventory.threshold.reorder_at if inventory.threshold else None,
                    "overstock_at": inventory.threshold.overstock_at if inventory.threshold else None,
                },
            )
        except IntegrityError as exc:
            raise ConflictError("An inventory item with conflicting unique fields already exists.") from exc

        existing_alert_ids = set(row.alerts.values_list("id", flat=True))
        for alert in inventory.alerts.values():
            if alert.id not in existing_alert_ids:
                orm.StockAlertModel.objects.create(id=alert.id, inventory=row, health_status=alert.health_status, triggered_at=alert.triggered_at, acknowledged=alert.acknowledged)

        return inventory

    def code_exists(self, code: str, exclude_id: uuid.UUID | None = None) -> bool:
        qs = orm.InventoryModel.objects.filter(code=code)
        if exclude_id:
            qs = qs.exclude(id=exclude_id)
        return qs.exists()

    def list_for_admin(self, status: str | None, query: str | None, page: int, page_size: int) -> tuple[list[Inventory], int]:
        qs = orm.InventoryModel.objects.all()
        if status:
            qs = qs.filter(status=status)
        if query:
            qs = qs.filter(code__icontains=query)
        total = qs.count()
        rows = qs.order_by("-created_at")[(page - 1) * page_size : page * page_size]
        return [self._to_domain(r) for r in rows], total

    def _to_domain(self, row: orm.InventoryModel) -> Inventory:
        threshold = None
        if row.low_stock_at is not None and row.reorder_at is not None:
            threshold = StockThreshold(low_stock_at=row.low_stock_at, reorder_at=row.reorder_at, overstock_at=row.overstock_at)
        alerts = {a.id: StockAlert(id=a.id, health_status=a.health_status, triggered_at=a.triggered_at, acknowledged=a.acknowledged) for a in row.alerts.all()}
        return Inventory(
            id=row.id, code=InventoryCode(row.code), product_variant_id=row.product_variant_id, status=InventoryStatus(row.status),
            is_batch_tracked=row.is_batch_tracked, is_serial_tracked=row.is_serial_tracked, threshold=threshold, alerts=alerts,
        )


class DjangoWarehouseInventoryRepository:
    def get_by_id(self, warehouse_inventory_id: uuid.UUID) -> WarehouseInventory | None:
        row = orm.WarehouseInventoryModel.objects.filter(id=warehouse_inventory_id).first()
        return self._to_domain(row) if row else None

    def get_by_id_for_update(self, warehouse_inventory_id: uuid.UUID) -> WarehouseInventory | None:
        row = orm.WarehouseInventoryModel.objects.select_for_update().filter(id=warehouse_inventory_id).first()
        return self._to_domain(row) if row else None

    def get_by_inventory_and_warehouse(self, inventory_id: uuid.UUID, warehouse_id: uuid.UUID) -> WarehouseInventory | None:
        row = orm.WarehouseInventoryModel.objects.filter(inventory_id=inventory_id, warehouse_id=warehouse_id).first()
        return self._to_domain(row) if row else None

    def save(self, warehouse_inventory: WarehouseInventory) -> WarehouseInventory:
        defaults = {"inventory_id": warehouse_inventory.inventory_id, "warehouse_id": warehouse_inventory.warehouse_id}
        for status, field_name in _STATUS_FIELD_MAP.items():
            defaults[field_name] = warehouse_inventory.get_quantity(status)
        try:
            orm.WarehouseInventoryModel.objects.update_or_create(id=warehouse_inventory.id, defaults=defaults)
        except IntegrityError as exc:
            raise ConflictError("A warehouse inventory record with conflicting unique fields already exists.") from exc
        return warehouse_inventory

    def inventory_id_for_variant(self, product_variant_id: uuid.UUID) -> uuid.UUID | None:
        """Just the Inventory id -- a transfer never needs the whole Inventory aggregate (whose code format the catalog's auto-created rows, e.g. "INV-67871C09", don't follow)."""
        return orm.InventoryModel.objects.filter(product_variant_id=product_variant_id).values_list("id", flat=True).first()

    def get_or_create_for_warehouse(self, inventory_id: uuid.UUID, warehouse_id: uuid.UUID) -> WarehouseInventory:
        """The (inventory, warehouse) row, created empty when this branch has never held the product -- e.g. the receiving side of its first transfer. A concurrent creator losing the unique-constraint race simply reads the winner's row."""
        try:
            with transaction.atomic():
                row, _created = orm.WarehouseInventoryModel.objects.get_or_create(inventory_id=inventory_id, warehouse_id=warehouse_id)
        except IntegrityError:
            row = orm.WarehouseInventoryModel.objects.get(inventory_id=inventory_id, warehouse_id=warehouse_id)
        return self._to_domain(row)

    def lock_many(self, warehouse_inventory_ids: list[uuid.UUID]) -> dict[uuid.UUID, WarehouseInventory]:
        """Row-locks (SELECT ... FOR UPDATE) every given row in one statement, always in id order, so two transfers touching the same rows can never deadlock each other."""
        rows = orm.WarehouseInventoryModel.objects.select_for_update().filter(id__in=warehouse_inventory_ids).order_by("id")
        return {row.id: self._to_domain(row) for row in rows}

    def list_by_inventory(self, inventory_id: uuid.UUID) -> list[WarehouseInventory]:
        return [self._to_domain(r) for r in orm.WarehouseInventoryModel.objects.filter(inventory_id=inventory_id)]

    def list_by_warehouse(self, warehouse_id: uuid.UUID) -> list[WarehouseInventory]:
        return [self._to_domain(r) for r in orm.WarehouseInventoryModel.objects.filter(warehouse_id=warehouse_id)]

    def _to_domain(self, row: orm.WarehouseInventoryModel) -> WarehouseInventory:
        quantities = {status: getattr(row, field_name) for status, field_name in _STATUS_FIELD_MAP.items()}
        return WarehouseInventory(id=row.id, inventory_id=row.inventory_id, warehouse_id=row.warehouse_id, quantities=quantities)

    def persist_transaction_and_ledger(self, warehouse_inventory_id: uuid.UUID, transaction_entity, ledger_entity) -> None:
        """
        Called by Application Services alongside `save()` -- persists
        the `InventoryTransaction`/`InventoryLedger` pair a domain
        method returned. Kept as an explicit, separate method (rather
        than folded into `save()`) since not every `save()` call
        follows a transaction-producing domain method (e.g. a plain
        reconciliation `RestoreSnapshot` write has no ledger pair to
        persist).
        """
        orm.InventoryTransactionModel.objects.create(
            id=transaction_entity.id, warehouse_inventory_id=warehouse_inventory_id, movement_type=transaction_entity.movement_type,
            quantity=transaction_entity.quantity, from_status=transaction_entity.from_status.value if transaction_entity.from_status else None,
            to_status=transaction_entity.to_status.value if transaction_entity.to_status else None, reference=transaction_entity.reference, occurred_at=transaction_entity.occurred_at,
        )
        orm.InventoryLedgerModel.objects.create(
            id=ledger_entity.id, warehouse_inventory_id=warehouse_inventory_id, entry_type=ledger_entity.entry_type.value, stock_status=ledger_entity.stock_status.value,
            quantity_delta=ledger_entity.quantity_delta, balance_after=ledger_entity.balance_after, reference=ledger_entity.reference, occurred_at=ledger_entity.occurred_at,
        )


class DjangoShelfInventoryRepository:
    def get_by_id(self, shelf_inventory_id: uuid.UUID) -> ShelfInventory | None:
        row = orm.ShelfInventoryModel.objects.filter(id=shelf_inventory_id).first()
        return self._to_domain(row) if row else None

    def save(self, shelf_inventory: ShelfInventory) -> ShelfInventory:
        orm.ShelfInventoryModel.objects.update_or_create(
            id=shelf_inventory.id, defaults={"warehouse_inventory_id": shelf_inventory.warehouse_inventory_id, "shelf_id": shelf_inventory.shelf_id, "quantity": shelf_inventory.quantity.value}
        )
        return shelf_inventory

    def list_by_warehouse_inventory(self, warehouse_inventory_id: uuid.UUID) -> list[ShelfInventory]:
        return [self._to_domain(r) for r in orm.ShelfInventoryModel.objects.filter(warehouse_inventory_id=warehouse_inventory_id)]

    def _to_domain(self, row: orm.ShelfInventoryModel) -> ShelfInventory:
        return ShelfInventory(id=row.id, warehouse_inventory_id=row.warehouse_inventory_id, shelf_id=row.shelf_id, quantity=StockQuantity(row.quantity))


class DjangoReservationRepository:
    def get_by_id(self, reservation_id: uuid.UUID) -> Reservation | None:
        row = orm.ReservationModel.objects.filter(id=reservation_id).prefetch_related("items").first()
        return self._to_domain(row) if row else None

    def get_by_number(self, reservation_number: str) -> Reservation | None:
        row = orm.ReservationModel.objects.filter(reservation_number=reservation_number).prefetch_related("items").first()
        return self._to_domain(row) if row else None

    def save(self, reservation: Reservation) -> Reservation:
        row, _ = orm.ReservationModel.objects.update_or_create(
            id=reservation.id,
            defaults={
                "reservation_number": reservation.reservation_number.value, "owner_type": reservation.owner_type, "owner_id": reservation.owner_id,
                "warehouse_inventory_id": reservation.warehouse_inventory_id, "status": reservation.status.value, "expires_at": reservation.expires_at,
            },
        )
        existing_ids = set(row.items.values_list("id", flat=True))
        for item in reservation.items.values():
            if item.id not in existing_ids:
                orm.ReservationItemModel.objects.create(id=item.id, reservation=row, quantity=item.quantity.value, batch_id=item.batch_id)
        return reservation

    def list_expired(self, as_of) -> list[Reservation]:
        rows = orm.ReservationModel.objects.filter(status__in=[ReservationStatus.PENDING.value, ReservationStatus.CONFIRMED.value], expires_at__lte=as_of).prefetch_related("items")
        return [self._to_domain(r) for r in rows]

    def _to_domain(self, row: orm.ReservationModel) -> Reservation:
        items = {i.id: ReservationItem(id=i.id, quantity=StockQuantity(i.quantity), batch_id=i.batch_id) for i in row.items.all()}
        return Reservation(
            id=row.id, reservation_number=ReservationNumber(row.reservation_number), owner_type=row.owner_type, owner_id=row.owner_id,
            warehouse_inventory_id=row.warehouse_inventory_id, status=ReservationStatus(row.status), expires_at=row.expires_at, items=items,
        )


class DjangoMovementRepository:
    def get_by_id(self, movement_id: uuid.UUID) -> InventoryMovement | None:
        row = orm.InventoryMovementModel.objects.filter(id=movement_id).prefetch_related("items").first()
        return self._to_domain(row) if row else None

    def save(self, movement: InventoryMovement) -> InventoryMovement:
        row, _ = orm.InventoryMovementModel.objects.update_or_create(
            id=movement.id,
            defaults={
                "movement_type": movement.movement_type.value, "reference": movement.reference.value,
                "source_warehouse_inventory_id": movement.source_warehouse_inventory_id, "destination_warehouse_inventory_id": movement.destination_warehouse_inventory_id,
                "occurred_at": movement.occurred_at,
            },
        )
        existing_ids = set(row.items.values_list("id", flat=True))
        for item in movement.items.values():
            if item.id not in existing_ids:
                orm.MovementItemModel.objects.create(id=item.id, movement=row, quantity=item.quantity.value, batch_id=item.batch_id)
        return movement

    def list_by_warehouse_inventory(self, warehouse_inventory_id: uuid.UUID, page: int, page_size: int) -> tuple[list[InventoryMovement], int]:
        from django.db.models import Q

        qs = orm.InventoryMovementModel.objects.filter(Q(source_warehouse_inventory_id=warehouse_inventory_id) | Q(destination_warehouse_inventory_id=warehouse_inventory_id))
        total = qs.count()
        rows = qs.order_by("-occurred_at")[(page - 1) * page_size : page * page_size].prefetch_related("items")
        return [self._to_domain(r) for r in rows], total

    def _to_domain(self, row: orm.InventoryMovementModel) -> InventoryMovement:
        items = {i.id: MovementItem(id=i.id, quantity=StockQuantity(i.quantity), batch_id=i.batch_id) for i in row.items.all()}
        return InventoryMovement(
            id=row.id, movement_type=MovementType(row.movement_type), reference=MovementReference(row.reference),
            source_warehouse_inventory_id=row.source_warehouse_inventory_id, destination_warehouse_inventory_id=row.destination_warehouse_inventory_id,
            items=items, occurred_at=row.occurred_at,
        )


class DjangoAdjustmentRepository:
    def get_by_id(self, adjustment_id: uuid.UUID) -> InventoryAdjustment | None:
        row = orm.InventoryAdjustmentModel.objects.filter(id=adjustment_id).first()
        return self._to_domain(row) if row else None

    def save(self, adjustment: InventoryAdjustment) -> InventoryAdjustment:
        orm.InventoryAdjustmentModel.objects.update_or_create(
            id=adjustment.id,
            defaults={
                "warehouse_inventory_id": adjustment.warehouse_inventory_id, "reason": adjustment.reason.value,
                "quantity_delta": adjustment.quantity_delta, "reference": adjustment.reference, "stock_status": adjustment.stock_status.value,
            },
        )
        return adjustment

    def _to_domain(self, row: orm.InventoryAdjustmentModel) -> InventoryAdjustment:
        return InventoryAdjustment(id=row.id, warehouse_inventory_id=row.warehouse_inventory_id, reason=AdjustmentReason(row.reason), quantity_delta=row.quantity_delta, reference=row.reference, stock_status=StockStatus(row.stock_status))


class DjangoLedgerRepository:
    """Read-only, per application/ports.py::LedgerRepository's own docstring -- writes flow through DjangoWarehouseInventoryRepository.persist_transaction_and_ledger()."""

    def list_entries(self, warehouse_inventory_id: uuid.UUID, stock_status: str | None = None) -> list[dict]:
        qs = orm.InventoryLedgerModel.objects.filter(warehouse_inventory_id=warehouse_inventory_id)
        if stock_status:
            qs = qs.filter(stock_status=stock_status)
        return [{"id": str(r.id), "entry_type": r.entry_type, "stock_status": r.stock_status, "quantity_delta": r.quantity_delta, "balance_after": r.balance_after, "occurred_at": r.occurred_at} for r in qs.order_by("occurred_at")]

    def get_latest_balance(self, warehouse_inventory_id: uuid.UUID, stock_status: str) -> int:
        row = orm.InventoryLedgerModel.objects.filter(warehouse_inventory_id=warehouse_inventory_id, stock_status=stock_status).order_by("-occurred_at").first()
        return row.balance_after if row else 0


class DjangoBatchRepository:
    def get_by_id(self, batch_id: uuid.UUID) -> Batch | None:
        row = orm.BatchModel.objects.filter(id=batch_id).prefetch_related("serials").first()
        return self._to_domain(row) if row else None

    def get_by_number(self, batch_number: str) -> Batch | None:
        row = orm.BatchModel.objects.filter(batch_number=batch_number).prefetch_related("serials").first()
        return self._to_domain(row) if row else None

    def save(self, batch: Batch) -> Batch:
        try:
            row, _ = orm.BatchModel.objects.update_or_create(
                id=batch.id,
                defaults={
                    "inventory_id": batch.inventory_id, "batch_number": batch.batch_number.value,
                    "manufacture_date": batch.manufacture_date.value if batch.manufacture_date else None,
                    "expiration_date": batch.expiration_date.value if batch.expiration_date else None,
                    "status": batch.status.value, "quantity_received": batch.quantity_received.value,
                },
            )
        except IntegrityError as exc:
            raise ConflictError("A batch with conflicting unique fields already exists.") from exc

        existing_serial_ids = set(row.serials.values_list("id", flat=True))
        for serial in batch.serials.values():
            if serial.id not in existing_serial_ids:
                orm.SerialModel.objects.create(id=serial.id, batch=row, serial_number=serial.serial_number.value, status=serial.status.value)
            else:
                orm.SerialModel.objects.filter(id=serial.id).update(status=serial.status.value)
        return batch

    def number_exists(self, batch_number: str, exclude_id: uuid.UUID | None = None) -> bool:
        qs = orm.BatchModel.objects.filter(batch_number=batch_number)
        if exclude_id:
            qs = qs.exclude(id=exclude_id)
        return qs.exists()

    def list_candidates_for_allocation(self, inventory_id: uuid.UUID, warehouse_id: uuid.UUID, as_of: date) -> list[BatchCandidate]:
        rows = orm.BatchModel.objects.filter(inventory_id=inventory_id, status=BatchStatus.ACTIVE.value).exclude(expiration_date__lte=as_of)
        candidates = []
        for row in rows:
            wi = orm.WarehouseInventoryModel.objects.filter(inventory_id=inventory_id, warehouse_id=warehouse_id).first()
            available = wi.available_quantity if wi else 0
            candidates.append(BatchCandidate(batch_id=row.id, available_quantity=available, received_at=row.created_at, expiration_date=row.expiration_date))
        return candidates

    def list_by_inventory(self, inventory_id: uuid.UUID) -> list[Batch]:
        return [self._to_domain(r) for r in orm.BatchModel.objects.filter(inventory_id=inventory_id).prefetch_related("serials")]

    def _to_domain(self, row: orm.BatchModel) -> Batch:
        serials = {s.id: SerialItem(id=s.id, serial_number=SerialNumber(s.serial_number), status=SerialStatus(s.status)) for s in row.serials.all()}
        return Batch(
            id=row.id, inventory_id=row.inventory_id, batch_number=BatchNumber(row.batch_number),
            manufacture_date=ManufactureDate(row.manufacture_date) if row.manufacture_date else None,
            expiration_date=ExpirationDate(row.expiration_date) if row.expiration_date else None,
            status=BatchStatus(row.status), quantity_received=StockQuantity(row.quantity_received), serials=serials,
        )


class DjangoSerialRepository:
    def serial_exists(self, serial_number: str, exclude_batch_id: uuid.UUID | None = None) -> bool:
        qs = orm.SerialModel.objects.filter(serial_number=serial_number)
        if exclude_batch_id:
            qs = qs.exclude(batch_id=exclude_batch_id)
        return qs.exists()

    def get_batch_id_for_serial(self, serial_number: str) -> uuid.UUID | None:
        row = orm.SerialModel.objects.filter(serial_number=serial_number).only("batch_id").first()
        return row.batch_id if row else None


class DjangoSnapshotRepository:
    def get_by_id(self, snapshot_id: uuid.UUID) -> InventorySnapshot | None:
        row = orm.InventorySnapshotModel.objects.filter(id=snapshot_id).prefetch_related("items").first()
        return self._to_domain(row) if row else None

    def get_latest_version(self) -> int:
        row = orm.InventorySnapshotModel.objects.order_by("-version").first()
        return row.version if row else 0

    def save(self, snapshot: InventorySnapshot) -> InventorySnapshot:
        try:
            row, _ = orm.InventorySnapshotModel.objects.update_or_create(
                id=snapshot.id, defaults={"version": snapshot.version.value, "status": snapshot.status.value, "captured_at": snapshot.captured_at}
            )
        except IntegrityError as exc:
            raise ConflictError(f"Snapshot version {snapshot.version.value} already exists.") from exc

        existing_ids = set(row.items.values_list("id", flat=True))
        for item in snapshot.items.values():
            if item.id not in existing_ids:
                orm.SnapshotItemModel.objects.create(id=item.id, snapshot=row, inventory_id=item.inventory_id, quantities_by_status=item.quantities_by_status)
        return snapshot

    def _to_domain(self, row: orm.InventorySnapshotModel) -> InventorySnapshot:
        items = {i.id: StockSnapshot(id=i.id, inventory_id=i.inventory_id, quantities_by_status=i.quantities_by_status) for i in row.items.all()}
        return InventorySnapshot(id=row.id, version=SnapshotVersion(row.version), status=InventorySnapshotStatus(row.status), captured_at=row.captured_at, items=items)


class DjangoCycleCountRepository:
    def get_by_id(self, cycle_count_id: uuid.UUID) -> CycleCount | None:
        row = orm.CycleCountModel.objects.filter(id=cycle_count_id).prefetch_related("items").first()
        return self._to_domain(row) if row else None

    def save(self, cycle_count: CycleCount) -> CycleCount:
        row, _ = orm.CycleCountModel.objects.update_or_create(id=cycle_count.id, defaults={"warehouse_id": cycle_count.warehouse_id, "status": cycle_count.status.value})
        for inventory_id, quantity in cycle_count.counted_quantities.items():
            orm.CycleCountItemModel.objects.update_or_create(cycle_count=row, inventory_id=inventory_id, defaults={"counted_quantity": quantity})
        return cycle_count

    def _to_domain(self, row: orm.CycleCountModel) -> CycleCount:
        counted = {i.inventory_id: i.counted_quantity for i in row.items.all()}
        return CycleCount(id=row.id, warehouse_id=row.warehouse_id, status=CycleCountStatus(row.status), counted_quantities=counted)


class DjangoPhysicalInventoryRepository:
    def get_by_id(self, physical_inventory_id: uuid.UUID) -> PhysicalInventory | None:
        row = orm.PhysicalInventoryModel.objects.filter(id=physical_inventory_id).prefetch_related("items").first()
        return self._to_domain(row) if row else None

    def save(self, physical_inventory: PhysicalInventory) -> PhysicalInventory:
        row, _ = orm.PhysicalInventoryModel.objects.update_or_create(id=physical_inventory.id, defaults={"warehouse_id": physical_inventory.warehouse_id, "status": physical_inventory.status.value})
        for inventory_id, quantity in physical_inventory.counted_quantities.items():
            orm.PhysicalInventoryItemModel.objects.update_or_create(physical_inventory=row, inventory_id=inventory_id, defaults={"counted_quantity": quantity})
        return physical_inventory

    def _to_domain(self, row: orm.PhysicalInventoryModel) -> PhysicalInventory:
        counted = {i.inventory_id: i.counted_quantity for i in row.items.all()}
        return PhysicalInventory(id=row.id, warehouse_id=row.warehouse_id, status=PhysicalInventoryStatus(row.status), counted_quantities=counted)


class DjangoStockTransferRepository:
    _NUMBER_LOCK_KEY = 7_311_204_118  # arbitrary, stable pg advisory-lock key for transfer numbering

    def next_sequence(self) -> int:
        """Gap-free, collision-free document numbering: a transaction-scoped advisory lock serialises only the numbering step (released automatically at commit/rollback)."""
        from django.db import connection
        from django.db.models import Max

        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [self._NUMBER_LOCK_KEY])
        current = orm.StockTransferModel.objects.aggregate(m=Max("sequence"))["m"] or 0
        return current + 1

    def save(self, transfer, sequence: int, actor_name: str = "") -> None:
        row = orm.StockTransferModel.objects.create(
            id=transfer.id, sequence=sequence, number=transfer.number,
            source_warehouse_id=transfer.source_warehouse_id, destination_warehouse_id=transfer.destination_warehouse_id,
            note=transfer.note, actor_id=transfer.actor_id, actor_name=actor_name[:150],
            total_units=transfer.total_units, completed_at=transfer.completed_at,
        )
        orm.StockTransferLineModel.objects.bulk_create([
            orm.StockTransferLineModel(
                transfer=row, product_variant_id=line.product_variant_id, quantity=line.quantity,
                source_warehouse_inventory_id=line.source_warehouse_inventory_id, destination_warehouse_inventory_id=line.destination_warehouse_inventory_id,
                source_balance_after=line.source_balance_after, destination_balance_after=line.destination_balance_after,
            )
            for line in transfer.lines
        ])
