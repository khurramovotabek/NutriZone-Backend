"""
Notifications' Domain Event Catalogue registration.

Imported once from `apps/notifications/apps.py::NotificationsConfig.
ready()`, matching every prior module's `shared/event_contracts/*.py`
pattern.
"""
from __future__ import annotations

from apps.notifications.domain.events import (
    NotificationCancelled,
    NotificationChannelDisabled,
    NotificationChannelEnabled,
    NotificationCreated,
    NotificationDelivered,
    NotificationDeliveryFailed,
    NotificationDeliverySent,
    NotificationRead,
    NotificationSeen,
)
from core.events import EventContract, registry

for _event_type, _payload_cls in (
    ("NotificationCreated", NotificationCreated),
    ("NotificationDeliverySent", NotificationDeliverySent),
    ("NotificationDelivered", NotificationDelivered),
    ("NotificationDeliveryFailed", NotificationDeliveryFailed),
    ("NotificationSeen", NotificationSeen),
    ("NotificationRead", NotificationRead),
    ("NotificationCancelled", NotificationCancelled),
    ("NotificationChannelEnabled", NotificationChannelEnabled),
    ("NotificationChannelDisabled", NotificationChannelDisabled),
):
    try:
        registry.register(EventContract(event_type=_event_type, emitted_by="notifications", payload_schema=_payload_cls))
    except Exception:  # noqa: BLE001 - EventContractError on duplicate registration (e.g. Django autoreload re-importing this module)
        pass
