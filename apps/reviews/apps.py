"""
Django AppConfig for the `reviews` bounded context.

Maps 1:1 to Domain Architecture Specification 2.11 and to the
`reviews` schema defined in the Enterprise Database Blueprint §4.
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ReviewsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.reviews"
    label = "reviews"
    verbose_name = _("Reviews")

    def ready(self) -> None:
        """
        Wires process-wide singletons at startup, per MIC §7 and
        Django Implementation Blueprint §5, matching every prior
        module's `ready()` pattern. Local imports inside `ready()`
        are a genuine Django framework requirement (the app registry
        is not populated at module-import time), not a style choice
        -- confirmed against Wallet's/Loyalty's own identical
        `apps.py` pattern.
        """

        from apps.reviews.infrastructure import admin  # noqa: F401 -- registers admin.py, which Django default discovery cannot reach at this project's infrastructure/admin.py location
        from shared.event_contracts import reviews as reviews_event_contracts  # noqa: F401

        from apps.reviews.infrastructure.health import (
            check_composition_integrity,
            check_orphaned_media,
            check_rating_constraint_integrity,
            check_review_cache,
            check_review_outbox_backlog,
            check_review_repository,
        )
        from core.health.registry import register_module_check

        register_module_check("review_repository", check_review_repository)
        register_module_check("review_outbox_backlog", check_review_outbox_backlog)
        register_module_check("review_rating_constraint_integrity", check_rating_constraint_integrity)
        register_module_check("review_orphaned_media", check_orphaned_media)
        register_module_check("review_composition_integrity", check_composition_integrity)
        register_module_check("review_cache", check_review_cache)
