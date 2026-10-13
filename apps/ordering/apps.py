"""
Django AppConfig for the `ordering` bounded context.
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class OrderingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ordering"
    label = "ordering"
    verbose_name = _("Ordering")

    def ready(self) -> None:
        """
        Wires process-wide singletons at startup, per MIC §7 and
        Django Implementation Blueprint §5, matching every prior
        module's `ready()` pattern.
        """

        from apps.ordering.infrastructure import admin  # noqa: F401 -- registers admin.py, which Django default discovery cannot reach at this project's infrastructure/admin.py location
        from shared.event_contracts import ordering as ordering_event_contracts  # noqa: F401

        from apps.ordering.infrastructure.health import (
            check_database_consistency,
            check_expired_orders,
            check_ordering_cache,
            check_ordering_repository,
            check_outbox_pending_events,
            check_stale_returns,
        )
        from core.health.registry import register_module_check

        register_module_check("ordering_repository", check_ordering_repository)
        register_module_check("ordering_cache", check_ordering_cache)
        register_module_check("ordering_outbox_pending", check_outbox_pending_events)
        register_module_check("ordering_expired_orders", check_expired_orders)
        register_module_check("ordering_stale_returns", check_stale_returns)
        register_module_check("ordering_database_consistency", check_database_consistency)
