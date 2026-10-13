"""
Inventory domain events.

Registered against `core.events.registry` via
`shared/event_contracts/inventory.py`, matching every prior module's
pattern.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class InventoryCreated:
    inventory_id: uuid.UUID
    code: str
    product_variant_id: uuid.UUID

    def to_payload(self) -> dict:
        return {**asdict(self), "inventory_id": str(self.inventory_id), "product_variant_id": str(self.product_variant_id)}


@dataclass(frozen=True, slots=True)
class InventoryUpdated:
    inventory_id: uuid.UUID
    before: dict
    after: dict

    def to_payload(self) -> dict:
        return {**asdict(self), "inventory_id": str(self.inventory_id)}


@dataclass(frozen=True, slots=True)
class InventoryArchivedEvent:
    inventory_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"inventory_id": str(self.inventory_id)}


@dataclass(frozen=True, slots=True)
class InventoryRestored:
    inventory_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"inventory_id": str(self.inventory_id)}


@dataclass(frozen=True, slots=True)
class StockConfirmed:
    """Phase 02F: confirm_incoming's own event, moving INCOMING -> AVAILABLE -- the only path stock takes into AVAILABLE from outside the system, per confirm_incoming()'s own docstring."""

    warehouse_inventory_id: uuid.UUID
    quantity: int
    reference: str

    def to_payload(self) -> dict:
        return {**asdict(self), "warehouse_inventory_id": str(self.warehouse_inventory_id)}


@dataclass(frozen=True, slots=True)
class StockReceived:
    warehouse_inventory_id: uuid.UUID
    quantity: int
    reference: str

    def to_payload(self) -> dict:
        return {**asdict(self), "warehouse_inventory_id": str(self.warehouse_inventory_id)}


@dataclass(frozen=True, slots=True)
class StockReserved:
    reservation_id: uuid.UUID
    warehouse_inventory_id: uuid.UUID
    quantity: int

    def to_payload(self) -> dict:
        return {**asdict(self), "reservation_id": str(self.reservation_id), "warehouse_inventory_id": str(self.warehouse_inventory_id)}


@dataclass(frozen=True, slots=True)
class ReservationReleased:
    reservation_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"reservation_id": str(self.reservation_id)}


@dataclass(frozen=True, slots=True)
class StockTransferred:
    source_warehouse_inventory_id: uuid.UUID
    destination_warehouse_inventory_id: uuid.UUID
    quantity: int

    def to_payload(self) -> dict:
        return {**asdict(self), "source_warehouse_inventory_id": str(self.source_warehouse_inventory_id), "destination_warehouse_inventory_id": str(self.destination_warehouse_inventory_id)}


@dataclass(frozen=True, slots=True)
class StockAdjusted:
    adjustment_id: uuid.UUID
    warehouse_inventory_id: uuid.UUID
    quantity_delta: int
    reason: str

    def to_payload(self) -> dict:
        return {**asdict(self), "adjustment_id": str(self.adjustment_id), "warehouse_inventory_id": str(self.warehouse_inventory_id)}


@dataclass(frozen=True, slots=True)
class StockExpired:
    warehouse_inventory_id: uuid.UUID
    quantity: int
    batch_id: uuid.UUID | None

    def to_payload(self) -> dict:
        return {**asdict(self), "warehouse_inventory_id": str(self.warehouse_inventory_id), "batch_id": str(self.batch_id) if self.batch_id else None}


@dataclass(frozen=True, slots=True)
class StockDamaged:
    warehouse_inventory_id: uuid.UUID
    quantity: int

    def to_payload(self) -> dict:
        return {**asdict(self), "warehouse_inventory_id": str(self.warehouse_inventory_id)}


@dataclass(frozen=True, slots=True)
class BatchCreated:
    batch_id: uuid.UUID
    inventory_id: uuid.UUID
    batch_number: str

    def to_payload(self) -> dict:
        return {**asdict(self), "batch_id": str(self.batch_id), "inventory_id": str(self.inventory_id)}


@dataclass(frozen=True, slots=True)
class SerialRegistered:
    batch_id: uuid.UUID
    serial_item_id: uuid.UUID
    serial_number: str

    def to_payload(self) -> dict:
        return {**asdict(self), "batch_id": str(self.batch_id), "serial_item_id": str(self.serial_item_id)}


@dataclass(frozen=True, slots=True)
class ReservationCreated:
    reservation_id: uuid.UUID
    reservation_number: str
    warehouse_inventory_id: uuid.UUID

    def to_payload(self) -> dict:
        return {**asdict(self), "reservation_id": str(self.reservation_id), "warehouse_inventory_id": str(self.warehouse_inventory_id)}


@dataclass(frozen=True, slots=True)
class ReservationCancelled:
    reservation_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"reservation_id": str(self.reservation_id)}


@dataclass(frozen=True, slots=True)
class ReservationExpiredEvent:
    reservation_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"reservation_id": str(self.reservation_id)}


@dataclass(frozen=True, slots=True)
class CycleCountStarted:
    cycle_count_id: uuid.UUID
    warehouse_id: uuid.UUID

    def to_payload(self) -> dict:
        return {**asdict(self), "cycle_count_id": str(self.cycle_count_id), "warehouse_id": str(self.warehouse_id)}


@dataclass(frozen=True, slots=True)
class CycleCountCompleted:
    cycle_count_id: uuid.UUID
    discrepancy_count: int

    def to_payload(self) -> dict:
        return {**asdict(self), "cycle_count_id": str(self.cycle_count_id)}


@dataclass(frozen=True, slots=True)
class PhysicalInventoryStarted:
    physical_inventory_id: uuid.UUID
    warehouse_id: uuid.UUID

    def to_payload(self) -> dict:
        return {**asdict(self), "physical_inventory_id": str(self.physical_inventory_id), "warehouse_id": str(self.warehouse_id)}


@dataclass(frozen=True, slots=True)
class PhysicalInventoryCompleted:
    physical_inventory_id: uuid.UUID
    discrepancy_count: int

    def to_payload(self) -> dict:
        return {**asdict(self), "physical_inventory_id": str(self.physical_inventory_id)}


@dataclass(frozen=True, slots=True)
class InventorySnapshotCreated:
    snapshot_id: uuid.UUID
    version: int

    def to_payload(self) -> dict:
        return {**asdict(self), "snapshot_id": str(self.snapshot_id)}
