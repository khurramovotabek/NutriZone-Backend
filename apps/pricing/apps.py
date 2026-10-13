"""
Django AppConfig for the `pricing` bounded context.
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PricingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.pricing"
    label = "pricing"
    verbose_name = _("Pricing")

    def ready(self) -> None:
        """
        Wires process-wide singletons at startup, per MIC §7 and
        Django Implementation Blueprint §5, matching every prior
        module's `ready()` pattern.
        """

        from apps.pricing.infrastructure import admin  # noqa: F401 -- registers admin.py, which Django default discovery cannot reach at this project's infrastructure/admin.py location
        from shared.event_contracts import pricing as pricing_event_contracts  # noqa: F401

        from apps.pricing.infrastructure.health import (
            check_pricing_calculation_engine,
            check_pricing_cache,
            check_pricing_campaigns,
            check_pricing_repository,
            check_pricing_snapshots,
        )
        from core.health.registry import register_module_check

        register_module_check("pricing_repository", check_pricing_repository)
        register_module_check("pricing_cache", check_pricing_cache)
        register_module_check("pricing_calculation_engine", check_pricing_calculation_engine)
        register_module_check("pricing_snapshots", check_pricing_snapshots)
        register_module_check("pricing_campaigns", check_pricing_campaigns)
