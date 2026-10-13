"""
Inventory aggregate roots: Inventory, WarehouseInventory, ShelfInventory,
Reservation, InventoryMovement, InventoryAdjustment, Batch, CycleCount,
PhysicalInventory, InventorySnapshot.

`WarehouseInventory` is the central stock-bucket aggregate: every unit
of stock lives in exactly one `StockStatus` bucket at a time, and every
method below is a *bucket transition* -- this is where "stock can never
become negative," "reserved cannot exceed available," "damaged stock
cannot be reserved," "quarantine stock cannot be transferred," and
"incoming stock cannot be sold" are all enforced structurally: there is
simply no method that performs a forbidden transition, not a runtime
check bolted onto a generic one.

Cross-module references (Inventory.product_variant_id ->
products.ProductVariant, WarehouseInventory.warehouse_id ->
store.Warehouse) are IDs only, per the platform-wide modular-monolith
isolation rule already applied consistently in every prior module.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

from apps.inventory.domain.entities import (
    BatchItem, InventoryLedger, InventoryTransaction, MovementItem, ReservationItem, SerialItem,
    StockAlert, StockSnapshot,
)
from apps.inventory.domain.enums import (
    AdjustmentReason, BatchStatus, CycleCountStatus, InventorySnapshotStatus, InventoryStatus, LedgerEntryType,
    MovementType, PhysicalInventoryStatus, ReservationStatus, StockStatus,
)
from apps.inventory.domain.events import (
    BatchCreated, CycleCountCompleted, CycleCountStarted, InventoryArchivedEvent, InventoryRestored,
    InventorySnapshotCreated, InventoryUpdated, PhysicalInventoryCompleted, PhysicalInventoryStarted,
    ReservationCancelled, ReservationExpiredEvent, SerialRegistered,
)
from apps.inventory.domain.exceptions import (
    BatchExpired, DuplicateSerial, InsufficientStock, InvalidCycleCountLifecycleTransition,
    InvalidInventoryLifecycleTransition, InvalidMovement, InvalidPhysicalInventoryLifecycleTransition,
    InvalidReservationLifecycleTransition, InventoryArchived, NegativeStock, ReservationExpired,
)
from apps.inventory.domain.value_objects import (
    BatchNumber, ExpirationDate, InventoryCode, ManufactureDate, MovementReference, ReservationNumber,
    SerialNumber, SnapshotVersion, StockQuantity, StockThreshold,
)
from common.exceptions import ValidationFailed


@dataclass(slots=True)
class Inventory:
    """Aggregate root -- platform-wide tracking configuration for one sellable item (one ProductVariant). Owns no stock quantities itself (WarehouseInventory does); this is the config/status record."""

    id: uuid.UUID
    code: InventoryCode
    product_variant_id: uuid.UUID
    status: InventoryStatus = InventoryStatus.ACTIVE
    is_batch_tracked: bool = False
    is_serial_tracked: bool = False
    threshold: StockThreshold | None = None
    alerts: dict[uuid.UUID, StockAlert] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.is_serial_tracked and not self.is_batch_tracked:
            raise ValidationFailed("Serial-tracked inventory must also be batch-tracked (serials are registered within a batch).")

    def update(self, threshold: StockThreshold | None = None) -> InventoryUpdated:
        before = {"threshold": self.threshold}
        if threshold is not None:
            self.threshold = threshold
        return InventoryUpdated(inventory_id=self.id, before=before, after={"threshold": self.threshold})

    def archive(self) -> InventoryArchivedEvent:
        if self.status == InventoryStatus.ARCHIVED:
            raise InvalidInventoryLifecycleTransition("This inventory item is already archived.")
        self.status = InventoryStatus.ARCHIVED
        return InventoryArchivedEvent(inventory_id=self.id)

    def restore(self) -> InventoryRestored:
        if self.status != InventoryStatus.ARCHIVED:
            raise InvalidInventoryLifecycleTransition("Only an archived inventory item can be restored.")
        self.status = InventoryStatus.ACTIVE
        return InventoryRestored(inventory_id=self.id)

    def assert_active(self) -> None:
        if self.status == InventoryStatus.ARCHIVED:
            raise InventoryArchived("This inventory item is archived and cannot be modified.")

    def raise_alert(self, health_status: str, at: datetime) -> StockAlert:
        alert = StockAlert(id=uuid.uuid4(), health_status=health_status, triggered_at=at)
        self.alerts[alert.id] = alert
        return alert


@dataclass(slots=True)
class WarehouseInventory:
    """
    Aggregate root -- the actual stock-bucket ledger for one Inventory
    item at one Warehouse. Every method is a bucket-to-bucket (or
    bucket-to-void, for sale/loss) transition; there is no generic
    "set quantity" method, by design -- see module docstring.
    """

    id: uuid.UUID
    inventory_id: uuid.UUID
    warehouse_id: uuid.UUID
    quantities: dict[StockStatus, int] = field(default_factory=lambda: {s: 0 for s in StockStatus})

    def _get(self, status: StockStatus) -> int:
        return self.quantities.get(status, 0)

    def _set(self, status: StockStatus, value: int) -> None:
        if value < 0:
            raise NegativeStock(f"This operation would leave '{status.value}' stock negative.")
        self.quantities[status] = value

    @property
    def available_quantity(self) -> int:
        return self._get(StockStatus.AVAILABLE)

    @property
    def reserved_quantity(self) -> int:
        return self._get(StockStatus.RESERVED)

    def get_quantity(self, status: StockStatus) -> int:
        """Public read accessor for any bucket -- `available_quantity`/`reserved_quantity` cover the two most common cases as properties; this covers the rest (DAMAGED/EXPIRED/QUARANTINE/INCOMING/RETURNED) without application-layer code reaching into the "private" `_get()` method."""
        return self._get(status)

    def receive(self, quantity: StockQuantity, reference: str, occurred_at: datetime) -> tuple[InventoryTransaction, InventoryLedger]:
        self._set(StockStatus.INCOMING, self._get(StockStatus.INCOMING) + quantity.value)
        transaction = InventoryTransaction(id=uuid.uuid4(), movement_type=MovementType.RECEIVE.value, quantity=quantity.value, from_status=None, to_status=StockStatus.INCOMING, reference=reference, occurred_at=occurred_at)
        ledger = InventoryLedger(id=uuid.uuid4(), entry_type=LedgerEntryType.RECEIVE, stock_status=StockStatus.INCOMING, quantity_delta=quantity.value, balance_after=self._get(StockStatus.INCOMING), reference=reference, occurred_at=occurred_at)
        return transaction, ledger

    def confirm_incoming(self, quantity: StockQuantity, reference: str, occurred_at: datetime) -> tuple[InventoryTransaction, InventoryLedger]:
        """Moves INCOMING -> AVAILABLE (post-receiving QC/putaway) -- the only path stock takes into AVAILABLE from outside the system."""
        incoming = self._get(StockStatus.INCOMING)
        if quantity.value > incoming:
            raise InsufficientStock(f"Cannot confirm {quantity.value} units; only {incoming} incoming.")
        self._set(StockStatus.INCOMING, incoming - quantity.value)
        self._set(StockStatus.AVAILABLE, self._get(StockStatus.AVAILABLE) + quantity.value)
        transaction = InventoryTransaction(id=uuid.uuid4(), movement_type=MovementType.RECEIVE.value, quantity=quantity.value, from_status=StockStatus.INCOMING, to_status=StockStatus.AVAILABLE, reference=reference, occurred_at=occurred_at)
        ledger = InventoryLedger(id=uuid.uuid4(), entry_type=LedgerEntryType.RECEIVE, stock_status=StockStatus.AVAILABLE, quantity_delta=quantity.value, balance_after=self._get(StockStatus.AVAILABLE), reference=reference, occurred_at=occurred_at)
        return transaction, ledger

    def reserve(self, quantity: StockQuantity, reference: str, occurred_at: datetime) -> tuple[InventoryTransaction, InventoryLedger]:
        """AVAILABLE -> RESERVED only -- structurally impossible to reserve DAMAGED/EXPIRED/QUARANTINE/INCOMING stock."""
        available = self._get(StockStatus.AVAILABLE)
        if quantity.value > available:
            raise InsufficientStock(f"Cannot reserve {quantity.value} units; only {available} available.")
        self._set(StockStatus.AVAILABLE, available - quantity.value)
        self._set(StockStatus.RESERVED, self._get(StockStatus.RESERVED) + quantity.value)
        transaction = InventoryTransaction(id=uuid.uuid4(), movement_type=MovementType.RESERVE.value, quantity=quantity.value, from_status=StockStatus.AVAILABLE, to_status=StockStatus.RESERVED, reference=reference, occurred_at=occurred_at)
        ledger = InventoryLedger(id=uuid.uuid4(), entry_type=LedgerEntryType.RESERVE, stock_status=StockStatus.RESERVED, quantity_delta=quantity.value, balance_after=self._get(StockStatus.RESERVED), reference=reference, occurred_at=occurred_at)
        return transaction, ledger

    def release_reservation(self, quantity: StockQuantity, reference: str, occurred_at: datetime) -> tuple[InventoryTransaction, InventoryLedger]:
        reserved = self._get(StockStatus.RESERVED)
        if quantity.value > reserved:
            raise InsufficientStock(f"Cannot release {quantity.value} units; only {reserved} reserved.")
        self._set(StockStatus.RESERVED, reserved - quantity.value)
        self._set(StockStatus.AVAILABLE, self._get(StockStatus.AVAILABLE) + quantity.value)
        transaction = InventoryTransaction(id=uuid.uuid4(), movement_type=MovementType.RELEASE.value, quantity=quantity.value, from_status=StockStatus.RESERVED, to_status=StockStatus.AVAILABLE, reference=reference, occurred_at=occurred_at)
        ledger = InventoryLedger(id=uuid.uuid4(), entry_type=LedgerEntryType.RELEASE, stock_status=StockStatus.AVAILABLE, quantity_delta=quantity.value, balance_after=self._get(StockStatus.AVAILABLE), reference=reference, occurred_at=occurred_at)
        return transaction, ledger

    def sell(self, quantity: StockQuantity, reference: str, occurred_at: datetime) -> tuple[InventoryTransaction, InventoryLedger]:
        """RESERVED -> void (leaves the system) -- a sale must always be preceded by a reservation; this structurally guarantees 'incoming stock cannot be sold' (INCOMING can only reach AVAILABLE, never RESERVED, without first being reserved from AVAILABLE)."""
        reserved = self._get(StockStatus.RESERVED)
        if quantity.value > reserved:
            raise InsufficientStock(f"Cannot sell {quantity.value} units; only {reserved} reserved for sale.")
        self._set(StockStatus.RESERVED, reserved - quantity.value)
        transaction = InventoryTransaction(id=uuid.uuid4(), movement_type=MovementType.SALE.value, quantity=quantity.value, from_status=StockStatus.RESERVED, to_status=None, reference=reference, occurred_at=occurred_at)
        ledger = InventoryLedger(id=uuid.uuid4(), entry_type=LedgerEntryType.SALE, stock_status=StockStatus.RESERVED, quantity_delta=-quantity.value, balance_after=self._get(StockStatus.RESERVED), reference=reference, occurred_at=occurred_at)
        return transaction, ledger

    def transfer_out(self, quantity: StockQuantity, reference: str, occurred_at: datetime) -> tuple[InventoryTransaction, InventoryLedger]:
        """AVAILABLE -> void (arrives at the destination WarehouseInventory via receive_transfer_in()) -- only AVAILABLE stock may transfer, structurally guaranteeing 'quarantine stock cannot be transferred'."""
        available = self._get(StockStatus.AVAILABLE)
        if quantity.value > available:
            raise InsufficientStock(f"Cannot transfer {quantity.value} units; only {available} available.")
        self._set(StockStatus.AVAILABLE, available - quantity.value)
        transaction = InventoryTransaction(id=uuid.uuid4(), movement_type=MovementType.TRANSFER.value, quantity=quantity.value, from_status=StockStatus.AVAILABLE, to_status=None, reference=reference, occurred_at=occurred_at)
        ledger = InventoryLedger(id=uuid.uuid4(), entry_type=LedgerEntryType.TRANSFER, stock_status=StockStatus.AVAILABLE, quantity_delta=-quantity.value, balance_after=self._get(StockStatus.AVAILABLE), reference=reference, occurred_at=occurred_at)
        return transaction, ledger

    def receive_transfer_in(self, quantity: StockQuantity, reference: str, occurred_at: datetime) -> tuple[InventoryTransaction, InventoryLedger]:
        self._set(StockStatus.AVAILABLE, self._get(StockStatus.AVAILABLE) + quantity.value)
        transaction = InventoryTransaction(id=uuid.uuid4(), movement_type=MovementType.TRANSFER.value, quantity=quantity.value, from_status=None, to_status=StockStatus.AVAILABLE, reference=reference, occurred_at=occurred_at)
        ledger = InventoryLedger(id=uuid.uuid4(), entry_type=LedgerEntryType.TRANSFER, stock_status=StockStatus.AVAILABLE, quantity_delta=quantity.value, balance_after=self._get(StockStatus.AVAILABLE), reference=reference, occurred_at=occurred_at)
        return transaction, ledger

    def mark_damaged(self, quantity: StockQuantity, reference: str, occurred_at: datetime, from_status: StockStatus = StockStatus.AVAILABLE) -> tuple[InventoryTransaction, InventoryLedger]:
        current = self._get(from_status)
        if quantity.value > current:
            raise InsufficientStock(f"Cannot damage {quantity.value} units; only {current} in '{from_status.value}'.")
        self._set(from_status, current - quantity.value)
        self._set(StockStatus.DAMAGED, self._get(StockStatus.DAMAGED) + quantity.value)
        transaction = InventoryTransaction(id=uuid.uuid4(), movement_type=MovementType.DAMAGE.value, quantity=quantity.value, from_status=from_status, to_status=StockStatus.DAMAGED, reference=reference, occurred_at=occurred_at)
        ledger = InventoryLedger(id=uuid.uuid4(), entry_type=LedgerEntryType.DAMAGE, stock_status=StockStatus.DAMAGED, quantity_delta=quantity.value, balance_after=self._get(StockStatus.DAMAGED), reference=reference, occurred_at=occurred_at)
        return transaction, ledger

    def mark_expired(self, quantity: StockQuantity, reference: str, occurred_at: datetime, from_status: StockStatus = StockStatus.AVAILABLE) -> tuple[InventoryTransaction, InventoryLedger]:
        """Moves stock INTO EXPIRED -- structurally, no method ever moves stock OUT of EXPIRED back to AVAILABLE, guaranteeing 'expired stock cannot become available'."""
        current = self._get(from_status)
        if quantity.value > current:
            raise InsufficientStock(f"Cannot expire {quantity.value} units; only {current} in '{from_status.value}'.")
        self._set(from_status, current - quantity.value)
        self._set(StockStatus.EXPIRED, self._get(StockStatus.EXPIRED) + quantity.value)
        transaction = InventoryTransaction(id=uuid.uuid4(), movement_type=MovementType.EXPIRE.value, quantity=quantity.value, from_status=from_status, to_status=StockStatus.EXPIRED, reference=reference, occurred_at=occurred_at)
        ledger = InventoryLedger(id=uuid.uuid4(), entry_type=LedgerEntryType.EXPIRE, stock_status=StockStatus.EXPIRED, quantity_delta=quantity.value, balance_after=self._get(StockStatus.EXPIRED), reference=reference, occurred_at=occurred_at)
        return transaction, ledger

    def quarantine(self, quantity: StockQuantity, reference: str, occurred_at: datetime, from_status: StockStatus = StockStatus.AVAILABLE) -> tuple[InventoryTransaction, InventoryLedger]:
        current = self._get(from_status)
        if quantity.value > current:
            raise InsufficientStock(f"Cannot quarantine {quantity.value} units; only {current} in '{from_status.value}'.")
        self._set(from_status, current - quantity.value)
        self._set(StockStatus.QUARANTINE, self._get(StockStatus.QUARANTINE) + quantity.value)
        transaction = InventoryTransaction(id=uuid.uuid4(), movement_type=MovementType.ADJUSTMENT.value, quantity=quantity.value, from_status=from_status, to_status=StockStatus.QUARANTINE, reference=reference, occurred_at=occurred_at)
        ledger = InventoryLedger(id=uuid.uuid4(), entry_type=LedgerEntryType.ADJUSTMENT, stock_status=StockStatus.QUARANTINE, quantity_delta=quantity.value, balance_after=self._get(StockStatus.QUARANTINE), reference=reference, occurred_at=occurred_at)
        return transaction, ledger

    def receive_return(self, quantity: StockQuantity, reference: str, occurred_at: datetime) -> tuple[InventoryTransaction, InventoryLedger]:
        """A customer return lands in RETURNED, not directly AVAILABLE -- it must pass an inspection step (a subsequent confirm_incoming-style transition, application-layer decision) before resale, matching the same 'incoming needs confirmation' discipline as receive()."""
        self._set(StockStatus.RETURNED, self._get(StockStatus.RETURNED) + quantity.value)
        transaction = InventoryTransaction(id=uuid.uuid4(), movement_type=MovementType.RETURN.value, quantity=quantity.value, from_status=None, to_status=StockStatus.RETURNED, reference=reference, occurred_at=occurred_at)
        ledger = InventoryLedger(id=uuid.uuid4(), entry_type=LedgerEntryType.RETURN, stock_status=StockStatus.RETURNED, quantity_delta=quantity.value, balance_after=self._get(StockStatus.RETURNED), reference=reference, occurred_at=occurred_at)
        return transaction, ledger

    def adjust(self, status: StockStatus, delta: int, reference: str, occurred_at: datetime) -> tuple[InventoryTransaction, InventoryLedger]:
        """Direct manual correction to any single bucket -- backs InventoryAdjustment; still routes through `_set()`'s negative-stock guard."""
        current = self._get(status)
        self._set(status, current + delta)
        transaction = InventoryTransaction(id=uuid.uuid4(), movement_type=MovementType.ADJUSTMENT.value, quantity=abs(delta), from_status=status if delta < 0 else None, to_status=status if delta > 0 else None, reference=reference, occurred_at=occurred_at)
        ledger = InventoryLedger(id=uuid.uuid4(), entry_type=LedgerEntryType.ADJUSTMENT, stock_status=status, quantity_delta=delta, balance_after=self._get(status), reference=reference, occurred_at=occurred_at)
        return transaction, ledger


