"""
Reviews' Domain Event Catalogue registration.

Imported once from `apps/reviews/apps.py::ReviewsConfig.ready()`,
matching every prior module's `shared/event_contracts/*.py` pattern.
"""
from __future__ import annotations

from apps.reviews.domain.events import (
    ReviewApproved,
    ReviewCreated,
    ReviewEdited,
    ReviewHidden,
    ReviewMediaAttached,
    ReviewPublished,
    ReviewRejected,
    ReviewSubmitted,
    ReviewWithdrawn,
)
from core.events import EventContract, registry

for _event_type, _payload_cls in (
    ("ReviewCreated", ReviewCreated),
    ("ReviewSubmitted", ReviewSubmitted),
    ("ReviewApproved", ReviewApproved),
    ("ReviewRejected", ReviewRejected),
    ("ReviewPublished", ReviewPublished),
    ("ReviewHidden", ReviewHidden),
    ("ReviewEdited", ReviewEdited),
    ("ReviewWithdrawn", ReviewWithdrawn),
    ("ReviewMediaAttached", ReviewMediaAttached),
):
    try:
        registry.register(EventContract(event_type=_event_type, emitted_by="reviews", payload_schema=_payload_cls))
    except Exception:  # noqa: BLE001 - EventContractError on duplicate registration (e.g. Django autoreload re-importing this module)
        pass
