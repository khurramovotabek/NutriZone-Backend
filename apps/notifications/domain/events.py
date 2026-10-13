"""
Notifications domain events.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class NotificationCreated:
    notification_id: uuid.UUID
    recipient_id: uuid.UUID
    notification_type: str

    def to_payload(self) -> dict:
        return {**asdict(self), "notification_id": str(self.notification_id), "recipient_id": str(self.recipient_id)}


@dataclass(frozen=True, slots=True)
class NotificationDeliverySent:
    notification_id: uuid.UUID
    delivery_id: uuid.UUID
    channel: str

    def to_payload(self) -> dict:
        return {**asdict(self), "notification_id": str(self.notification_id), "delivery_id": str(self.delivery_id)}


@dataclass(frozen=True, slots=True)
class NotificationDelivered:
    notification_id: uuid.UUID
    delivery_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"notification_id": str(self.notification_id), "delivery_id": str(self.delivery_id)}


@dataclass(frozen=True, slots=True)
class NotificationDeliveryFailed:
    notification_id: uuid.UUID
    delivery_id: uuid.UUID
    reason: str | None

    def to_payload(self) -> dict:
        return {**asdict(self), "notification_id": str(self.notification_id), "delivery_id": str(self.delivery_id)}


@dataclass(frozen=True, slots=True)
class NotificationSeen:
    notification_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"notification_id": str(self.notification_id)}


@dataclass(frozen=True, slots=True)
class NotificationRead:
    notification_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"notification_id": str(self.notification_id)}


@dataclass(frozen=True, slots=True)
class NotificationCancelled:
    notification_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"notification_id": str(self.notification_id)}


@dataclass(frozen=True, slots=True)
class NotificationChannelEnabled:
    preference_id: uuid.UUID
    user_id: uuid.UUID
    channel: str
    notification_type: str

    def to_payload(self) -> dict:
        return {**asdict(self), "preference_id": str(self.preference_id), "user_id": str(self.user_id)}


@dataclass(frozen=True, slots=True)
class NotificationChannelDisabled:
    preference_id: uuid.UUID
    user_id: uuid.UUID
    channel: str
    notification_type: str

    def to_payload(self) -> dict:
        return {**asdict(self), "preference_id": str(self.preference_id), "user_id": str(self.user_id)}
