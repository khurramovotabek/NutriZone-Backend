"""
Notifications Application Services. Phase 02G's own first services --
`apps/notifications/application/ports.py`'s own docstring explicitly
disclosed "zero Application Services, zero service context" before
this phase, confirmed by direct inspection of `application/services/`
containing only an empty `__init__.py`.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from django.db import transaction
from django.utils import timezone as django_timezone

from apps.notifications.application.ports import NotificationRepository
from apps.notifications.application.services._shared import NotificationServiceContext
from apps.notifications.domain.aggregates import Notification
from apps.notifications.domain.enums import NotificationPriority, NotificationType
from apps.notifications.domain.value_objects import NotificationBody, NotificationTitle


def _now() -> datetime:
    return django_timezone.now()


class CreateNotification:
    """Wraps `Notification.create()` (the domain's own static factory), persists it, and stages `NotificationCreated` -- the same shape every other module's own creation service already establishes."""

    def __init__(self, repo: NotificationRepository, ctx: NotificationServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(
        self, recipient_id: uuid.UUID, notification_type: NotificationType, priority: NotificationPriority,
        title: str, body: str, template_key: str | None = None,
    ) -> Notification:
        notification, event = Notification.create(
            notification_id=uuid.uuid4(), recipient_id=recipient_id, notification_type=notification_type,
            priority=priority, title=NotificationTitle(title), body=NotificationBody(body),
            at=_now(), template_key=template_key,
        )
        saved = self._repo.save(notification)
        self._ctx.stage_events([("NotificationCreated", event.to_payload())])
        self._ctx.audit().created(entity_type="Notification", entity_id=str(notification.id), after={"recipient_id": str(recipient_id), "notification_type": notification_type.value})
        self._ctx.invalidate_notification_cache()
        self._ctx.metric("notifications_created_total", type=notification_type.value)
        return saved
