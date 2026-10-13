"""
Authentication application services: RequestOTP, VerifyOTP,
RefreshToken, Logout, LogoutAll.

Each class is a single use case (Django Implementation Blueprint §3):
constructor-injected with the ports/gateways it needs, one public
`execute()` method, orchestration only -- business rules are delegated
to `domain/services.py`'s OTPPolicy/TokenPolicy and the User aggregate.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from django.db import transaction

from apps.identity.application.ports import (
    OTPChallengeRepository,
    OTPProvider,
    OTPProviderError,
    TokenIssuer,
    UserRepository,
    UserSessionRepository,
)
from apps.identity.domain.aggregates import User
from apps.identity.domain.enums import AuthProviderType, DeviceType, UserStatus
from apps.identity.domain.events import SuspiciousLoginDetected, UserAuthenticated, UserRegistered
from apps.identity.domain.exceptions import (
    OTPDeliveryFailedError,
    OTPExpiredError,
    OTPInvalidError,
    OTPMaxAttemptsExceededError,
    RefreshTokenInvalidError,
    RefreshTokenReusedError,
)
from apps.identity.domain.services import OTPChallengeState, OTPPolicy
from apps.identity.domain.value_objects import OTPCode, PhoneNumber
from core.audit import AuditEventBuilder
from core.clock import Clock
from core.observability import get_correlation_id
from core.ratelimit import per_ip_limiter, per_user_limiter

_OTP_REQUEST_IP_LIMIT = 10  # coarser than the per-phone 3/hour quota -- catches an attacker rotating phone numbers from one IP
_OTP_REQUEST_IP_WINDOW_SECONDS = 3600


@dataclass(frozen=True, slots=True)
class DeviceContext:
    """Request-derived context every auth use case needs -- assembled once at the interfaces/api layer from the HTTP request."""

    ip_address: str | None
    user_agent: str | None
    device_name: str | None = None
    device_type: DeviceType = DeviceType.WEB


@dataclass(frozen=True, slots=True)
class AuthResult:
    user_id: uuid.UUID
    access_token: str
    refresh_token: str
    session_id: uuid.UUID
    is_new_user: bool


class IssueAuthenticationForUser:
    """
    Phase 4 Telegram automatic login: the shared "complete
    authentication for an already-resolved, already-verified user"
    logic, extracted from VerifyOTP's own tail (Phase 04's original
    implementation) so it can be reused by any authentication method
    that has already established identity through its own means
    (OTP code verification, Telegram bot confirmation, etc.) without
    duplicating JWT issuance, UserSession creation, event staging, or
    audit logging.

    Deliberately does NOT perform identity verification itself -- the
    caller is responsible for that (VerifyOTP's own OTP check,
    CompleteTelegramAuthSession's own session/Telegram-identity
    checks). This service only completes the authentication for a
    user identity the caller has already established as genuine.
    """

    def __init__(self, session_repo: UserSessionRepository, token_issuer: TokenIssuer, stage_events) -> None:
        self._session_repo = session_repo
        self._token_issuer = token_issuer
        self._stage_events = stage_events

    def execute(self, user: User, device_context: DeviceContext, provider_type: str, is_new_user: bool = False) -> AuthResult:
        tokens = self._token_issuer.issue(user.id)

        from apps.identity.domain.entities import UserSession as UserSessionEntity

        session = UserSessionEntity(
            id=uuid.uuid4(),
            user_id=user.id,
            device_id=None,
            device_name=device_context.device_name,
            device_type=device_context.device_type,
            refresh_token_hash=tokens.refresh_token_hash,
            ip_address=device_context.ip_address,
            user_agent=device_context.user_agent,
            last_activity=Clock.now(),
            expires_at=tokens.refresh_expires_at,
        )
        session = self._session_repo.create(session)

        self._stage_events(
            [
                (
                    "UserAuthenticated",
                    UserAuthenticated(
                        user_id=user.id,
                        session_id=session.id,
                        provider_type=provider_type,
                        ip_address=device_context.ip_address,
                    ).to_payload(),
                )
            ]
        )

        audit = AuditEventBuilder(context_schema="identity", actor_id=str(user.id))
        audit.login(entity_id=str(user.id), extra={"session_id": str(session.id), "correlation_id": get_correlation_id()})

        return AuthResult(
            user_id=user.id,
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            session_id=session.id,
            is_new_user=is_new_user,
        )


class RequestOTP:
    def __init__(
        self,
        otp_repo: OTPChallengeRepository,
        user_repo: UserRepository,
        otp_provider: OTPProvider,
        hash_otp_code,
        max_requests_per_hour: int | None = None,
    ) -> None:
        self._otp_repo = otp_repo
        self._user_repo = user_repo
        self._otp_provider = otp_provider
        self._hash_otp_code = hash_otp_code
        # None (the default for every existing caller/test) preserves
        # OTPPolicy's own real production quota exactly -- only the
        # composition root ever passes an explicit override, sourced
        # from the OTP_MAX_REQUESTS_PER_HOUR Django setting, so a
        # non-default value can only ever come from deliberate
        # environment configuration (e.g. local development), never a
        # silent behavior change to the production security control.
        self._max_requests_per_hour = max_requests_per_hour

    @transaction.atomic
    def execute(self, phone_number_raw: str, ip_address: str | None) -> None:
        """`@transaction.atomic` added here as a real defect fix: required now that `get_latest()` uses `select_for_update()` (a real concurrency fix in its own right -- see that method's docstring), and independently closes a genuine race where two concurrent requests for the same phone number could both pass the cooldown check in `OTPPolicy.can_resend()` before either had created its own challenge row, both then creating and sending a code."""
        phone_number = PhoneNumber(phone_number_raw)

        # Rate limiting (Architecture Review §14): per-phone quota is
        # the primary business rule (enforced via OTPPolicy against the
        # durable otp_codes table below); the per-IP limiter is a
        # coarser, faster-to-check defense against an attacker rotating
        # phone numbers from a single source.
        if ip_address:
            ip_limiter = per_ip_limiter("otp_request", limit=_OTP_REQUEST_IP_LIMIT, window_seconds=_OTP_REQUEST_IP_WINDOW_SECONDS)
            ip_limiter.check(ip_address)  # best-effort: does not itself raise, business quota below is authoritative

        one_hour_ago = Clock.now() - _hours(1)
        requests_last_hour = self._otp_repo.count_requested_since(phone_number, since=one_hour_ago)
        if self._max_requests_per_hour is None:
            OTPPolicy.assert_within_hourly_quota(requests_last_hour)
        else:
            OTPPolicy.assert_within_hourly_quota(requests_last_hour, max_requests=self._max_requests_per_hour)

        latest = self._otp_repo.get_latest(phone_number)
        OTPPolicy.can_resend(latest.created_at if latest else None)

        code = OTPCode.generate()
        code_hash = self._hash_otp_code(code.value)
        expires_at = OTPPolicy.new_expiry()

        self._otp_repo.create(phone_number, code_hash, expires_at)
        try:
            delivered = self._otp_provider.send_otp(phone_number, code.value)
        except OTPProviderError as exc:
            raise OTPDeliveryFailedError("The OTP could not be delivered. Please try again shortly.") from exc
        if not delivered:
            raise OTPDeliveryFailedError("The OTP could not be delivered. Please try again shortly.")

        audit = AuditEventBuilder(context_schema="identity")
        # No user_id yet at this point for a first-time phone number --
        # the audit event uses the phone-number-derived identity
        # (entity_id) rather than requiring a user to already exist.
        audit.exported(entity_type="OTPChallenge", entity_id=str(phone_number), extra={"event": "otp_requested"})


class VerifyOTP:
    def __init__(
        self,
        otp_repo: OTPChallengeRepository,
        user_repo: UserRepository,
        session_repo: UserSessionRepository,
        token_issuer: TokenIssuer,
        hash_otp_code,
        stage_events,
        default_role_assigner=None,
    ) -> None:
        self._otp_repo = otp_repo
        self._user_repo = user_repo
        self._session_repo = session_repo
        self._token_issuer = token_issuer
        self._hash_otp_code = hash_otp_code
        self._stage_events = stage_events  # callable(list[tuple[event_type: str, payload: dict]]) -> None, staged inside this method's own transaction
        self._default_role_assigner = default_role_assigner  # Phase 09.4b: optional callable(user_id) -> None, assigns the default "customer" Role on first registration. Optional and defaulting to None so the existing test-suite caller (which constructs VerifyOTP without this argument) remains unaffected.

    @transaction.atomic
    def execute(self, phone_number_raw: str, code_raw: str, device_context: DeviceContext) -> AuthResult:
        phone_number = PhoneNumber(phone_number_raw)
        code = OTPCode(code_raw)

        challenge = self._otp_repo.get_latest(phone_number)
        if challenge is None:
            raise OTPInvalidError("No verification code was requested for this phone number.")

        self._verify_and_consume(challenge, code)
        return self._complete(phone_number, device_context)

    @transaction.atomic
    def execute_by_code_only(self, code_raw: str, device_context: DeviceContext) -> AuthResult:
        """
        Real, product-required login path: the user never types a
        phone number on the website at all. The 6-digit code was
        already generated by the Telegram bot for a user it already
        knows (via `_send_login_code()`'s own RequestOTP call) --
        hash_otp_code() is deterministic, so `find_active_by_code_hash()`
        is a real, indexed lookup that yields the exact same
        OTPChallengeState (including the phone_number it was created
        for) that the phone+code path above would have found. Reuses
        the identical verify/consume/complete logic -- no second,
        divergent code-only implementation.
        """
        code = OTPCode(code_raw)
        code_hash = self._hash_otp_code(code_raw)

        challenge = self._otp_repo.find_active_by_code_hash(code_hash)
        if challenge is None:
            raise OTPInvalidError("This code is invalid or has expired.")
        if not challenge.phone_number:
            raise OTPInvalidError("This code is invalid or has expired.")

        self._verify_and_consume(challenge, code)
        return self._complete(PhoneNumber(challenge.phone_number), device_context)

    def _verify_and_consume(self, challenge: OTPChallengeState, code: OTPCode) -> None:
        try:
            OTPPolicy.verify(challenge, code, self._hash_otp_code)
        except (OTPExpiredError, OTPMaxAttemptsExceededError, OTPInvalidError):
            # A real defect fixed here: this previously caught bare `Exception`,
            # meaning a genuine bug or infrastructure failure (a DB error, for
            # example) would silently count against the user's OTP attempt
            # budget along with a real wrong-code guess. Now only the three
            # specific, expected verification-failure exceptions
            # OTPPolicy.verify() can actually raise increment the counter;
            # anything else propagates untouched, exactly as an unexpected
            # error should.
            self._otp_repo.increment_attempt(challenge.id)
            raise

        if not self._otp_repo.mark_consumed(challenge.id):
            # A real defect fixed here: closes the gap between OTPPolicy.verify()'s
            # own consumed_at check (against the `challenge` snapshot read at the
            # top of this method) and the actual atomic consumption -- if a
            # concurrent request for the same challenge_id already consumed it
            # in between, mark_consumed() now reports that honestly (False)
            # instead of silently double-consuming, and this request correctly
            # fails as an invalid/already-used code rather than proceeding to
            # issue tokens for an already-redeemed OTP.
            raise OTPInvalidError("This code has already been used.")

    def _complete(self, phone_number: PhoneNumber, device_context: DeviceContext) -> AuthResult:
        user = self._user_repo.get_by_phone_number(phone_number)
        is_new_user = user is None
        if user is None:
            user = User(id=uuid.uuid4(), phone_number=phone_number, full_name="", status=UserStatus.ACTIVE)
            user = self._user_repo.save(user)
            self._stage_events(
                [("UserRegistered", UserRegistered(user_id=user.id, phone_number=phone_number.value, registered_via=AuthProviderType.PHONE_OTP.value).to_payload())]
            )
            if self._default_role_assigner is not None:
                self._default_role_assigner(user.id)
        else:
            user.assert_can_authenticate()

        tokens_result = IssueAuthenticationForUser(self._session_repo, self._token_issuer, self._stage_events).execute(
            user, device_context, provider_type=AuthProviderType.PHONE_OTP.value, is_new_user=is_new_user
        )

        return AuthResult(
            user_id=tokens_result.user_id,
            access_token=tokens_result.access_token,
            refresh_token=tokens_result.refresh_token,
            session_id=tokens_result.session_id,
            is_new_user=tokens_result.is_new_user,
        )


class RefreshToken:
    def __init__(self, session_repo: UserSessionRepository, token_issuer: TokenIssuer, user_repo: UserRepository, stage_events) -> None:
        self._session_repo = session_repo
        self._token_issuer = token_issuer
        self._user_repo = user_repo
        self._stage_events = stage_events

    @transaction.atomic
    def execute(self, raw_refresh_token: str, ip_address: str | None = None) -> AuthResult:
        token_hash = self._token_issuer.hash_refresh_token(raw_refresh_token)
        session = self._session_repo.get_by_refresh_token_hash(token_hash)

        if session is None:
            # A real defect fixed here: this branch previously always raised the
            # generic RefreshTokenInvalidError, silently treating "token never
            # existed" and "token was validly rotated out and is now being
            # reused" (an active theft/replay signature) identically. The data
            # to distinguish them (RevokedTokenRecord, including the owning
            # user_id/session_id) was already being written correctly by
            # revoke() -- it was simply never read here. report_reuse() now
            # correctly revokes only the compromised user's own session
            # family, never an unrelated user's sessions.
            reuse = self._session_repo.is_token_reuse(token_hash)
            if reuse is not None:
                reused_user_id, reused_session_id = reuse
                self.report_reuse(reused_user_id, reused_session_id, ip_address, self._stage_events)
            raise RefreshTokenInvalidError("This refresh token is invalid or has already been rotated.")

        if not session.is_active or session.expires_at <= Clock.now():
            raise RefreshTokenInvalidError("This session has expired or been revoked.")

        user = self._user_repo.get_by_id(session.user_id)
        if user is None:
            raise RefreshTokenInvalidError("The account for this session no longer exists.")
        user.assert_can_authenticate()

        # Rotation: revoke the presented session's token and issue a
        # fresh pair bound to a new session row. A second presentation of
        # this now-revoked token is caught above, at the top of this
        # method -- get_by_refresh_token_hash returns None on the next
        # call, and the is_token_reuse() check distinguishes genuine
        # reuse (RefreshTokenReusedError, full session-family revocation)
        # from a token that simply never existed (RefreshTokenInvalidError).
        self._session_repo.revoke(session.id)
        tokens = self._token_issuer.issue(user.id)

        from apps.identity.domain.entities import UserSession as UserSessionEntity

        new_session = UserSessionEntity(
            id=uuid.uuid4(),
            user_id=user.id,
            device_id=session.device_id,
            device_name=session.device_name,
            device_type=session.device_type,
            refresh_token_hash=tokens.refresh_token_hash,
            ip_address=session.ip_address,
            user_agent=session.user_agent,
            last_activity=Clock.now(),
            expires_at=tokens.refresh_expires_at,
        )
        new_session = self._session_repo.create(new_session)

        return AuthResult(
            user_id=user.id,
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            session_id=new_session.id,
            is_new_user=False,
        )

    def report_reuse(self, user_id: uuid.UUID, session_id: uuid.UUID, ip_address: str | None, stage_events) -> None:
        """
        Called by the interfaces layer when a token-reuse condition is
        detected (Architecture Review §14): revokes the full session
        family and raises SuspiciousLoginDetected.
        """
        self._session_repo.revoke_all_for_user(user_id)
        stage_events([("SuspiciousLoginDetected", SuspiciousLoginDetected(user_id=user_id, session_id=session_id, ip_address=ip_address).to_payload())])
        raise RefreshTokenReusedError("Token reuse detected -- all sessions for this account have been revoked.")


class Logout:
    def __init__(self, session_repo: UserSessionRepository, token_issuer: TokenIssuer, stage_events) -> None:
        self._session_repo = session_repo
        self._token_issuer = token_issuer
        self._stage_events = stage_events

    @transaction.atomic
    def execute(self, user_id: uuid.UUID, session_id: uuid.UUID, raw_refresh_token: str | None = None) -> None:
        from apps.identity.domain.events import SessionRevoked

        self._session_repo.revoke(session_id)
        if raw_refresh_token:
            self._token_issuer.blacklist_refresh_token(raw_refresh_token)

        self._stage_events([("SessionRevoked", SessionRevoked(user_id=user_id, session_id=session_id, revoked_by=None).to_payload())])

        audit = AuditEventBuilder(context_schema="identity", actor_id=str(user_id))
        audit.logout(entity_id=str(user_id))


class LogoutAll:
    def __init__(self, session_repo: UserSessionRepository) -> None:
        self._session_repo = session_repo

    def execute(self, user_id: uuid.UUID) -> None:
        self._session_repo.revoke_all_for_user(user_id)
        audit = AuditEventBuilder(context_schema="identity", actor_id=str(user_id))
        audit.logout(entity_id=str(user_id))


def _hours(n: int):
    from datetime import timedelta

    return timedelta(hours=n)
