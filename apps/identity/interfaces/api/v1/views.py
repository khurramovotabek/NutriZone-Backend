"""
Identity API views.

Thin per Django Implementation Blueprint §3: each view deserializes
the request, calls exactly one Application Service (built via
infrastructure/composition.py), and returns the result through the
standard response envelope (common/responses/). No business logic
lives here -- every validation/decision the mission's quality gates
ask to verify ("No business logic in serializers/views/models") is
delegated to `application/`/`domain/`.

Every authenticated view relies on `request.user` being an
`IdentityUserProxy` (infrastructure/authentication.py) -- exposed as
`request.identity` via a small property shim below, matching this
phase's explicit "every request must expose request.identity instead
of relying on Django User" requirement.
"""
from __future__ import annotations

import uuid

from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.identity.domain.enums import DeviceType
from apps.identity.infrastructure import composition
from apps.identity.interfaces.api.v1.filters import parse_admin_user_list_params
from apps.identity.interfaces.api.v1.permissions import IsAuthenticatedIdentityUser
from apps.identity.interfaces.api.v1.serializers import (
    AdminUpdateUserStatusSerializer,
    AdminUserDetailSerializer,
    AdminUserListItemSerializer,
    AvatarUploadSerializer,
    LogoutSerializer,
    RefreshTokenSerializer,
    RequestOTPSerializer,
    TokenPairResponseSerializer,
    UpdateProfileSerializer,
    UserProfileSerializer,
    UserSessionSerializer,
    VerifyCodeOnlySerializer,
    VerifyOTPSerializer,
)
from common.exceptions import ValidationFailed
from common.responses import paginated_response, success_response
from core.metrics import default_collector
from core.observability import timed
from core.ratelimit import ScopedRateLimitThrottle
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema

from core.openapi import STANDARD_ERROR_RESPONSES, auth_examples, error_examples


def _responses(*codes: int) -> dict:
    """Subsets Enterprise REST API Blueprint §17's standard error response set for one endpoint's OpenAPI documentation."""
    return {code: STANDARD_ERROR_RESPONSES[code] for code in codes}


def _client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _attach_identity(request) -> None:
    """Exposes `request.identity` as an alias of `request.user` (this phase's explicit requirement) without a second auth round-trip."""
    request.identity = request.user


# --- Rate-limit throttle classes (mission §11) -----------------------

class OTPRequestThrottle(ScopedRateLimitThrottle):
    scope = "identity.otp_request"
    limit = 3
    window_seconds = 3600
    identifier_source = "field:phone_number"


class OTPVerifyThrottle(ScopedRateLimitThrottle):
    scope = "identity.otp_verify"
    limit = 10
    window_seconds = 3600
    identifier_source = "field:phone_number"


class LoginThrottle(ScopedRateLimitThrottle):
    scope = "identity.login"
    limit = 20
    window_seconds = 3600
    identifier_source = "ip"


class RefreshThrottle(ScopedRateLimitThrottle):
    scope = "identity.refresh"
    limit = 30
    window_seconds = 3600
    identifier_source = "ip"


class ProfileUpdateThrottle(ScopedRateLimitThrottle):
    scope = "identity.profile_update"
    limit = 30
    window_seconds = 3600
    identifier_source = "user"


class AdminOperationThrottle(ScopedRateLimitThrottle):
    scope = "identity.admin_operation"
    limit = 300
    window_seconds = 3600
    identifier_source = "user"


# --- Authentication ----------------------------------------------------

