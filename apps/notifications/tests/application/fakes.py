"""
Fake implementations of Notifications' two Application-layer Ports.
"""
from __future__ import annotations


class FakeNotificationRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, notification_id):
        return self.by_id.get(notification_id)

    def save(self, notification):
        self.by_id[notification.id] = notification
        return notification

    def list_for_recipient(self, recipient_id, status, page, page_size):
        results = [n for n in self.by_id.values() if n.recipient_id == recipient_id]
        if status:
            results = [n for n in results if n.status.value == status]
        return results[(page - 1) * page_size : page * page_size], len(results)


class FakeNotificationPreferenceRepository:
    def __init__(self) -> None:
        self.by_user_id: dict = {}

    def get_by_user_id(self, user_id):
        return self.by_user_id.get(user_id)

    def save(self, preference):
        self.by_user_id[preference.user_id] = preference
        return preference
