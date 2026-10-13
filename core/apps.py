"""
Django AppConfig for `core/`.

`core/` is platform infrastructure, not a bounded context, but it needs
an `AppConfig.ready()` hook to wire process-wide singletons (the
FeatureFlags provider chain) once Django's app registry is available --
this is the one, narrow reason `core` is registered in INSTALLED_APPS
alongside the 21 business apps.
"""
from __future__ import annotations

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    label = "nutrizone_core"
    verbose_name = "NutriZone Core Infrastructure"

    def ready(self) -> None:
        from django.conf import settings

        from core.flags import (
            CachedFlagProvider,
            ChainedFlagProvider,
            EnvironmentFlagProvider,
            FeatureFlags,
            RedisFlagProvider,
        )

        try:
            redis_provider: object = CachedFlagProvider(RedisFlagProvider(), ttl_seconds=5.0)
        except Exception:  # noqa: BLE001 - Redis may be unavailable during e.g. `manage.py check`
            redis_provider = EnvironmentFlagProvider({})

        env_provider = EnvironmentFlagProvider(getattr(settings, "NUTRIZONE_INFRA_FLAGS", {}))
        FeatureFlags.configure(ChainedFlagProvider([redis_provider, env_provider]))