class RequestOTPView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [OTPRequestThrottle, LoginThrottle]

    @extend_schema(
        tags=["Identity"],
        summary="Request an OTP code",
        description="Sends a 6-digit verification code to the given phone number via the configured OTP provider. Rate-limited to 3 requests/hour per phone number (Architecture Review §14).",
        request=RequestOTPSerializer,
        examples=error_examples(),
        responses={202: OpenApiResponse(description="Code sent"), **_responses(422, 429, 503)},
    )
    def post(self, request):
        from django.conf import settings
        from apps.identity.domain.exceptions import OTPDeliveryFailedError

        if not getattr(settings, "NUTRIZONE_SMS_LOGIN_ENABLED", False):
            # Temporarily disabled per explicit product decision -- Telegram
            # is the sole customer login path for now. A simple, reversible
            # settings toggle (NUTRIZONE_SMS_LOGIN_ENABLED), not a deletion --
            # flip it back to re-enable, no code changes needed.
            raise OTPDeliveryFailedError("SMS login is temporarily unavailable. Please log in via Telegram instead.")

        serializer = RequestOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with timed("identity.request_otp"):
            composition.build_request_otp().execute(
                phone_number_raw=serializer.validated_data["phone_number"], ip_address=_client_ip(request)
            )
        default_collector.counter("identity_otp_requested_total")
        return success_response(data={"message": "Verification code sent."}, status_code=202)


class RequestTelegramLoginCodeView(APIView):
    """
    Telegram-first authentication: sends the same kind of 6-digit
    code as RequestOTPView, but exclusively via the user's already-
    linked Telegram account (TelegramOTPProvider) instead of SMS.
    Reuses RequestOTPSerializer and VerifyOTPView unchanged -- the
    existing /auth/verify-otp endpoint already correctly verifies a
    Telegram-delivered code, since VerifyOTP has no dependency on how
    the code was delivered.

    If the phone number has no linked Telegram account,
    TelegramOTPProvider raises a clear OTPProviderNonRetryableError
    (surfaced by RequestOTP's own existing error handling) rather
    than silently falling back to SMS or fabricating success.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [OTPRequestThrottle, LoginThrottle]

    @extend_schema(
        tags=["Identity"],
        summary="Request a Telegram-delivered login code",
        description="Sends a 6-digit verification code via the user's linked Telegram account. The phone number must already be linked to a Telegram account (via the bot's own contact-sharing flow) -- returns 422 if not linked. Verify with the existing POST /auth/verify-otp.",
        request=RequestOTPSerializer,
        examples=error_examples(),
        responses={202: OpenApiResponse(description="Code sent via Telegram"), **_responses(422, 429)},
    )
    def post(self, request):
        from apps.identity.domain.exceptions import OTPDeliveryFailedError
        from apps.identity.infrastructure.gateways.otp_providers import OTPProviderNonRetryableError

        serializer = RequestOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            with timed("identity.request_telegram_otp"):
                composition.build_request_telegram_otp().execute(
                    phone_number_raw=serializer.validated_data["phone_number"], ip_address=_client_ip(request)
                )
        except OTPDeliveryFailedError as exc:
            # RequestOTP (shared with SMS delivery) deliberately collapses
            # every provider failure into one 503 -- correct for a
            # transient SMS-gateway outage, but "this phone has no linked
            # Telegram account" is a permanent, customer-facing condition
            # that retrying will never fix. Unwrap __cause__ to recover
            # that distinction for this Telegram-specific endpoint only,
            # without changing RequestOTP's own shared, intentional
            # contract.
            if isinstance(exc.__cause__, OTPProviderNonRetryableError):
                raise ValidationFailed(str(exc.__cause__), details={"fields": [{"field": "phone_number", "code": "TELEGRAM_NOT_LINKED"}]}) from exc
            raise
        default_collector.counter("identity_telegram_otp_requested_total")
        return success_response(data={"message": "Verification code sent via Telegram."}, status_code=202)


class TelegramAuthSessionThrottle(ScopedRateLimitThrottle):
    scope = "identity.telegram_auth_session"
    limit = 10
    window_seconds = 3600
    identifier_source = "ip"


class CreateTelegramAuthSessionView(APIView):
    """
    Phase 4: backend for the website's "Continue with Telegram"
    button. Returns only what the frontend needs to open the deep
    link and start polling -- never the token hash, never any
    Telegram identity (none exists yet at this point).
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [TelegramAuthSessionThrottle]

    @extend_schema(
        tags=["Identity"],
        summary="Create a Telegram automatic-login session",
        description="Creates a short-lived (5 minute) PENDING session and returns a Telegram bot deep-link URL. Poll GET /auth/telegram/session/{session_id} for its status.",
        responses={201: OpenApiResponse(description="Session created"), **_responses(429)},
    )
    def post(self, request):
        from django.conf import settings

        from apps.identity.application.services.telegram_auth import CreateTelegramAuthSession

        with timed("identity.create_telegram_auth_session"):
            created = CreateTelegramAuthSession().execute()

        bot_username = getattr(settings, "TELEGRAM_BOT_USERNAME", None)
        telegram_url = f"https://t.me/{bot_username}?start={created.raw_token}" if bot_username else None

        return success_response(
            data={
                "session_id": str(created.session_id),
                "telegram_url": telegram_url,
                "expires_in": created.expires_in,
            },
            status_code=201,
        )


