"""
Inventory's Domain Event Catalogue registration.

Imported once from `apps/inventory/apps.py::InventoryConfig.ready()`,
matching every prior module's `shared/event_contracts/*.py` pattern.
"""
from __future__ import annotations

from apps.inventory.domain.events import (
    BatchCreated,
    CycleCountCompleted,
    CycleCountStarted,
    InventoryArchivedEvent,
    InventoryCreated,
    InventoryRestored,
    InventorySnapshotCreated,
    InventoryUpdated,
    PhysicalInventoryCompleted,
    PhysicalInventoryStarted,
    ReservationCancelled,
    ReservationCreated,
    ReservationExpiredEvent,
    ReservationReleased,
    SerialRegistered,
    StockAdjusted,
    StockConfirmed,
    StockDamaged,
    StockExpired,
    StockReceived,
    StockReserved,
    StockTransferred,
)
from core.events import EventContract, registry

for _event_type, _payload_cls in (
    ("InventoryCreated", InventoryCreated),
    ("InventoryUpdated", InventoryUpdated),
    ("InventoryArchivedEvent", InventoryArchivedEvent),
    ("InventoryRestored", InventoryRestored),
    ("StockReceived", StockReceived),
    ("StockConfirmed", StockConfirmed),
    ("StockReserved", StockReserved),
    ("ReservationReleased", ReservationReleased),
    ("StockTransferred", StockTransferred),
    ("StockAdjusted", StockAdjusted),
    ("StockExpired", StockExpired),
    ("StockDamaged", StockDamaged),
    ("BatchCreated", BatchCreated),
    ("SerialRegistered", SerialRegistered),
    ("ReservationCreated", ReservationCreated),
    ("ReservationCancelled", ReservationCancelled),
    ("ReservationExpiredEvent", ReservationExpiredEvent),
    ("CycleCountStarted", CycleCountStarted),
    ("CycleCountCompleted", CycleCountCompleted),
    ("PhysicalInventoryStarted", PhysicalInventoryStarted),
    ("PhysicalInventoryCompleted", PhysicalInventoryCompleted),
    ("InventorySnapshotCreated", InventorySnapshotCreated),
):
    try:
        registry.register(EventContract(event_type=_event_type, emitted_by="inventory", payload_schema=_payload_cls))
    except Exception:  # noqa: BLE001 - EventContractError on duplicate registration (e.g. Django autoreload re-importing this module)
        pass
