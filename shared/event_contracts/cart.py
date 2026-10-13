"""
Cart's Domain Event Catalogue registration.

Imported once from `apps/cart/apps.py::CartConfig.ready()`, matching
every prior module's `shared/event_contracts/*.py` pattern.
"""
from __future__ import annotations

from apps.cart.domain.events import (
    CartArchivedEvent,
    CartCleared,
    CartCreated,
    CartExpiredEvent,
    CartLockedEvent,
    CartMerged,
    CartRestored,
    CartSaved,
    CartSnapshotCreated,
    CartSnapshotRestored,
    CartUnlocked,
    CheckoutReadinessCalculated,
    CouponReferenceApplied,
    CouponReferenceRemoved,
    CustomerAssigned,
    ItemAdded,
    ItemQuantityUpdated,
    ItemRemoved,
    PriceSnapshotAttached,
    PriceSnapshotDetached,
    ReservationAttached,
    ReservationDetached,
)
from core.events import EventContract, registry

for _event_type, _payload_cls in (
    ("CartCreated", CartCreated),
    ("ItemAdded", ItemAdded),
    ("ItemRemoved", ItemRemoved),
    ("ItemQuantityUpdated", ItemQuantityUpdated),
    ("CartCleared", CartCleared),
    ("CartMerged", CartMerged),
    ("CustomerAssigned", CustomerAssigned),
    ("CouponReferenceApplied", CouponReferenceApplied),
    ("CouponReferenceRemoved", CouponReferenceRemoved),
    ("PriceSnapshotAttached", PriceSnapshotAttached),
    ("PriceSnapshotDetached", PriceSnapshotDetached),
    ("ReservationAttached", ReservationAttached),
    ("ReservationDetached", ReservationDetached),
    ("CartSaved", CartSaved),
    ("CartArchivedEvent", CartArchivedEvent),
    ("CartExpiredEvent", CartExpiredEvent),
    ("CartRestored", CartRestored),
    ("CartLockedEvent", CartLockedEvent),
    ("CartUnlocked", CartUnlocked),
    ("CartSnapshotCreated", CartSnapshotCreated),
    ("CartSnapshotRestored", CartSnapshotRestored),
    ("CheckoutReadinessCalculated", CheckoutReadinessCalculated),
):
    try:
        registry.register(EventContract(event_type=_event_type, emitted_by="cart", payload_schema=_payload_cls))
    except Exception:  # noqa: BLE001 - EventContractError on duplicate registration (e.g. Django autoreload re-importing this module)
        pass
