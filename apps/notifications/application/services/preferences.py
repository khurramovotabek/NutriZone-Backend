"""Self-service notification preferences: load (creating the all-enabled default on first use) and toggle one (channel, type) combination."""
from __future__ import annotations

import uuid

from apps.notifications.domain.aggregates import NotificationPreference
from apps.notifications.domain.enums import NotificationChannel, NotificationType


class GetOrCreatePreference:
    def __init__(self, repository) -> None:
        self._repository = repository

    def execute(self, user_id: uuid.UUID) -> NotificationPreference:
        preference = self._repository.get_by_user_id(user_id)
        if preference is None:
            preference = self._repository.save(NotificationPreference.create(preference_id=uuid.uuid4(), user_id=user_id))
        return preference


class SetPreference:
    """Idempotent: enabling an enabled combination (or disabling a disabled one) changes nothing."""

    def __init__(self, repository) -> None:
        self._repository = repository

    def execute(self, user_id: uuid.UUID, channel: NotificationChannel, notification_type: NotificationType, enabled: bool) -> NotificationPreference:
        preference = GetOrCreatePreference(self._repository).execute(user_id)
        changed = preference.enable(channel, notification_type) if enabled else preference.disable(channel, notification_type)
        if changed is not None:
            self._repository.save(preference)
        return preference
