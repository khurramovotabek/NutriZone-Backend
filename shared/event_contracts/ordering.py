"""
Ordering's Domain Event Catalogue registration.

Imported once from `apps/ordering/apps.py::OrderingConfig.ready()`,
matching every prior module's `shared/event_contracts/*.py` pattern.
"""
from __future__ import annotations

from apps.ordering.domain.events import (
    CancellationApproved,
    CancellationCompleted,
    CancellationRejected,
    CancellationRequested,
    FulfillmentReferenceAdded,
    FulfillmentStatusUpdated,
    InvoiceIssued,
    LineItemCancelled,
    LineItemReturned,
    OrderArchivedEvent,
    OrderCancelled,
    OrderCompleted,
    OrderConfirmed,
    OrderCreated,
    OrderDelivered,
    OrderFailedEvent,
    OrderLockedEvent,
    OrderProcessingStarted,
    OrderRestored,
    OrderShipped,
    OrderUnlocked,
    PaymentReferenceAdded,
    PaymentStatusUpdated,
    ReturnApproved,
    ReturnReceived,
    ReturnRefunded,
    ReturnRejected,
    ReturnRequested,
)
from core.events import EventContract, registry

for _event_type, _payload_cls in (
    ("OrderCreated", OrderCreated),
    ("OrderConfirmed", OrderConfirmed),
    ("OrderProcessingStarted", OrderProcessingStarted),
    ("OrderShipped", OrderShipped),
    ("OrderDelivered", OrderDelivered),
    ("OrderCompleted", OrderCompleted),
    ("OrderCancelled", OrderCancelled),
    ("OrderFailedEvent", OrderFailedEvent),
    ("LineItemCancelled", LineItemCancelled),
    ("LineItemReturned", LineItemReturned),
    ("PaymentReferenceAdded", PaymentReferenceAdded),
    ("PaymentStatusUpdated", PaymentStatusUpdated),
    ("FulfillmentReferenceAdded", FulfillmentReferenceAdded),
    ("FulfillmentStatusUpdated", FulfillmentStatusUpdated),
    ("InvoiceIssued", InvoiceIssued),
    ("ReturnRequested", ReturnRequested),
    ("ReturnApproved", ReturnApproved),
    ("ReturnRejected", ReturnRejected),
    ("ReturnReceived", ReturnReceived),
    ("ReturnRefunded", ReturnRefunded),
    ("CancellationRequested", CancellationRequested),
    ("CancellationApproved", CancellationApproved),
    ("CancellationRejected", CancellationRejected),
    ("CancellationCompleted", CancellationCompleted),
    ("OrderLockedEvent", OrderLockedEvent),
    ("OrderUnlocked", OrderUnlocked),
    ("OrderArchivedEvent", OrderArchivedEvent),
    ("OrderRestored", OrderRestored),
):
    try:
        registry.register(EventContract(event_type=_event_type, emitted_by="ordering", payload_schema=_payload_cls))
    except Exception:  # noqa: BLE001 - EventContractError on duplicate registration (e.g. Django autoreload re-importing this module)
        pass
