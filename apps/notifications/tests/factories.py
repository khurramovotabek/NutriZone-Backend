"""
Test factories for Notifications domain objects -- keeps every test
file's Arrange step short and consistent. Both factories construct
aggregates exclusively through their real public `create()` factory
methods, never by direct field assignment or private-member access.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from apps.notifications.domain.aggregates import Notification, NotificationPreference
from apps.notifications.domain.enums import NotificationPriority, NotificationType
from apps.notifications.domain.value_objects import NotificationBody, NotificationTitle


def make_notification(**overrides) -> Notification:
    notification_id = overrides.pop("notification_id", uuid.uuid4())
    recipient_id = overrides.pop("recipient_id", uuid.uuid4())
    notification_type = overrides.pop("notification_type", NotificationType.TRANSACTIONAL)
    priority = overrides.pop("priority", NotificationPriority.NORMAL)
    title = overrides.pop("title", NotificationTitle("Your order shipped"))
    body = overrides.pop("body", NotificationBody("Your order is on its way."))
    at = overrides.pop("at", datetime.utcnow())
    template_key = overrides.pop("template_key", None)
    notification, _ = Notification.create(notification_id, recipient_id, notification_type, priority, title, body, at, template_key=template_key)
    for key, value in overrides.items():
        setattr(notification, key, value)
    return notification


def make_preference(**overrides) -> NotificationPreference:
    preference_id = overrides.pop("preference_id", uuid.uuid4())
    user_id = overrides.pop("user_id", uuid.uuid4())
    preference = NotificationPreference.create(preference_id, user_id)
    for key, value in overrides.items():
        setattr(preference, key, value)
    return preference
