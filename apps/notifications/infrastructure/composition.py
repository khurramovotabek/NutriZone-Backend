"""
Composition root for the `notifications` module.

**A disclosed, minimal scope, matching this phase's own explicit
boundary and the identical precedent already established across
Wallet/Loyalty/Reviews/Chat Phase 2**: this composition root wires
exactly what actually exists this phase -- 2 repositories, 2
selectors, and 1 gateway. Zero Application Service factories exist
because zero Application Services exist for Notifications yet.
"""
from __future__ import annotations

import uuid

from apps.notifications.application.services._shared import NotificationServiceContext
from apps.notifications.application.services.notifications import CreateNotification
from apps.notifications.infrastructure import models as orm
from apps.notifications.infrastructure.gateways import NotImplementedTelegramGateway
from apps.notifications.infrastructure.repositories import DjangoNotificationPreferenceRepository, DjangoNotificationRepository
from apps.notifications.infrastructure.selectors import NotificationSelector, NotificationStatisticsSelector
from core.outbox import stage_event


def stage_notification_events(events: list[tuple[str, dict]]) -> None:
    for event_type, payload in events:
        stage_event(orm.NotificationOutboxEvent, event_type, payload)


def build_notification_service_context(actor_id: uuid.UUID | None = None) -> NotificationServiceContext:
    return NotificationServiceContext(stage_events=stage_notification_events, actor_id=actor_id)


def build_create_notification(actor_id: uuid.UUID | None = None) -> CreateNotification:
    return CreateNotification(DjangoNotificationRepository(), build_notification_service_context(actor_id))


def build_notification_repository() -> DjangoNotificationRepository:
    return DjangoNotificationRepository()


def build_notification_preference_repository() -> DjangoNotificationPreferenceRepository:
    return DjangoNotificationPreferenceRepository()


def build_notification_selector() -> NotificationSelector:
    return NotificationSelector()


def build_notification_statistics_selector() -> NotificationStatisticsSelector:
    return NotificationStatisticsSelector()


def build_telegram_gateway():
    from apps.notifications.infrastructure.gateways import get_telegram_gateway

    return get_telegram_gateway()


def build_orders_telegram_gateway():
    from apps.notifications.infrastructure.gateways import get_orders_telegram_gateway

    return get_orders_telegram_gateway()
