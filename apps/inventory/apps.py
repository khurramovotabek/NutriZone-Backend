"""
Django AppConfig for the `inventory` bounded context.
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class InventoryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.inventory"
    label = "inventory"
    verbose_name = _("Inventory")

    def ready(self) -> None:
        """
        Wires process-wide singletons at startup, per MIC §7 and
        Django Implementation Blueprint §5, matching every prior
        module's `ready()` pattern:
          1. Registers Inventory's domain events against the Domain
             Event Catalogue enforcement registry.
          2. Registers Inventory's own health checks against
             core.health.registry.
        """

        from apps.inventory.infrastructure import admin  # noqa: F401 -- registers admin.py, which Django default discovery cannot reach at this project's infrastructure/admin.py location
        from shared.event_contracts import inventory as inventory_event_contracts  # noqa: F401

        from apps.inventory.infrastructure.health import (
            check_inventory_batch,
            check_inventory_cache,
            check_inventory_ledger,
            check_inventory_repository,
            check_inventory_reservation,
            check_inventory_snapshot,
        )
        from core.health.registry import register_module_check

        register_module_check("inventory_repository", check_inventory_repository)
        register_module_check("inventory_cache", check_inventory_cache)
        register_module_check("inventory_ledger", check_inventory_ledger)
        register_module_check("inventory_snapshot", check_inventory_snapshot)
        register_module_check("inventory_batch", check_inventory_batch)
        register_module_check("inventory_reservation", check_inventory_reservation)
