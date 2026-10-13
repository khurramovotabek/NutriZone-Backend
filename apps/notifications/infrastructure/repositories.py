"""
Notifications repositories.

Concrete implementations of application/ports.py's `NotificationRepository`
and `NotificationPreferenceRepository` Protocols -- maps ORM rows to
domain dataclasses only, never leaks ORM objects outside this module.

**No `version` field is read from or written to the ORM against
Domain state** -- see models.py's own module docstring for the full
rationale (neither certified aggregate models one; the ORM's own
`OptimisticLockMixin` version column is maintained automatically and
is purely an Infrastructure-internal concern).
"""
from __future__ import annotations

import uuid

from django.db import IntegrityError

from apps.notifications.domain.aggregates import Notification, NotificationPreference
from apps.notifications.domain.entities import NotificationDelivery
from apps.notifications.domain.enums import DeliveryStatus, NotificationChannel, NotificationPriority, NotificationStatus, NotificationType
from apps.notifications.domain.value_objects import NotificationBody, NotificationTitle
from apps.notifications.infrastructure import models as orm
from common.exceptions import ConflictError


class DjangoNotificationRepository:
    def get_by_id(self, notification_id: uuid.UUID) -> Notification | None:
        row = orm.NotificationModel.objects.filter(id=notification_id).prefetch_related("deliveries").first()
        return self._to_domain(row) if row else None

    def save(self, notification: Notification) -> Notification:
        try:
            row, _ = orm.NotificationModel.objects.update_or_create(
                id=notification.id,
                defaults={
                    "recipient_id": notification.recipient_id, "notification_type": notification.notification_type.value,
                    "priority": notification.priority.value, "title": notification.title.value, "body": notification.body.value,
                    "template_key": notification.template_key, "status": notification.status.value,
                    "seen_at": notification.seen_at, "read_at": notification.read_at, "created_at": notification.created_at,
                },
            )
        except IntegrityError as exc:
            raise ConflictError("A notification with conflicting unique fields already exists.") from exc

        existing_delivery_ids = set(row.deliveries.values_list("id", flat=True))
        for delivery in notification.deliveries.values():
            if delivery.id not in existing_delivery_ids:
                orm.NotificationDeliveryModel.objects.create(id=delivery.id, notification=row, channel=delivery.channel.value, status=delivery.status.value, attempted_at=delivery.attempted_at, delivered_at=delivery.delivered_at, failed_at=delivery.failed_at, failure_reason=delivery.failure_reason, provider_reference=delivery.provider_reference)
            else:
                orm.NotificationDeliveryModel.objects.filter(id=delivery.id).update(status=delivery.status.value, delivered_at=delivery.delivered_at, failed_at=delivery.failed_at, failure_reason=delivery.failure_reason, provider_reference=delivery.provider_reference)
        return notification

    def list_for_recipient(self, recipient_id: uuid.UUID, status: str | None, page: int, page_size: int) -> tuple[list[Notification], int]:
        qs = orm.NotificationModel.objects.filter(recipient_id=recipient_id)
        if status:
            qs = qs.filter(status=status)
        total = qs.count()
        rows = qs.order_by("-created_at")[(page - 1) * page_size : page * page_size]
        return [self._to_domain(r) for r in rows], total

    def _to_domain(self, row: orm.NotificationModel) -> Notification:
        deliveries = {}
        for d in row.deliveries.all():
            delivery = NotificationDelivery(id=d.id, channel=NotificationChannel(d.channel), status=DeliveryStatus(d.status), attempted_at=d.attempted_at, delivered_at=d.delivered_at, failed_at=d.failed_at, failure_reason=d.failure_reason, provider_reference=d.provider_reference)
            deliveries[delivery.id] = delivery

        return Notification(
            id=row.id, recipient_id=row.recipient_id, notification_type=NotificationType(row.notification_type),
            priority=NotificationPriority(row.priority), title=NotificationTitle(row.title), body=NotificationBody(row.body),
            template_key=row.template_key, status=NotificationStatus(row.status), deliveries=deliveries,
            created_at=row.created_at, seen_at=row.seen_at, read_at=row.read_at,
        )


class DjangoNotificationPreferenceRepository:
    def get_by_user_id(self, user_id: uuid.UUID) -> NotificationPreference | None:
        row = orm.NotificationPreferenceModel.objects.filter(user_id=user_id).first()
        return self._to_domain(row) if row else None

    def save(self, preference: NotificationPreference) -> NotificationPreference:
        try:
            orm.NotificationPreferenceModel.objects.update_or_create(
                id=preference.id,
                defaults={
                    "user_id": preference.user_id,
                    "disabled_combinations": [[c.value, t.value] for c, t in preference.disabled_combinations],
                },
            )
        except IntegrityError as exc:
            raise ConflictError("A notification preference for this user already exists.") from exc
        return preference

    def _to_domain(self, row: orm.NotificationPreferenceModel) -> NotificationPreference:
        disabled = {(NotificationChannel(c), NotificationType(t)) for c, t in row.disabled_combinations}
        return NotificationPreference(id=row.id, user_id=row.user_id, disabled_combinations=disabled)