class TelegramAuthSessionStatusThrottle(ScopedRateLimitThrottle):
    scope = "identity.telegram_auth_status"
    limit = 120  # ~2s polling interval over the 5-minute session lifetime, with headroom
    window_seconds = 3600
    identifier_source = "ip"


class GetTelegramAuthSessionStatusView(APIView):
    """
    Phase 4: frontend polling target. Returns only a status string
    while PENDING/EXPIRED/FAILED. Only once the bot-side confirmation
    flow (apps.telegram_bot) has already transitioned the session to
    VERIFIED does this endpoint complete the authentication and
    return real JWT tokens -- via the exact same
    IssueAuthenticationForUser service the existing OTP-based
    /auth/verify-otp endpoint uses, so an authenticated Telegram user
    is indistinguishable from an OTP-authenticated one anywhere else
    in the system.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [TelegramAuthSessionStatusThrottle]

    @extend_schema(
        tags=["Identity"],
        summary="Poll a Telegram automatic-login session",
        description="Returns {status: pending|expired|failed} while waiting, or issues real JWT access/refresh tokens exactly once, the moment the session is VERIFIED (then marks it CONSUMED -- a second call never succeeds again).",
        responses={200: OpenApiResponse(description="Session status or issued tokens"), **_responses(404, 409, 429)},
    )
    def get(self, request, session_id):
        import uuid as _uuid

        from apps.identity.application.services.telegram_auth import (
            CompleteTelegramAuthSession,
            TelegramAuthSessionAlreadyConsumed,
            TelegramAuthSessionExpired,
            TelegramAuthSessionNotReady,
        )
        from apps.identity.infrastructure import models as identity_orm

        try:
            session_uuid = _uuid.UUID(session_id)
        except ValueError:
            return success_response(data={"status": "failed"}, status_code=200)

        try:
            with timed("identity.complete_telegram_auth_session"):
                result = composition.build_complete_telegram_auth_session().execute(session_uuid, _build_device_context(request))
        except TelegramAuthSessionNotReady:
            session = identity_orm.TelegramAuthSession.objects.filter(id=session_uuid).first()
            status_value = session.status if session is not None else "failed"
            return success_response(data={"status": status_value}, status_code=200)
        except TelegramAuthSessionExpired:
            return success_response(data={"status": "expired"}, status_code=200)
        except TelegramAuthSessionAlreadyConsumed:
            return success_response(data={"status": "consumed"}, status_code=200)

        default_collector.counter("identity_telegram_auth_completed_total")
        return success_response(
            data={
                "status": "verified",
                "access_token": result.access_token,
                "refresh_token": result.refresh_token,
                "user_id": str(result.user_id),
            },
            status_code=200,
        )


class VerifyOTPView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [OTPVerifyThrottle, LoginThrottle]

    @extend_schema(
        tags=["Identity"],
        summary="Verify an OTP code and obtain a token pair",
        description="Verifies the code; creates the account on first-ever verification for this phone number (UserRegistered event), or logs an existing account in (UserAuthenticated event). Returns an access/refresh token pair and creates a UserSession.",
        request=VerifyOTPSerializer,
        responses={200: TokenPairResponseSerializer, **_responses(422, 429)},
    )
    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        device_context = _build_device_context(request)
        with timed("identity.verify_otp"):
            result = composition.build_verify_otp().execute(
                phone_number_raw=serializer.validated_data["phone_number"],
                code_raw=serializer.validated_data["code"],
                device_context=device_context,
            )
        default_collector.counter("identity_otp_verified_total")
        response_data = TokenPairResponseSerializer(
            {
                "access_token": result.access_token,
                "refresh_token": result.refresh_token,
                "session_id": result.session_id,
                "is_new_user": result.is_new_user,
            }
        ).data
        return success_response(data=response_data, status_code=200)


class VerifyCodeOnlyView(APIView):
    """
    Real, product-required login path: the website's login page shows
    only a 6-digit code input, no phone number field at all. The code
    was generated by the Telegram bot for a user it already knows;
    execute_by_code_only() finds that same challenge by its
    (deterministic) code_hash alone, with no phone_number filter.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [OTPVerifyThrottle, LoginThrottle]

    @extend_schema(
        tags=["Identity"],
        summary="Verify a 6-digit Telegram bot code and obtain a token pair (no phone number required)",
        description="Verifies a code generated by the Telegram bot's 'Get login code' button. Looks up the challenge by its code_hash alone -- the website never collects a phone number for this flow.",
        request=VerifyCodeOnlySerializer,
        responses={200: TokenPairResponseSerializer, **_responses(422, 429)},
    )
    def post(self, request):
        serializer = VerifyCodeOnlySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        device_context = _build_device_context(request)
        with timed("identity.verify_code_only"):
            result = composition.build_verify_otp().execute_by_code_only(
                code_raw=serializer.validated_data["code"],
                device_context=device_context,
            )
        default_collector.counter("identity_code_only_verified_total")
        response_data = TokenPairResponseSerializer(
            {
                "access_token": result.access_token,
                "refresh_token": result.refresh_token,
                "session_id": result.session_id,
                "is_new_user": result.is_new_user,
            }
        ).data
        return success_response(data=response_data, status_code=200)


