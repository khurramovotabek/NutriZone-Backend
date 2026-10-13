"""
POS' Domain Event Catalogue registration.

Imported once from `apps/pos/apps.py::PosConfig.ready()`, matching
every prior module's `shared/event_contracts/*.py` pattern.
"""
from __future__ import annotations

from apps.pos.domain.events import SaleCompleted, SaleCustomerSet, SaleLineItemAdded, SaleLineItemQuantityUpdated, SaleLineItemRemoved, SaleOpened, SaleRefunded, SaleVoided
from core.events import EventContract, registry

for _event_type, _payload_cls in (
    ("SaleOpened", SaleOpened),
    ("SaleCustomerSet", SaleCustomerSet),
    ("SaleLineItemAdded", SaleLineItemAdded),
    ("SaleLineItemRemoved", SaleLineItemRemoved),
    ("SaleLineItemQuantityUpdated", SaleLineItemQuantityUpdated),
    ("SaleCompleted", SaleCompleted),
    ("SaleVoided", SaleVoided),
    ("SaleRefunded", SaleRefunded),
):
    try:
        registry.register(EventContract(event_type=_event_type, emitted_by="pos", payload_schema=_payload_cls))
    except Exception:  # noqa: BLE001 - EventContractError on duplicate registration (e.g. Django autoreload re-importing this module)
        pass
