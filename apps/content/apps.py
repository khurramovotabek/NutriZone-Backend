"""Django AppConfig for the `content` bounded context.

Maps 1:1 to Domain Architecture Specification 2.17 and to the
`content` schema defined in the Enterprise Database Blueprint §4.
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ContentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.content"
    label = "content"
    verbose_name = _("Content")

    def ready(self) -> None:
        from apps.content.infrastructure import admin  # noqa: F401 -- registers admin.py, which Django default discovery cannot reach at this project's infrastructure/admin.py location
        from apps.content.infrastructure import models  # noqa: F401