class RefreshTokenView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [RefreshThrottle]

    @extend_schema(
        tags=["Identity"],
        summary="Rotate a refresh token for a new access/refresh pair",
        description="Single-use refresh token rotation (Enterprise REST API Blueprint §4). Reuse of an already-rotated token revokes the full session family and is reported as TOKEN_REUSE_DETECTED.",
        request=RefreshTokenSerializer,
        responses={200: TokenPairResponseSerializer, **_responses(401, 429)},
    )
    def post(self, request):
        serializer = RefreshTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with timed("identity.refresh_token"):
            result = composition.build_refresh_token().execute(serializer.validated_data["refresh_token"], ip_address=_client_ip(request))
        response_data = TokenPairResponseSerializer(
            {
                "access_token": result.access_token,
                "refresh_token": result.refresh_token,
                "session_id": result.session_id,
                "is_new_user": False,
            }
        ).data
        return success_response(data=response_data, status_code=200)


class LogoutView(APIView):
    permission_classes = [IsAuthenticatedIdentityUser]

    @extend_schema(
        tags=["Identity"],
        summary="Revoke the current session",
        request=LogoutSerializer,
        examples=auth_examples(),
        responses={204: OpenApiResponse(description="Logged out"), **_responses(401)},
    )
    def post(self, request):
        _attach_identity(request)
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        session_id = _current_session_id(request)
        composition.build_logout().execute(
            user_id=request.identity.id,
            session_id=session_id,
            raw_refresh_token=serializer.validated_data.get("refresh_token") or None,
        )
        return success_response(data=None, status_code=204)


