"""
Django AppConfig for the `identity` bounded context.

Maps 1:1 to Domain Architecture Specification §2.1 and to the
`identity` schema defined in the Enterprise Database Blueprint §4.
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class IdentityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.identity"
    label = "identity"
    verbose_name = _("Identity")

    def ready(self) -> None:
        """
        Wires process-wide singletons at startup, per MIC §7 and Django
        Implementation Blueprint §5:
          1. Registers identity's domain events against the Domain
             Event Catalogue enforcement registry (core.events.registry)
             -- required before stage_event() will accept them.
          2. Wires identity's CheckPermission as the concrete
             PermissionResolver every other app's HasPermissionCode
             permission class calls (common/permissions/permissions.py).
          3. Registers identity's own health checks (repository, OTP
             provider, token issuer) against core.health.registry.
        """

        from apps.identity.infrastructure import admin  # noqa: F401 -- registers admin.py, which Django default discovery cannot reach at this project's infrastructure/admin.py location
        from shared.event_contracts import identity as identity_event_contracts  # noqa: F401

        from apps.identity.application.services.roles import CheckPermission
        from apps.identity.infrastructure.health import (
            check_identity_repository,
            check_otp_provider,
            check_token_issuer,
        )
        from apps.identity.infrastructure.repositories import DjangoRoleAssignmentRepository
        from common.permissions import HasPermissionCode
        from core.health.registry import register_module_check

        HasPermissionCode.resolver = CheckPermission(DjangoRoleAssignmentRepository())

        register_module_check("identity_repository", check_identity_repository)
        register_module_check("identity_otp_provider", check_otp_provider)
        register_module_check("identity_token_issuer", check_token_issuer)
