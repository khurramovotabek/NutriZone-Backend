"""
Store Management's Domain Event Catalogue registration.

Imported once from `apps/store/apps.py::StoreConfig.ready()`, matching
every prior module's `shared/event_contracts/*.py` pattern.
"""
from __future__ import annotations

from apps.store.domain.events import (
    BranchCreated,
    CoverageUpdated,
    EmployeeAssigned,
    EmployeeRemoved,
    HolidayAdded,
    HolidayRemoved,
    ManagerAssigned,
    ScheduleUpdated,
    ShelfCreated,
    StoreArchived,
    StoreActivated,
    StoreClosed,
    StoreCreated,
    StoreEntityDeleted,
    StoreRestored,
    StoreSettingsUpdated,
    StoreSuspended,
    StoreUpdated,
    WarehouseCreated,
    WarehouseUpdated,
)
from core.events import EventContract, registry

for _event_type, _payload_cls in (
    ("StoreCreated", StoreCreated),
    ("StoreUpdated", StoreUpdated),
    ("StoreActivated", StoreActivated),
    ("StoreSuspended", StoreSuspended),
    ("StoreClosed", StoreClosed),
    ("StoreArchived", StoreArchived),
    ("StoreRestored", StoreRestored),
    ("BranchCreated", BranchCreated),
    ("WarehouseCreated", WarehouseCreated),
    ("WarehouseUpdated", WarehouseUpdated),
    ("ShelfCreated", ShelfCreated),
    ("CoverageUpdated", CoverageUpdated),
    ("EmployeeAssigned", EmployeeAssigned),
    ("EmployeeRemoved", EmployeeRemoved),
    ("ManagerAssigned", ManagerAssigned),
    ("ScheduleUpdated", ScheduleUpdated),
    ("HolidayAdded", HolidayAdded),
    ("HolidayRemoved", HolidayRemoved),
    ("StoreSettingsUpdated", StoreSettingsUpdated),
    ("StoreEntityDeleted", StoreEntityDeleted),
):
    try:
        registry.register(EventContract(event_type=_event_type, emitted_by="store", payload_schema=_payload_cls))
    except Exception:  # noqa: BLE001 - EventContractError on duplicate registration (e.g. Django autoreload re-importing this module)
        pass