@dataclass(slots=True)
class ShelfInventory:
    """Aggregate root -- shelf-granularity quantity within one WarehouseInventory, for precise pick/put-away tracking."""

    id: uuid.UUID
    warehouse_inventory_id: uuid.UUID
    shelf_id: uuid.UUID
    quantity: StockQuantity = field(default_factory=lambda: StockQuantity(0))

    def add(self, quantity: StockQuantity) -> None:
        self.quantity = self.quantity + quantity

    def remove(self, quantity: StockQuantity) -> None:
        self.quantity = self.quantity - quantity  # raises NegativeStock via StockQuantity.__post_init__ if it would go negative


@dataclass(slots=True)
class Reservation:
    """Aggregate root -- a hold against a WarehouseInventory's AVAILABLE stock, referenced by a future owner (Cart/Order, not yet built)."""

    id: uuid.UUID
    reservation_number: ReservationNumber
    owner_type: str
    owner_id: uuid.UUID
    warehouse_inventory_id: uuid.UUID
    status: ReservationStatus = ReservationStatus.PENDING
    expires_at: datetime | None = None
    items: dict[uuid.UUID, ReservationItem] = field(default_factory=dict)

    def add_item(self, item: ReservationItem) -> None:
        if self.status != ReservationStatus.PENDING:
            raise InvalidReservationLifecycleTransition("Cannot add items to a reservation that is not pending.")
        self.items[item.id] = item

    def total_quantity(self) -> int:
        return sum(item.quantity.value for item in self.items.values())

    def confirm(self) -> None:
        if self.status != ReservationStatus.PENDING:
            raise InvalidReservationLifecycleTransition("Only a pending reservation can be confirmed.")
        self.status = ReservationStatus.CONFIRMED

    def cancel(self) -> ReservationCancelled:
        if self.status in (ReservationStatus.CANCELLED, ReservationStatus.EXPIRED, ReservationStatus.RELEASED):
            raise InvalidReservationLifecycleTransition(f"Cannot cancel a reservation that is already {self.status.value}.")
        self.status = ReservationStatus.CANCELLED
        return ReservationCancelled(reservation_id=self.id)

    def expire(self, as_of: datetime) -> ReservationExpiredEvent:
        if self.expires_at is None or as_of < self.expires_at:
            raise ReservationExpired("This reservation has not yet reached its expiration time.")
        if self.status not in (ReservationStatus.PENDING, ReservationStatus.CONFIRMED):
            raise InvalidReservationLifecycleTransition(f"Cannot expire a reservation that is already {self.status.value}.")
        self.status = ReservationStatus.EXPIRED
        return ReservationExpiredEvent(reservation_id=self.id)


