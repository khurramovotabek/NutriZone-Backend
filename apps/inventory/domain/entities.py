"""
Inventory domain entities (non-root members of an aggregate).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from apps.inventory.domain.enums import LedgerEntryType, SerialStatus, StockStatus
from apps.inventory.domain.value_objects import BatchNumber, SerialNumber, StockQuantity


@dataclass(slots=True)
class InventoryLedger:
    """
    Non-root entity -- one append-only journal line, produced by every
    stock-affecting operation (Movement/Adjustment/Reservation). The
    "Ledger" itself is not a separate aggregate root (not listed among
    this module's ten aggregates) -- it is the ordered collection of
    these entries for one Inventory/WarehouseInventory, queried via
    `LedgerRepository` at the infrastructure layer. "Ledger balancing"
    (the domain rule) means: replaying every entry's `quantity_delta`
    from zero must equal the current `balance_after` of the most
    recent entry -- verified by `domain/services.py::LedgerPolicy`.
    """

    id: uuid.UUID
    entry_type: LedgerEntryType
    stock_status: StockStatus
    quantity_delta: int  # signed: positive for increases, negative for decreases
    balance_after: int
    reference: str
    occurred_at: datetime


@dataclass(slots=True)
class InventoryTransaction:
    """
    Non-root entity -- the immutable record of *what happened* (as
    opposed to `InventoryLedger`, which records the *resulting
    balance*). Every Movement/Adjustment produces exactly one
    InventoryTransaction plus one-or-more InventoryLedger entries (one
    ledger entry per StockStatus bucket the transaction touched, since
    a single transfer touches both a source and destination bucket).
    """

    id: uuid.UUID
    movement_type: str  # MovementType.value
    quantity: int
    from_status: StockStatus | None
    to_status: StockStatus | None
    reference: str
    occurred_at: datetime


@dataclass(slots=True)
class ReservationItem:
    """Non-root entity, owned by Reservation -- one line item, optionally pinned to a specific Batch (FEFO-selected or caller-specified)."""

    id: uuid.UUID
    quantity: StockQuantity
    batch_id: uuid.UUID | None = None


@dataclass(slots=True)
class BatchItem:
    """
    Non-root entity, owned by Batch -- NOT one physical unit (that's
    `SerialItem`, for serialized goods); this represents a
    sub-allocation of a batch's quantity to a specific warehouse/shelf
    location, since one received batch is frequently split across
    multiple shelf locations on put-away.
    """

    id: uuid.UUID
    warehouse_inventory_id: uuid.UUID
    shelf_inventory_id: uuid.UUID | None
    quantity: StockQuantity


@dataclass(slots=True)
class SerialItem:
    """Non-root entity, owned by Batch (for serial-tracked inventory) -- one physical unit."""

    id: uuid.UUID
    serial_number: SerialNumber
    status: SerialStatus = SerialStatus.IN_STOCK


@dataclass(slots=True)
class InventoryHistory:
    """Non-root entity -- a denormalized, human-readable audit trail line, distinct from InventoryLedger's balance-bearing accounting record (this is 'what an ops person sees in a timeline view', not the reconciliation source of truth)."""

    id: uuid.UUID
    description: str
    occurred_at: datetime
    actor_id: uuid.UUID | None = None


@dataclass(slots=True)
class StockSnapshot:
    """Non-root entity, owned by InventorySnapshot -- one item's captured quantities at snapshot time, per StockStatus bucket."""

    id: uuid.UUID
    inventory_id: uuid.UUID
    quantities_by_status: dict[str, int] = field(default_factory=dict)  # StockStatus.value -> quantity


@dataclass(slots=True)
class StockAlert:
    """Non-root entity, owned by Inventory -- a fired threshold breach, per `ThresholdRule`."""

    id: uuid.UUID
    health_status: str  # InventoryHealthStatus.value
    triggered_at: datetime
    acknowledged: bool = False


@dataclass(slots=True)
class ThresholdRule:
    """Non-root entity, owned by Inventory -- wraps a StockThreshold with its own identity so multiple threshold configurations (e.g. per-warehouse overrides) can coexist."""

    id: uuid.UUID
    low_stock_at: int
    reorder_at: int
    overstock_at: int | None = None
    warehouse_id: uuid.UUID | None = None  # None means "platform-wide default"


@dataclass(slots=True)
class MovementItem:
    """Non-root entity, owned by InventoryMovement -- one line item of a movement, optionally batch-pinned."""

    id: uuid.UUID
    quantity: StockQuantity
    batch_id: uuid.UUID | None = None
