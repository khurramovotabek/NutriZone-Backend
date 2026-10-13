"""Django AppConfig for the `search` bounded context.

Maps 1:1 to Domain Architecture Specification 2.16 and to the
`search` schema defined in the Enterprise Database Blueprint §4.
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SearchConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.search"
    label = "search"
    verbose_name = _("Search")

    def ready(self) -> None:
        from apps.search.infrastructure import admin  # noqa: F401 -- registers admin.py (infrastructure/ is outside default discovery)
        from apps.search.infrastructure import models  # noqa: F401
