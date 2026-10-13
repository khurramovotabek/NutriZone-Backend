"""
Phase 4 Telegram automatic login application services.

Two services, matching the real session lifecycle:

CreateTelegramAuthSession -- called when the user clicks
"Continue with Telegram" on the website. Creates a PENDING
TelegramAuthSession with a cryptographically random, single-use
token (never persisted in recoverable form -- only its hash).

CompleteTelegramAuthSession -- called by the status-polling endpoint
once the bot has already marked the session VERIFIED (via a separate,
bot-side confirmation flow in apps.telegram_bot). Issues real JWT via
IssueAuthenticationForUser (the exact same shared service VerifyOTP
uses) and marks the session CONSUMED -- single-use, matching this
project's own established OTPCodeChallenge convention.

Deliberately does NOT implement Telegram identity verification itself
-- that happens bot-side (apps.telegram_bot), which is the only
component that ever receives a genuine, Telegram-authenticated
update. This service only completes authentication for a session the
bot has already verified.
"""
from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone as django_timezone

from apps.identity.application.services.auth import AuthResult, DeviceContext, IssueAuthenticationForUser
from apps.identity.domain.enums import AuthProviderType
from common.exceptions import ConflictError, ResourceNotFound

SESSION_TTL_SECONDS = 300  # 5 minutes, matching this phase's own recommended default


class TelegramAuthSessionNotReady(ConflictError):
    """Raised when the status endpoint is asked to complete a session that isn't VERIFIED yet (still PENDING) -- the caller should keep polling, not treat this as an error."""

    code = "TELEGRAM_AUTH_NOT_READY"


class TelegramAuthSessionExpired(ConflictError):
    code = "TELEGRAM_AUTH_EXPIRED"


class TelegramAuthSessionAlreadyConsumed(ConflictError):
    """A real, tested defense against replay: the same session must never issue a second JWT."""

    code = "TELEGRAM_AUTH_ALREADY_CONSUMED"


@dataclass(frozen=True, slots=True)
class CreatedTelegramAuthSession:
    session_id: uuid.UUID
    raw_token: str
    expires_at: object
    expires_in: int


class CreateTelegramAuthSession:
    def execute(self) -> CreatedTelegramAuthSession:
        from apps.identity.infrastructure import models as identity_orm
        from apps.identity.infrastructure.security import hash_refresh_token

        raw_token = secrets.token_urlsafe(32)
        token_hash = hash_refresh_token(raw_token)
        expires_at = django_timezone.now() + timedelta(seconds=SESSION_TTL_SECONDS)

        session = identity_orm.TelegramAuthSession.objects.create(
            id=uuid.uuid4(), token_hash=token_hash, status=identity_orm.TelegramAuthSessionStatus.PENDING, expires_at=expires_at,
        )

        return CreatedTelegramAuthSession(session_id=session.id, raw_token=raw_token, expires_at=expires_at, expires_in=SESSION_TTL_SECONDS)


class CreateBotInitiatedAuthSession:
    """
    Phase 5 (bot menu "auto-login" button): unlike
    CreateTelegramAuthSession (called from the website, starts PENDING,
    needs a separate bot-side confirmation), this is called FROM the
    bot itself, for a customer whose Telegram identity the webhook has
    already, genuinely authenticated (from_user["id"], never
    client-supplied). No separate confirmation step is needed or
    possible -- the user pressing this button inside their own
    Telegram chat already IS the confirmation. The session is created
    directly in VERIFIED status, ready for the website to complete via
    the exact same CompleteTelegramAuthSession/polling endpoint the
    website-initiated flow already uses.
    """

    def execute(self, customer_id: uuid.UUID, telegram_user_id: int) -> "CreatedTelegramAuthSession":
        from apps.identity.infrastructure import models as identity_orm
        from apps.identity.infrastructure.security import hash_refresh_token

        raw_token = secrets.token_urlsafe(32)
        token_hash = hash_refresh_token(raw_token)
        expires_at = django_timezone.now() + timedelta(seconds=SESSION_TTL_SECONDS)

        session = identity_orm.TelegramAuthSession.objects.create(
            id=uuid.uuid4(), token_hash=token_hash, status=identity_orm.TelegramAuthSessionStatus.VERIFIED,
            telegram_user_id=telegram_user_id, user_id=customer_id, expires_at=expires_at, verified_at=django_timezone.now(),
        )

        return CreatedTelegramAuthSession(session_id=session.id, raw_token=raw_token, expires_at=expires_at, expires_in=SESSION_TTL_SECONDS)


class CompleteTelegramAuthSession:
    """
    Called by the status-polling endpoint. Only issues JWT if the
    bot-side confirmation flow has already transitioned the session
    to VERIFIED with a real, linked user_id attached -- this service
    performs no Telegram identity verification of its own.
    """

    def __init__(self, issue_authentication: IssueAuthenticationForUser) -> None:
        self._issue_authentication = issue_authentication

    def execute(self, session_id: uuid.UUID, device_context: DeviceContext) -> AuthResult:
        from apps.identity.infrastructure import models as identity_orm
        from apps.identity.infrastructure.repositories import _user_to_domain

        # Two separate atomic blocks, deliberately: raising an exception
        # from *inside* a `with transaction.atomic():` block rolls back
        # every write made inside that same block, regardless of the
        # write's position relative to the raise -- a real bug caught by
        # testing here. The expiration-check-and-mark block below must
        # exit cleanly (no exception) so its own write is durable; only
        # once it has already committed do we inspect its result and
        # raise, outside of any atomic context.
        with transaction.atomic():
            session = identity_orm.TelegramAuthSession.objects.select_for_update().filter(id=session_id).first()
            if session is None:
                raise ResourceNotFound("Telegram authentication session not found.")

            if session.status == identity_orm.TelegramAuthSessionStatus.CONSUMED:
                raise TelegramAuthSessionAlreadyConsumed("This Telegram login session has already been used.")

            is_expired = session.expires_at <= django_timezone.now()
            if is_expired and session.status != identity_orm.TelegramAuthSessionStatus.EXPIRED:
                session.status = identity_orm.TelegramAuthSessionStatus.EXPIRED
                session.save(update_fields=["status"])

        if is_expired:
            raise TelegramAuthSessionExpired("This Telegram login session has expired.")

        with transaction.atomic():
            session = identity_orm.TelegramAuthSession.objects.select_for_update().filter(id=session_id).first()

            if session.status != identity_orm.TelegramAuthSessionStatus.VERIFIED or session.user_id is None:
                raise TelegramAuthSessionNotReady("This Telegram login session has not been confirmed yet.")

            user_row = identity_orm.User.objects.filter(id=session.user_id).first()
            if user_row is None:
                raise ResourceNotFound("The linked NutriZone account could not be found.")
            user = _user_to_domain(user_row)

            result = self._issue_authentication.execute(user, device_context, provider_type=AuthProviderType.TELEGRAM.value, is_new_user=False)

            session.status = identity_orm.TelegramAuthSessionStatus.CONSUMED
            session.consumed_at = django_timezone.now()
            session.save(update_fields=["status", "consumed_at"])

        return result
