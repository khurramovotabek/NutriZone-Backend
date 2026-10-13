"""
Django AppConfig for the `products` bounded context (Products &
Catalog, Domain Architecture Specification §2.2).
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ProductsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.products"
    label = "products"
    verbose_name = _("Products & Catalog")

    def ready(self) -> None:
        """
        Wires process-wide singletons at startup, per MIC §7 and
        Django Implementation Blueprint §5, matching
        `apps.identity.apps.IdentityConfig.ready()`'s exact pattern:
          1. Registers Products' domain events against the Domain
             Event Catalogue enforcement registry (core.events.registry).
          2. Registers Products' own health checks (repository, media
             storage, search, cache, outbox, event registration)
             against core.health.registry.
        """

        from apps.products.infrastructure import admin  # noqa: F401 -- registers admin.py, which Django default discovery cannot reach at this project's infrastructure/admin.py location
        from shared.event_contracts import products as products_event_contracts  # noqa: F401

        from apps.products.infrastructure.health import (
            check_products_cache,
            check_products_event_registration,
            check_products_media_storage,
            check_products_outbox,
            check_products_repository,
            check_products_search,
        )
        from core.health.registry import register_module_check

        register_module_check("products_repository", check_products_repository)
        register_module_check("products_media_storage", check_products_media_storage)
        register_module_check("products_search", check_products_search)
        register_module_check("products_cache", check_products_cache)
        register_module_check("products_outbox", check_products_outbox)
        register_module_check("products_event_registration", check_products_event_registration)

        # Smart search index (infrastructure/smart_search.py): any write to
        # what it indexes makes the next search rebuild it. dispatch_uid
        # keeps this idempotent if ready() ever runs twice.
        from django.db.models.signals import post_delete, post_save

        from apps.products.infrastructure import models as orm
        from apps.products.infrastructure.smart_search import invalidate_index

        for model in (orm.Product, orm.ProductTranslation, orm.ProductVariant, orm.Brand, orm.BrandTranslation, orm.Category, orm.CategoryTranslation):
            for signal in (post_save, post_delete):
                signal.connect(invalidate_index, sender=model, dispatch_uid=f"smart_search_invalidate_{signal is post_save}_{model.__name__}")
