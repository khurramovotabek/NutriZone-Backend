"""
Django AppConfig for the `cart` bounded context.
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CartConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.cart"
    label = "cart"
    verbose_name = _("Cart")

    def ready(self) -> None:
        """
        Wires process-wide singletons at startup, per MIC §7 and
        Django Implementation Blueprint §5, matching every prior
        module's `ready()` pattern.
        """

        from apps.cart.infrastructure import admin  # noqa: F401 -- registers admin.py, which Django default discovery cannot reach at this project's infrastructure/admin.py location
        from shared.event_contracts import cart as cart_event_contracts  # noqa: F401

        from apps.cart.infrastructure.health import (
            check_cart_cache,
            check_cart_repository,
            check_cart_state_consistency,
            check_reservation_cleanup,
            check_snapshot_validity,
        )
        from core.health.registry import register_module_check

        register_module_check("cart_repository", check_cart_repository)
        register_module_check("cart_cache", check_cart_cache)
        register_module_check("cart_state_consistency", check_cart_state_consistency)
        register_module_check("cart_reservation_cleanup", check_reservation_cleanup)
        register_module_check("cart_snapshot_validity", check_snapshot_validity)
