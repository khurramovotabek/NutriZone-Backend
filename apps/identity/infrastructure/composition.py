"""
Composition root for the `identity` module's interfaces layer.

Wires concrete `infrastructure/` implementations into `application/
services/` constructors (dependency injection at the entrypoint, per
Django Implementation Blueprint §4) so `interfaces/api/v1/views.py`
never imports a repository/gateway class directly -- a view calls a
`build_*()` factory here and gets back a ready-to-use Application
Service. Centralizing this wiring in one file also means adding a new
concrete implementation (e.g. swapping `ConsoleOTPProvider` for
`EskizOTPProvider` in production) touches this file, not every view
that happens to need OTP delivery.
"""
from __future__ import annotations

from apps.identity.application.services.auth import Logout, LogoutAll, RefreshToken, RequestOTP, VerifyOTP
from apps.identity.application.services.profile import GetOwnProfile, SetAvatar, UpdateProfile, UploadAvatar
from apps.identity.application.services.roles import (
    AssignRole,
    CheckPermission,
    RemoveRole,
    SetRolePermissions,
)
from apps.identity.application.services.sessions import ListOwnSessions, RevokeSession
from apps.identity.application.services.staff import AdminGetUser, AdminListUsers, AdminUpdateUserStatus
from apps.identity.infrastructure import models as orm
from apps.identity.infrastructure.gateways.otp_providers import get_otp_provider
from apps.identity.infrastructure.repositories import (
    DjangoAvatarAssetRepository,
    DjangoOTPChallengeRepository,
    DjangoPermissionRepository,
    DjangoRoleAssignmentRepository,
    DjangoRoleRepository,
    DjangoUserRepository,
    DjangoUserSessionRepository,
)
from apps.identity.infrastructure.security import SimpleJWTTokenIssuer, hash_otp_code
from core.media import MediaPipeline, NoOpVirusScanner, PillowImageOptimizer
from core.outbox import stage_event
from core.storage import get_storage_backend


def stage_identity_events(events: list[tuple[str, dict]]) -> None:
    """The `stage_events` callable every auth/profile/roles service is constructed with."""
    for event_type, payload in events:
        stage_event(orm.IdentityOutboxEvent, event_type, payload)


def _otp_max_requests_per_hour() -> int:
    """Reads the real OTP_MAX_REQUESTS_PER_HOUR setting (default 3, matching OTPPolicy's own unchanged production quota) -- the one place environment configuration is allowed to reach this business rule, per MIC §4."""
    from django.conf import settings

    return settings.OTP_MAX_REQUESTS_PER_HOUR


def build_request_otp() -> RequestOTP:
    return RequestOTP(
        otp_repo=DjangoOTPChallengeRepository(),
        user_repo=DjangoUserRepository(),
        otp_provider=get_otp_provider(),
        hash_otp_code=hash_otp_code,
        max_requests_per_hour=_otp_max_requests_per_hour(),
    )


def build_request_telegram_otp() -> RequestOTP:
    """
    Explicitly uses TelegramOTPProvider, independent of the global
    NUTRIZONE_OTP_PROVIDER setting -- lets a dedicated "Telegram code
    login" endpoint exist side-by-side with the existing default
    (SMS-shaped) request-otp endpoint, rather than requiring the
    entire deployment's default provider to be switched. Reuses the
    exact same RequestOTP service, rate limiting, and
    OTPCodeChallenge model -- only the delivery channel differs.
    """
    from apps.identity.infrastructure.gateways.otp_providers import TelegramOTPProvider

    return RequestOTP(
        otp_repo=DjangoOTPChallengeRepository(),
        user_repo=DjangoUserRepository(),
        otp_provider=TelegramOTPProvider(),
        hash_otp_code=hash_otp_code,
        max_requests_per_hour=_otp_max_requests_per_hour(),
    )


