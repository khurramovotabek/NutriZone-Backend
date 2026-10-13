"""
Identity domain services.

Pure business rules with no I/O -- per MIC §4, a domain service never
touches the database, Celery, or any external system; it is handed
data by the calling Application Service and returns a decision. The
actual OTP storage/rate-limit-counter persistence lives in
`application/services/RequestOTP` via the `OTPChallengeRepository` port.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from apps.identity.domain.exceptions import (
    OTPExpiredError,
    OTPInvalidError,
    OTPMaxAttemptsExceededError,
    OTPResendTooSoonError,
)
from apps.identity.domain.value_objects import OTPCode
from core.clock import Clock

# Policy constants -- named here, in the domain layer, per Django
# Implementation Blueprint §6 ("business-meaningful constants live in
# domain/ or application/, never a bare literal"). Matches Architecture
# Review §14's OTP hardening requirement.
#
# Real, explicit product requirement: a login code (SMS or the
# Telegram-delivered "Sayt uchun kod olish" code alike -- both flow
# through this exact same OTPPolicy) is valid for 2 minutes, matching
# the reference login experience this authentication flow was
# rebuilt against ("Kod 2 daqiqada amal qiladi"). Every surface that
# communicates this duration reads it from here (the bot's own
# `login_code_sent` message via `TelegramOTPProvider`, and the
# website's `LoginCodeForm` countdown via `NEXT_PUBLIC_OTP_VALIDITY_SECONDS`)
# so all three can never drift out of sync with each other again.
OTP_EXPIRY_SECONDS = 120  # 2 minutes
OTP_MAX_VERIFY_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_MAX_REQUESTS_PER_HOUR = 3


@dataclass(frozen=True, slots=True)
class OTPChallengeState:
    """
    The persisted state an OTPPolicy decision is made against --
    handed in by the calling Application Service (read from
    `OTPChallengeRepository`), never fetched by the domain service
    itself.

    **`id` is a real defect fix, not part of the original design**:
    without it, every repository mutation (`increment_attempt`,
    `mark_consumed`) had no choice but to re-derive "the latest
    challenge for this phone number" independently and later than the
    original read -- a genuine race if a second OTP is requested for
    the same number between a verification attempt's read and its
    mutation. Carrying the specific challenge's own identity lets
    every mutation target that exact row.
    """

    id: uuid.UUID
    code_hash: str
    expires_at: datetime
    attempt_count: int
    consumed_at: datetime | None
    created_at: datetime
    phone_number: str | None = None


class OTPPolicy:
    """Stateless -- every method takes the state it needs as arguments."""

    @staticmethod
    def new_expiry() -> datetime:
        return Clock.now() + timedelta(seconds=OTP_EXPIRY_SECONDS)

    @staticmethod
    def can_resend(last_requested_at: datetime | None) -> None:
        """Raises OTPResendTooSoonError if the cooldown hasn't elapsed. Returns None (no exception) if resend is allowed."""
        if last_requested_at is None:
            return
        elapsed = (Clock.now() - last_requested_at).total_seconds()
        if elapsed < OTP_RESEND_COOLDOWN_SECONDS:
            raise OTPResendTooSoonError(
                f"Please wait {int(OTP_RESEND_COOLDOWN_SECONDS - elapsed)}s before requesting another code.",
                details={"retry_after_seconds": int(OTP_RESEND_COOLDOWN_SECONDS - elapsed)},
            )

    @staticmethod
    def assert_within_hourly_quota(requests_in_last_hour: int, max_requests: int = OTP_MAX_REQUESTS_PER_HOUR) -> None:
        """
        `max_requests` defaults to the real production quota (3) --
        overridable per call so the composition root can inject a
        higher, environment-specific limit (e.g. for local development)
        without this domain rule itself ever depending on Django
        settings (MIC §4: the domain layer never touches configuration/
        I/O directly). Production callers that pass nothing get the
        exact same, unchanged security behavior as before.
        """
        if requests_in_last_hour >= max_requests:
            raise OTPMaxAttemptsExceededError(
                f"Too many OTP requests. Maximum {max_requests} per hour."
            )

    @staticmethod
    def verify(challenge: OTPChallengeState, submitted_code: OTPCode, hasher) -> None:
        """
        Raises the specific failure reason (expired / max-attempts /
        invalid-code) so the API layer can return a precise error code
        per Enterprise REST API Blueprint §13.1's business error list.
        `hasher` is a callable `(code: str) -> str` -- injected rather
        than imported directly so this stays a pure function of its
        arguments, testable without any hashing library assumption
        baked into the domain layer.
        """
        if challenge.consumed_at is not None:
            raise OTPInvalidError("This code has already been used.")
        if Clock.now() >= challenge.expires_at:
            raise OTPExpiredError("This code has expired. Please request a new one.")
        if challenge.attempt_count >= OTP_MAX_VERIFY_ATTEMPTS:
            raise OTPMaxAttemptsExceededError("Too many incorrect attempts. Please request a new code.")
        if hasher(submitted_code.value) != challenge.code_hash:
            raise OTPInvalidError("Incorrect code.")


class TokenPolicy:
    """
    Pure policy constants + helper for JWT lifetimes, mirrored from
    config/settings/components/jwt.py so the domain layer states its
    own expectation of these values (used by unit tests asserting
    session `expires_at` math) without importing Django settings
    directly (domain has zero Django imports, per MIC §2.2).
    """

    ACCESS_TOKEN_MINUTES = 15
    REFRESH_TOKEN_DAYS = 30

    @classmethod
    def refresh_token_expiry(cls) -> datetime:
        return Clock.now() + timedelta(days=cls.REFRESH_TOKEN_DAYS)