@dataclass(slots=True)
class InventoryMovement:
    """Aggregate root -- the record of one stock-affecting operation across warehouses, produced alongside (not instead of) the WarehouseInventory-level InventoryTransaction/InventoryLedger entries it caused."""

    id: uuid.UUID
    movement_type: MovementType
    reference: MovementReference
    source_warehouse_inventory_id: uuid.UUID | None = None
    destination_warehouse_inventory_id: uuid.UUID | None = None
    items: dict[uuid.UUID, MovementItem] = field(default_factory=dict)
    occurred_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.movement_type == MovementType.TRANSFER and (self.source_warehouse_inventory_id is None or self.destination_warehouse_inventory_id is None):
            raise InvalidMovement("A transfer movement requires both a source and a destination warehouse inventory.")

    def add_item(self, item: MovementItem) -> None:
        self.items[item.id] = item

    def total_quantity(self) -> int:
        return sum(item.quantity.value for item in self.items.values())


@dataclass(slots=True)
class InventoryAdjustment:
    """Aggregate root -- a manual correction record."""

    id: uuid.UUID
    warehouse_inventory_id: uuid.UUID
    reason: AdjustmentReason
    quantity_delta: int
    reference: str
    stock_status: StockStatus = StockStatus.AVAILABLE

    def __post_init__(self) -> None:
        if self.quantity_delta == 0:
            raise ValidationFailed("An adjustment must have a non-zero quantity delta.", details={"fields": [{"field": "quantity_delta", "code": "ZERO"}]})