class LogoutAllView(APIView):
    permission_classes = [IsAuthenticatedIdentityUser]

    @extend_schema(
        tags=["Identity"],
        summary="Revoke every active session for the current account",
        responses={204: OpenApiResponse(description="All sessions revoked"), **_responses(401)},
    )
    def post(self, request):
        _attach_identity(request)
        composition.build_logout_all().execute(request.identity.id)
        return success_response(data=None, status_code=204)


def _current_session_id(request) -> uuid.UUID:
    """
    The access token doesn't itself carry a session_id claim (only
    `user_id`) -- the session to revoke on logout is resolved from the
    refresh token supplied in the request body when present; if absent,
    logout still succeeds by only blacklisting nothing and relying on
    the client discarding its tokens (a documented limitation -- see
    the module's Known Limitations in the completion report).
    """
    raw_refresh = request.data.get("refresh_token")
    if not raw_refresh:
        return uuid.uuid4()  # no-op session id -- RevokeSession/session_repo.revoke on a nonexistent id is a safe no-op
    from apps.identity.infrastructure.security import hash_refresh_token

    token_hash = hash_refresh_token(raw_refresh)
    session_repo = composition.DjangoUserSessionRepository()
    session = session_repo.get_by_refresh_token_hash(token_hash)
    return session.id if session else uuid.uuid4()


def _build_device_context(request):
    from apps.identity.application.services.auth import DeviceContext

    return DeviceContext(
        ip_address=_client_ip(request),
        # the storefront's server signs customers in on their behalf and passes the shopper's browser along
        user_agent=(request.META.get("HTTP_X_CLIENT_USER_AGENT") or request.META.get("HTTP_USER_AGENT") or "")[:512] or None,
        device_name=request.data.get("device_name"),
        device_type=DeviceType(request.data.get("device_type", DeviceType.WEB.value)),
    )


# --- Profile -------------------------------------------------------------

class MeView(APIView):
    permission_classes = [IsAuthenticatedIdentityUser]
    throttle_classes = [ProfileUpdateThrottle]

    def get_throttles(self):
        # The 30/hour budget is for profile *changes*. Reading the profile happens on every account/profile
        # page view; throttling it locked customers out of their profile for an hour after normal browsing.
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            from rest_framework.throttling import UserRateThrottle

            return [UserRateThrottle()]  # the global 300/min tier still applies
        return super().get_throttles()

    @extend_schema(
        tags=["Identity"],
        summary="Get the current user's profile",
        responses={200: UserProfileSerializer, **_responses(401)},
    )
    def get(self, request):
        _attach_identity(request)
        user = composition.build_get_own_profile().execute(request.identity.id)
        return success_response(data=UserProfileSerializer(user).data)

    @extend_schema(
        tags=["Identity"],
        summary="Update the current user's profile",
        description="Partial update -- every field optional (PATCH semantics). Business validation (username uniqueness) surfaces as 409, not 422.",
        request=UpdateProfileSerializer,
        responses={200: UserProfileSerializer, **_responses(401, 409, 422)},
    )
    def patch(self, request):
        _attach_identity(request)
        serializer = UpdateProfileSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = composition.build_update_profile().execute(user_id=request.identity.id, **serializer.validated_data)
        return success_response(data=UserProfileSerializer(user).data)


class WsTicketThrottle(ScopedRateLimitThrottle):
    scope = "identity.ws_ticket"
    limit = 60
    window_seconds = 3600
    identifier_source = "user"


class WsTicketView(APIView):
    """
    Mints a short-lived (60s) WebSocket auth ticket for the
    already-authenticated caller -- see `issue_ws_ticket`'s own
    docstring for why this exists instead of exposing the real access
    token to client JS. Never returns the real access/refresh token.
    """

    permission_classes = [IsAuthenticatedIdentityUser]
    throttle_classes = [WsTicketThrottle]

    @extend_schema(tags=["Identity"], summary="Issue a short-lived WebSocket auth ticket", responses={200: OpenApiResponse(description="Ticket issued"), **_responses(401)})
    def post(self, request):
        from apps.identity.infrastructure.security import issue_ws_ticket

        _attach_identity(request)
        ticket = issue_ws_ticket(request.identity.id)
        return success_response(data={"ticket": ticket, "expires_in": 60})


