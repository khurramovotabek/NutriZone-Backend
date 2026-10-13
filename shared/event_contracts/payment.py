"""
Payment's Domain Event Catalogue registration.

Imported once from `apps/payment/apps.py::PaymentConfig.ready()`,
matching every prior module's `shared/event_contracts/*.py` pattern.
"""
from __future__ import annotations

from apps.payment.domain.events import PaymentAudited, PaymentCancelled, PaymentCreated, PaymentFailed, PaymentSucceeded
from core.events import EventContract, registry

for _event_type, _payload_cls in (
    ("PaymentCreated", PaymentCreated),
    ("PaymentSucceeded", PaymentSucceeded),
    ("PaymentFailed", PaymentFailed),
    ("PaymentCancelled", PaymentCancelled),
    ("PaymentAudited", PaymentAudited),
):
    try:
        registry.register(EventContract(event_type=_event_type, emitted_by="payment", payload_schema=_payload_cls))
    except Exception:  # noqa: BLE001 - EventContractError on duplicate registration (e.g. Django autoreload re-importing this module)
        pass