@dataclass(slots=True)
class Batch:
    """Aggregate root -- one received lot of an Inventory item, carrying expiration/manufacture dates and owning SerialItem entities when serial-tracked."""

    id: uuid.UUID
    inventory_id: uuid.UUID
    batch_number: BatchNumber
    manufacture_date: ManufactureDate | None = None
    expiration_date: ExpirationDate | None = None
    status: BatchStatus = BatchStatus.ACTIVE
    quantity_received: StockQuantity = field(default_factory=lambda: StockQuantity(0))
    items: dict[uuid.UUID, BatchItem] = field(default_factory=dict)
    serials: dict[uuid.UUID, SerialItem] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.manufacture_date and self.expiration_date and self.expiration_date.value <= self.manufacture_date.value:
            raise ValidationFailed("expiration_date must be after manufacture_date.", details={"fields": [{"field": "expiration_date", "code": "BEFORE_MANUFACTURE_DATE"}]})

    def assert_not_expired(self, as_of: date) -> None:
        if self.status == BatchStatus.EXPIRED or (self.expiration_date and self.expiration_date.is_expired(as_of)):
            raise BatchExpired(f"Batch '{self.batch_number.value}' is expired and cannot be used.")

    def mark_expired(self, as_of: date) -> None:
        if self.expiration_date is None or not self.expiration_date.is_expired(as_of):
            raise ValidationFailed("This batch has not yet reached its expiration date.")
        if self.status == BatchStatus.DEPLETED:
            raise InvalidInventoryLifecycleTransition("A depleted batch cannot be marked expired.")
        self.status = BatchStatus.EXPIRED

    def register_serial(self, serial: SerialItem) -> SerialRegistered:
        if any(s.serial_number.value == serial.serial_number.value for s in self.serials.values()):
            raise DuplicateSerial(f"Serial number '{serial.serial_number.value}' is already registered on this batch.")
        self.serials[serial.id] = serial
        return SerialRegistered(batch_id=self.id, serial_item_id=serial.id, serial_number=serial.serial_number.value)


