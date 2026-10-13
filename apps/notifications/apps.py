"""
Django AppConfig for the `notifications` bounded context.

Maps 1:1 to Domain Architecture Specification 2.13 and to the
`notifications` schema defined in the Enterprise Database Blueprint §4.
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.notifications"
    label = "notifications"
    verbose_name = _("Notifications")

    def ready(self) -> None:
        """
        Wires process-wide singletons at startup, per MIC §7 and
        Django Implementation Blueprint §5, matching every prior
        module's `ready()` pattern. Local imports inside `ready()`
        are a genuine Django framework requirement (the app registry
        is not populated at module-import time), not a style choice.
        """

        from apps.notifications.infrastructure import inbox_signals  # noqa: F401 -- business events -> customer inbox
        from apps.notifications.infrastructure import admin  # noqa: F401 -- registers admin.py, which Django default discovery cannot reach at this project's infrastructure/admin.py location
        from shared.event_contracts import notifications as notifications_event_contracts  # noqa: F401

        from apps.notifications.infrastructure.health import (
            check_composition_integrity,
            check_notification_cache,
            check_notification_content_integrity,
            check_notification_outbox_backlog,
            check_notification_repository,
            check_orphaned_deliveries,
        )
        from core.health.registry import register_module_check

        register_module_check("notification_repository", check_notification_repository)
        register_module_check("notification_outbox_backlog", check_notification_outbox_backlog)
        register_module_check("notification_orphaned_deliveries", check_orphaned_deliveries)
        register_module_check("notification_content_integrity", check_notification_content_integrity)
        register_module_check("notification_composition_integrity", check_composition_integrity)
        register_module_check("notification_cache", check_notification_cache)
