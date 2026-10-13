"""
Django AppConfig for the `geo` bounded context (Geo & Location).

Scope note: `geo` is not one of the Domain Architecture Specification's
original eighteen bounded contexts -- see `apps/geo/domain/enums.py`'s
module docstring for the full reconciliation note.
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class GeoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.geo"
    label = "geo"
    verbose_name = _("Geo & Location")

    def ready(self) -> None:
        """
        Wires process-wide singletons at startup, per MIC §7 and Django
        Implementation Blueprint §5, matching every prior module's
        `ready()` pattern:
          1. Registers Geo's domain events against the Domain Event
             Catalogue enforcement registry.
          2. Registers Geo's own health checks against core.health.registry.
        """

        from apps.geo.infrastructure import admin  # noqa: F401 -- registers admin.py, which Django default discovery cannot reach at this project's infrastructure/admin.py location
        from shared.event_contracts import geo as geo_event_contracts  # noqa: F401

        from apps.geo.infrastructure.health import (
            check_geo_cache,
            check_geo_database,
            check_geo_outbox,
            check_geo_repository,
            check_geo_search,
        )
        from core.health.registry import register_module_check

        register_module_check("geo_repository", check_geo_repository)
        register_module_check("geo_database", check_geo_database)
        register_module_check("geo_cache", check_geo_cache)
        register_module_check("geo_outbox", check_geo_outbox)
        register_module_check("geo_search", check_geo_search)
