"""Django AppConfig for the `platform` bounded context.

Maps 1:1 to Domain Architecture Specification 2.18 and to the
`platform` schema defined in the Enterprise Database Blueprint §4.
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PlatformConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.platform"
    label = "platform"
    verbose_name = _("Platform")

    def ready(self) -> None:
        """
        Wires process-wide singletons at startup, per MIC §7 and
        Django Implementation Blueprint §5, matching every prior
        module's `ready()` pattern. Local imports inside `ready()`
        are a genuine Django framework requirement (the app registry
        is not populated at module-import time), not a style choice.
        """

        from apps.platform.infrastructure import admin  # noqa: F401 -- registers admin.py, which Django default discovery cannot reach at this project's infrastructure/admin.py location
        from apps.platform.infrastructure.admin_dashboard_view import install as install_dashboard_home
        from apps.platform.infrastructure.inventory_view import install_sidebar_entry as install_inventory_sidebar_entry
        from apps.platform.infrastructure.reports_view import install as install_reports_view
        from apps.platform.infrastructure.search_view import install as install_global_search
        from shared.event_contracts import platform as platform_event_contracts  # noqa: F401

        install_dashboard_home()
        install_reports_view()
        install_global_search()
        install_inventory_sidebar_entry()
        _translate_third_party_model_names()

        from apps.platform.infrastructure.admin_labels import install as install_admin_labels

        install_admin_labels()
        _localize_admin_descriptions_on_first_request()

        from apps.platform.infrastructure.health import (
            check_composition_integrity,
            check_feature_flag_repository,
            check_flag_redis_publisher,
        )
        from core.health.registry import register_module_check

        register_module_check("platform_feature_flag_repository", check_feature_flag_repository)
        register_module_check("platform_flag_redis_publisher", check_flag_redis_publisher)
        register_module_check("platform_composition_integrity", check_composition_integrity)


def _translate_third_party_model_names() -> None:
    """simplejwt's token_blacklist models carry no gettext-wrapped verbose names, so the dashboard sidebar showed them in English whatever the language; naming them here makes them translatable like every other model."""
    from django.apps import apps

    if not apps.is_installed("rest_framework_simplejwt.token_blacklist"):
        return
    names = {
        "OutstandingToken": (_("Issued token"), _("Issued tokens")),
        "BlacklistedToken": (_("Blocked token"), _("Blocked tokens")),
    }
    for model in apps.get_app_config("token_blacklist").get_models():
        if model.__name__ in names:
            model._meta.verbose_name, model._meta.verbose_name_plural = names[model.__name__]


def _localize_admin_descriptions_on_first_request() -> None:
    """Admin classes register after every AppConfig.ready() (autodiscover), so their column/action names are localized on the first request."""
    from django.core.signals import request_started

    def handler(**_kwargs):
        request_started.disconnect(dispatch_uid="nz_admin_descriptions")
        from apps.platform.infrastructure.admin_labels import install_admin_descriptions

        install_admin_descriptions()

    request_started.connect(handler, dispatch_uid="nz_admin_descriptions", weak=False)