@dataclass(slots=True)
class CycleCount:
    """Aggregate root -- a scheduled partial stock count for one Warehouse (a subset of items, unlike PhysicalInventory's full sweep)."""

    id: uuid.UUID
    warehouse_id: uuid.UUID
    status: CycleCountStatus = CycleCountStatus.PLANNED
    counted_quantities: dict[uuid.UUID, int] = field(default_factory=dict)  # inventory_id -> counted quantity

    def start(self) -> CycleCountStarted:
        if self.status != CycleCountStatus.PLANNED:
            raise InvalidCycleCountLifecycleTransition("Only a planned cycle count can be started.")
        self.status = CycleCountStatus.IN_PROGRESS
        return CycleCountStarted(cycle_count_id=self.id, warehouse_id=self.warehouse_id)

    def record_count(self, inventory_id: uuid.UUID, counted_quantity: int) -> None:
        if self.status != CycleCountStatus.IN_PROGRESS:
            raise InvalidCycleCountLifecycleTransition("Counts can only be recorded while the cycle count is in progress.")
        if counted_quantity < 0:
            raise NegativeStock("Counted quantity must not be negative.")
        self.counted_quantities[inventory_id] = counted_quantity

    def complete(self, expected_quantities: dict[uuid.UUID, int]) -> CycleCountCompleted:
        if self.status != CycleCountStatus.IN_PROGRESS:
            raise InvalidCycleCountLifecycleTransition("Only an in-progress cycle count can be completed.")
        discrepancies = sum(1 for inv_id, counted in self.counted_quantities.items() if expected_quantities.get(inv_id) != counted)
        self.status = CycleCountStatus.COMPLETED
        return CycleCountCompleted(cycle_count_id=self.id, discrepancy_count=discrepancies)

    def cancel(self) -> None:
        if self.status == CycleCountStatus.COMPLETED:
            raise InvalidCycleCountLifecycleTransition("A completed cycle count cannot be cancelled.")
        self.status = CycleCountStatus.CANCELLED