class AvatarUploadView(APIView):
    permission_classes = [IsAuthenticatedIdentityUser]
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [ProfileUpdateThrottle]

    @extend_schema(
        tags=["Identity"],
        summary="Upload a profile avatar",
        description="Runs the upload through the Media Pipeline (validate -> virus scan -> optimize -> WebP -> thumbnails -> store). Rejects unsupported MIME types or oversized files with 422.",
        request={"multipart/form-data": AvatarUploadSerializer},
        responses={201: OpenApiResponse(description="Avatar processed and set"), **_responses(401, 422)},
    )
    def post(self, request):
        _attach_identity(request)
        uploaded_file = request.FILES.get("avatar")
        if uploaded_file is None:
            raise ValidationFailed("No file was uploaded under the 'avatar' field.", details={"fields": [{"field": "avatar", "code": "REQUIRED"}]})

        content = uploaded_file.read()
        user, processed = composition.build_upload_avatar().execute(
            user_id=request.identity.id, filename=uploaded_file.name, content=content, mime_type=uploaded_file.content_type
        )
        return success_response(
            data={
                "profile": UserProfileSerializer(user).data,
                "media": {
                    "storage_path": processed.storage_path,
                    "has_webp_variant": processed.has_webp_variant,
                    "thumbnail_sizes": list(processed.thumbnail_paths.keys()),
                },
            },
            status_code=201,
        )


# --- Sessions --------------------------------------------------------------

class SessionsListView(APIView):
    permission_classes = [IsAuthenticatedIdentityUser]

    @extend_schema(
        tags=["Identity"],
        summary="List active sessions/devices for the current user",
        responses={200: UserSessionSerializer(many=True), **_responses(401)},
    )
    def get(self, request):
        _attach_identity(request)
        sessions = composition.build_list_own_sessions().execute(request.identity.id)
        import dataclasses

        data = [UserSessionSerializer(dataclasses.asdict(s) | {"is_active": s.is_active}).data for s in sessions]
        return paginated_response(data=data, pagination={"strategy": "page", "page": 1, "page_size": len(data), "total_pages": 1, "total_count": len(data)})


class SessionRevokeView(APIView):
    permission_classes = [IsAuthenticatedIdentityUser]

    @extend_schema(
        tags=["Identity"],
        summary="Revoke a specific session",
        description="A user may revoke only their own sessions unless granted `identity.session.revoke_any`.",
        responses={204: OpenApiResponse(description="Session revoked"), **_responses(401, 403, 404)},
    )
    def delete(self, request, session_id: str):
        _attach_identity(request)
        composition.build_revoke_session().execute(requesting_user_id=request.identity.id, target_session_id=uuid.UUID(session_id))
        return success_response(data=None, status_code=204)


# --- Admin --------------------------------------------------------------

