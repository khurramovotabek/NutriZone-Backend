"""
Notifications domain entities (non-root members of Notification).

**Only one entity exists**: `NotificationDelivery`. This is
deliberately modeled as an owned entity, NOT a separate aggregate --
a genuine contrast with Chat's own `Message`/`Conversation` split,
explained here rather than mechanically copied: delivery attempts
have small, bounded cardinality per notification (typically 1-5
channels, never unbounded), are tightly consistency-coupled to their
parent notification (a delivery attempt has no meaning or independent
query need outside the context of its own notification), and are not
independently high-frequency-created the way Chat's messages are.
None of the factors that justified Message as a separate aggregate
apply here.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from apps.notifications.domain.enums import DeliveryStatus, NotificationChannel


@dataclass(slots=True)
class NotificationDelivery:
    """
    Owned, non-root entity -- one per channel delivery attempt.
    `provider_reference` is a plain, opaque, unvalidated optional
    string (e.g. an external provider's own message id) -- Domain
    records it as a fact but never interprets or constrains it.
    """

    id: uuid.UUID
    channel: NotificationChannel
    status: DeliveryStatus
    attempted_at: datetime
    delivered_at: datetime | None = None
    failed_at: datetime | None = None
    failure_reason: str | None = None
    provider_reference: str | None = None
