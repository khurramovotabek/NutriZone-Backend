"""Django AppConfig for the `assistant` context: NutriZone's AI shopping assistant (Claude) for storefront customers."""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AssistantConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.assistant"
    label = "assistant"
    verbose_name = _("AI maslahatchi")

    def ready(self) -> None:
        from apps.assistant.infrastructure import (
            admin,  # noqa: F401 -- registers admin.py (infrastructure/ is outside default discovery)
            models,  # noqa: F401
        )