def _assign_default_customer_role(user_id) -> None:
    """
    Phase 09.4b: closes the confirmed customer-permission-bootstrap
    gap (Phases 09.2/09.3/09.4 all independently found this missing).
    Looks up the "customer" Role seeded by
    infrastructure/migrations/0002_seed_customer_role.py and assigns
    it directly -- no "already assigned" check needed since this is
    only ever called for a brand-new user inside VerifyOTP's own
    transaction.
    """
    role = orm.Role.objects.filter(code="customer").first()
    if role is None:
        return  # Fails open on missing seed data rather than blocking registration entirely -- a genuinely missing role is an ops/migration problem, not a reason to prevent account creation.
    orm.UserRole.objects.get_or_create(user_id=user_id, role_id=role.id, store_id=None)


def build_verify_otp() -> VerifyOTP:
    return VerifyOTP(
        otp_repo=DjangoOTPChallengeRepository(),
        user_repo=DjangoUserRepository(),
        session_repo=DjangoUserSessionRepository(),
        token_issuer=SimpleJWTTokenIssuer(),
        hash_otp_code=hash_otp_code,
        stage_events=stage_identity_events,
        default_role_assigner=_assign_default_customer_role,
    )


def build_complete_telegram_auth_session():
    from apps.identity.application.services.auth import IssueAuthenticationForUser
    from apps.identity.application.services.telegram_auth import CompleteTelegramAuthSession

    issuer = IssueAuthenticationForUser(session_repo=DjangoUserSessionRepository(), token_issuer=SimpleJWTTokenIssuer(), stage_events=stage_identity_events)
    return CompleteTelegramAuthSession(issue_authentication=issuer)


def build_refresh_token() -> RefreshToken:
    return RefreshToken(
        session_repo=DjangoUserSessionRepository(),
        token_issuer=SimpleJWTTokenIssuer(),
        user_repo=DjangoUserRepository(),
        stage_events=stage_identity_events,
    )


def build_logout() -> Logout:
    return Logout(session_repo=DjangoUserSessionRepository(), token_issuer=SimpleJWTTokenIssuer(), stage_events=stage_identity_events)


def build_logout_all() -> LogoutAll:
    return LogoutAll(session_repo=DjangoUserSessionRepository())


def build_get_own_profile() -> GetOwnProfile:
    return GetOwnProfile(user_repo=DjangoUserRepository())


def build_update_profile() -> UpdateProfile:
    return UpdateProfile(user_repo=DjangoUserRepository(), stage_events=stage_identity_events)


def build_set_avatar() -> SetAvatar:
    return SetAvatar(user_repo=DjangoUserRepository())


def build_upload_avatar() -> UploadAvatar:
    media_pipeline = MediaPipeline(
        storage=get_storage_backend(),
        virus_scanner=NoOpVirusScanner(),
        image_optimizer=PillowImageOptimizer(),
    )
    return UploadAvatar(
        user_repo=DjangoUserRepository(),
        avatar_repo=DjangoAvatarAssetRepository(),
        media_pipeline=media_pipeline,
        stage_events=stage_identity_events,
    )


def build_list_own_sessions() -> ListOwnSessions:
    return ListOwnSessions(session_repo=DjangoUserSessionRepository())


def build_revoke_session() -> RevokeSession:
    return RevokeSession(session_repo=DjangoUserSessionRepository(), stage_events=stage_identity_events)


def build_admin_list_users() -> AdminListUsers:
    return AdminListUsers(user_repo=DjangoUserRepository())


def build_admin_get_user() -> AdminGetUser:
    return AdminGetUser(user_repo=DjangoUserRepository())


def build_admin_update_user_status() -> AdminUpdateUserStatus:
    return AdminUpdateUserStatus(user_repo=DjangoUserRepository(), stage_events=stage_identity_events)


def build_assign_role() -> AssignRole:
    return AssignRole(role_repo=DjangoRoleRepository(), assignment_repo=DjangoRoleAssignmentRepository(), stage_events=stage_identity_events)


def build_remove_role() -> RemoveRole:
    return RemoveRole(assignment_repo=DjangoRoleAssignmentRepository())


def build_set_role_permissions() -> SetRolePermissions:
    return SetRolePermissions(role_repo=DjangoRoleRepository(), permission_repo=DjangoPermissionRepository())


def build_check_permission() -> CheckPermission:
    return CheckPermission(assignment_repo=DjangoRoleAssignmentRepository())