@dataclass(slots=True)
class PhysicalInventory:
    """Aggregate root -- a full-warehouse stock count, structurally identical to CycleCount's lifecycle but scoped to every item in the warehouse rather than a sampled subset."""

    id: uuid.UUID
    warehouse_id: uuid.UUID
    status: PhysicalInventoryStatus = PhysicalInventoryStatus.PLANNED
    counted_quantities: dict[uuid.UUID, int] = field(default_factory=dict)

    def start(self) -> PhysicalInventoryStarted:
        if self.status != PhysicalInventoryStatus.PLANNED:
            raise InvalidPhysicalInventoryLifecycleTransition("Only a planned physical inventory can be started.")
        self.status = PhysicalInventoryStatus.IN_PROGRESS
        return PhysicalInventoryStarted(physical_inventory_id=self.id, warehouse_id=self.warehouse_id)

    def record_count(self, inventory_id: uuid.UUID, counted_quantity: int) -> None:
        if self.status != PhysicalInventoryStatus.IN_PROGRESS:
            raise InvalidPhysicalInventoryLifecycleTransition("Counts can only be recorded while in progress.")
        if counted_quantity < 0:
            raise NegativeStock("Counted quantity must not be negative.")
        self.counted_quantities[inventory_id] = counted_quantity

    def complete(self, expected_quantities: dict[uuid.UUID, int]) -> PhysicalInventoryCompleted:
        if self.status != PhysicalInventoryStatus.IN_PROGRESS:
            raise InvalidPhysicalInventoryLifecycleTransition("Only an in-progress physical inventory can be completed.")
        discrepancies = sum(1 for inv_id, counted in self.counted_quantities.items() if expected_quantities.get(inv_id) != counted)
        self.status = PhysicalInventoryStatus.COMPLETED
        return PhysicalInventoryCompleted(physical_inventory_id=self.id, discrepancy_count=discrepancies)


@dataclass(slots=True)
class InventorySnapshot:
    """Aggregate root -- a point-in-time capture of stock levels, for audit/rollback."""

    id: uuid.UUID
    version: SnapshotVersion
    status: InventorySnapshotStatus = InventorySnapshotStatus.PENDING
    captured_at: datetime | None = None
    items: dict[uuid.UUID, StockSnapshot] = field(default_factory=dict)

    def add_item(self, item: StockSnapshot) -> None:
        if self.status != InventorySnapshotStatus.PENDING:
            raise ValidationFailed("Cannot add items to a snapshot that is not pending.")
        self.items[item.id] = item

    def complete(self, captured_at: datetime) -> InventorySnapshotCreated:
        if self.status != InventorySnapshotStatus.PENDING:
            raise ValidationFailed("Only a pending snapshot can be completed.")
        self.status = InventorySnapshotStatus.COMPLETED
        self.captured_at = captured_at
        return InventorySnapshotCreated(snapshot_id=self.id, version=self.version.value)

    def mark_failed(self) -> None:
        self.status = InventorySnapshotStatus.FAILED
