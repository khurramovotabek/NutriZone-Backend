"""
Django AppConfig for the `pos` bounded context.

Maps 1:1 to Domain Architecture Specification §2.15 and to the `pos`
schema defined in the Enterprise Database Blueprint §4.
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.pos"
    label = "pos"
    verbose_name = _("POS")

    def ready(self) -> None:
        """
        Wires process-wide singletons at startup, per MIC §7 and
        Django Implementation Blueprint §5, matching every prior
        module's `ready()` pattern. Local imports inside `ready()`
        are a genuine Django framework requirement (the app registry
        is not populated at module-import time), not a style choice.
        """

        from apps.pos.infrastructure import admin  # noqa: F401 -- registers admin.py, which Django default discovery cannot reach at this project's infrastructure/admin.py location
        from shared.event_contracts import pos as pos_event_contracts  # noqa: F401

        from apps.pos.infrastructure.health import (
            check_composition_integrity,
            check_orphaned_sale_line_items,
            check_pos_cache,
            check_pos_outbox_backlog,
            check_sale_line_item_integrity,
            check_sale_repository,
        )
        from core.health.registry import register_module_check

        register_module_check("pos_sale_repository", check_sale_repository)
        register_module_check("pos_outbox_backlog", check_pos_outbox_backlog)
        register_module_check("pos_orphaned_sale_line_items", check_orphaned_sale_line_items)
        register_module_check("pos_sale_line_item_integrity", check_sale_line_item_integrity)
        register_module_check("pos_composition_integrity", check_composition_integrity)
        register_module_check("pos_cache", check_pos_cache)
