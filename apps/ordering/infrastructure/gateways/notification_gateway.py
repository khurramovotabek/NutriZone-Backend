"""
NotificationGateway -- Anti-Corruption Layer interface for a future
Notification module.

Unlike Payment/FulfillmentGateway, this is fire-and-forget (Ordering
doesn't need a response), so its shape is a one-way "notify" call
rather than a status query -- but it remains read-only from Ordering's
perspective in the sense that Ordering never depends on notification
success/failure to make its own domain decisions (a failed
notification never blocks an order transition).
"""
from __future__ import annotations

import uuid
from typing import Protocol


class NotificationGateway(Protocol):
    def notify_order_event(self, order_id: uuid.UUID, event_type: str, payload: dict) -> None: ...


class NotImplementedNotificationGateway:
    """Default composition-root binding until a real Notification module exists -- a no-op rather than a raise, since notification failure should never be allowed to block order processing even before a real module exists."""

    def notify_order_event(self, order_id: uuid.UUID, event_type: str, payload: dict) -> None:
        pass
