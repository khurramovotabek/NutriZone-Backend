"""
Application-layer ports (abstract interfaces) for Notifications.

**A disclosed, minimal exception, matching the identical precedent
already established in every prior module's own Phase 2**
(Wallet/Loyalty/Reviews/Chat): this file's brief requires
Infrastructure's repositories to fulfill Ports, and every prior
module places Ports in `application/ports.py`, never in
`infrastructure/`. Two Protocols exist -- one per certified aggregate
root, since Notifications' Domain deliberately has two independent
aggregates (`Notification`, `NotificationPreference`). Zero business
logic, zero Application Services, zero service context. Nothing else
in `application/` was touched this phase.
"""
from __future__ import annotations

import uuid
from typing import Protocol

from apps.notifications.domain.aggregates import Notification, NotificationPreference


class NotificationRepository(Protocol):
    def get_by_id(self, notification_id: uuid.UUID) -> Notification | None: ...

    def save(self, notification: Notification) -> Notification: ...

    def list_for_recipient(self, recipient_id: uuid.UUID, status: str | None, page: int, page_size: int) -> tuple[list[Notification], int]: ...


class NotificationPreferenceRepository(Protocol):
    def get_by_user_id(self, user_id: uuid.UUID) -> NotificationPreference | None: ...

    def save(self, preference: NotificationPreference) -> NotificationPreference: ...
