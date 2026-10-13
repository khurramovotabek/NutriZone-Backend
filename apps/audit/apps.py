"""Django AppConfig for the `audit` bounded context."""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit"
    label = "audit"
    verbose_name = _("Audit")

    def ready(self) -> None:
        """Local imports inside `ready()` are a genuine Django framework requirement (the app registry is not populated at module-import time), not a style choice -- matches every prior module's `ready()` pattern."""

        from apps.audit.infrastructure import admin  # noqa: F401 -- registers admin.py, which Django default discovery cannot reach at this project's infrastructure/admin.py location
        from apps.audit.infrastructure.health import check_activity_timeline_table, check_subscriber_cursor_table
        from core.health.registry import register_module_check

        register_module_check("audit_activity_timeline_table", check_activity_timeline_table)
        register_module_check("audit_subscriber_cursor_table", check_subscriber_cursor_table)
