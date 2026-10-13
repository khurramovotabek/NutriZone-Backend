"""
Composition root for the `platform` module.
"""
from __future__ import annotations

import uuid

from apps.platform.application.services._shared import PlatformServiceContext
from apps.platform.application.services.flags import DefineFeatureFlag, EvaluateFlags, UpdateFeatureFlag
from apps.platform.infrastructure import models as orm
from apps.platform.infrastructure.flag_publisher import RedisFlagPublisher, to_flag_definition
from apps.platform.infrastructure.idempotency import DjangoIdempotencyExecutor
from apps.platform.infrastructure.repositories import DjangoFeatureFlagRepository
from core.flags.definitions import FlagContext
from core.flags.providers import CachedFlagProvider, RedisFlagProvider
from core.outbox import stage_event


def build_platform_service_context(actor_id: uuid.UUID | None = None) -> PlatformServiceContext:
    return PlatformServiceContext(stage_events=lambda events: [stage_event(orm.PlatformOutboxEvent, t, p) for t, p in events], actor_id=actor_id)


def build_feature_flag_repository() -> DjangoFeatureFlagRepository:
    return DjangoFeatureFlagRepository()


def build_flag_publisher() -> RedisFlagPublisher:
    return RedisFlagPublisher()


def build_define_feature_flag(actor_id=None) -> DefineFeatureFlag:
    return DefineFeatureFlag(build_feature_flag_repository(), build_flag_publisher(), build_platform_service_context(actor_id))


def build_update_feature_flag(actor_id=None) -> UpdateFeatureFlag:
    return UpdateFeatureFlag(build_feature_flag_repository(), build_flag_publisher(), build_platform_service_context(actor_id))


def build_evaluate_flags() -> EvaluateFlags:
    return EvaluateFlags(build_feature_flag_repository())


def build_flag_evaluator(context: FlagContext):
    """
    Returns the `evaluate_fn(flag) -> bool` closure `EvaluateFlags.
    execute()` needs. Prefers the fast, cached Redis path (matching
    `core.flags`'s own "Redis-only on the hot path" performance design
    -- see `core/flags/providers.py`'s docstring) and falls back to
    evaluating the already-fetched database row directly only if Redis
    has nothing cached for that key (a freshly-created flag not yet
    published, or a cold cache) -- never silently treats "no Redis
    entry" as "flag disabled" when the database row says otherwise.
    """
    fast_provider = CachedFlagProvider(RedisFlagProvider())

    def evaluate(flag) -> bool:
        cached_definition = fast_provider.get_definition(flag.key)
        definition = cached_definition if cached_definition is not None else to_flag_definition(flag)
        return definition.evaluate(context)

    return evaluate


def build_idempotency_executor() -> DjangoIdempotencyExecutor:
    """The one, reusable, PostgreSQL-backed idempotency executor every protected Application Service composes with -- see core/idempotency/contract.py for the full contract this implements."""
    return DjangoIdempotencyExecutor()


def build_get_site_settings():
    """Read-only accessor for the singleton SiteSettings row (matching SiteSettingsAdmin's own established "one row only" convention). Returns a fresh, empty-defaults instance if the row hasn't been created yet -- never raises, since a public endpoint (Contact page) must render even before an admin has configured branding."""
    from apps.platform.infrastructure.models import SiteSettings

    return SiteSettings.objects.first() or SiteSettings()
