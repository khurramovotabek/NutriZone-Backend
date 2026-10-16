"""Support desk / CRM: phone calls and walk-in questions logged by staff, worked through a Kanban board."""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SupportConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.support"
    label = "support"
    verbose_name = _("Support (CRM)")

    def ready(self) -> None:
        from apps.support.infrastructure import admin, models  # noqa: F401