class AdminUserListView(APIView):
    required_permission_code = "identity.user.view"
    throttle_classes = [AdminOperationThrottle]

    def get_permissions(self):
        from common.permissions import HasPermissionCode

        return [HasPermissionCode()]

    @extend_schema(
        tags=["Identity Admin"],
        summary="List/search users (staff)",
        description="Requires `identity.user.view`. Supports filter[status], filter[language], q (search), sort, page, page_size per Enterprise REST API Blueprint §9/§10.",
        responses={200: AdminUserListItemSerializer(many=True), **_responses(401, 403, 422)},
    )
    def get(self, request):
        _attach_identity(request)
        params = parse_admin_user_list_params(request.query_params)
        users, total = composition.build_admin_list_users().execute(
            status=params.status, query=params.query, page=params.page, page_size=params.page_size
        )
        data = AdminUserListItemSerializer(users, many=True).data
        total_pages = max((total + params.page_size - 1) // params.page_size, 1)
        return paginated_response(
            data=data,
            pagination={"strategy": "page", "page": params.page, "page_size": params.page_size, "total_pages": total_pages, "total_count": total},
        )


class AdminUserDetailView(APIView):
    required_permission_code = "identity.user.view"
    throttle_classes = [AdminOperationThrottle]

    def get_permissions(self):
        from common.permissions import HasPermissionCode

        return [HasPermissionCode()]

    @extend_schema(
        tags=["Identity Admin"],
        summary="Get a user's detail (staff)",
        description="Requires `identity.user.view`.",
        responses={200: AdminUserDetailSerializer, **_responses(401, 403, 404)},
    )
    def get(self, request, user_id: str):
        _attach_identity(request)
        user = composition.build_admin_get_user().execute(uuid.UUID(user_id))
        return success_response(data=AdminUserDetailSerializer(user).data)


class UserStatisticsView(APIView):
    """Wires the new UserStatisticsSelector -- Identity had no statistics selector or endpoint at all, closing the "customer statistics" dashboard gap using only existing, unambiguous UserStatus values."""

    required_permission_code = "identity.user.view"
    throttle_classes = [AdminOperationThrottle]

    def get_permissions(self):
        from common.permissions import HasPermissionCode

        return [HasPermissionCode()]

    @extend_schema(tags=["Identity Admin"], summary="Customer/user statistics (staff)", description="Requires `identity.user.view`.")
    def get(self, request):
        _attach_identity(request)
        from apps.identity.infrastructure.selectors import UserStatisticsSelector

        selector = UserStatisticsSelector()
        counts = selector.counts_by_status()
        return success_response(data={
            "total_customers": selector.total_customers(),
            "active_customers": counts.get("active", 0),
            "counts_by_status": counts,
        })


class AdminUpdateUserStatusView(APIView):
    required_permission_code = "identity.user.suspend"
    throttle_classes = [AdminOperationThrottle]

    def get_permissions(self):
        from common.permissions import HasPermissionCode

        return [HasPermissionCode()]

    @extend_schema(
        tags=["Identity Admin"],
        summary="Block or activate a user (staff)",
        description="Requires `identity.user.suspend`. Blocking a user raises UserBlocked; the account cannot authenticate while blocked.",
        request=AdminUpdateUserStatusSerializer,
        responses={200: AdminUserDetailSerializer, **_responses(401, 403, 404, 422)},
    )
    def patch(self, request, user_id: str):
        _attach_identity(request)
        serializer = AdminUpdateUserStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = composition.build_admin_update_user_status().execute(
            actor_user_id=request.identity.id,
            target_user_id=uuid.UUID(user_id),
            new_status=serializer.validated_data["status"],
            reason=serializer.validated_data.get("reason"),
        )
        return success_response(data=AdminUserDetailSerializer(user).data)


class AdminUpdateUserRolesView(APIView):
    required_permission_code = "identity.role.manage"
    throttle_classes = [AdminOperationThrottle]

    def get_permissions(self):
        from common.permissions import HasPermissionCode

        return [HasPermissionCode()]

    @extend_schema(
        tags=["Identity Admin"],
        summary="Assign a role to a user (staff)",
        description="Requires `identity.role.manage`. `store_id` is optional -- omit for a platform-wide role grant, supply for a store-scoped grant (Domain Architecture Specification §2.1).",
        responses={201: OpenApiResponse(description="Role assigned"), **_responses(401, 403, 404, 409, 422)},
    )
    def patch(self, request, user_id: str):
        _attach_identity(request)
        role_code = request.data.get("role_code")
        store_id = request.data.get("store_id")
        if not role_code:
            raise ValidationFailed("role_code is required.", details={"fields": [{"field": "role_code", "code": "REQUIRED"}]})

        assignment = composition.build_assign_role().execute(
            user_id=uuid.UUID(user_id), role_code=role_code, store_id=uuid.UUID(store_id) if store_id else None
        )
        return success_response(data={"user_id": str(assignment.user_id), "role_id": str(assignment.role_id), "store_id": str(assignment.store_id) if assignment.store_id else None}, status_code=201)
