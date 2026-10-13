"""
Identity domain exceptions.

All subclass common/exceptions/exceptions.py's DomainException hierarchy
(Django Implementation Blueprint §5) so common/exceptions/handlers.py
translates every one of these into the correct HTTP status/error code
(Enterprise REST API Blueprint §7) without identity needing its own
exception handler.
"""
from __future__ import annotations

from common.exceptions import AuthenticationRequired, BusinessRuleViolation, ConflictError, DomainException, PermissionDenied


class OTPExpiredError(BusinessRuleViolation):
    code = "OTP_EXPIRED"


class OTPDeliveryFailedError(DomainException):
    """
    The OTP could not be delivered by the configured provider -- covers
    both a retryable provider failure (send_otp() returned False) and a
    non-retryable one (the provider raised its own provider-specific
    exception, caught and translated here). Subclasses DomainException
    directly, not an existing subclass, since no existing exception in
    the hierarchy represents "an external dependency is unavailable" --
    the correct HTTP semantic is 503, not 422/409/429.
    """

    code = "OTP_DELIVERY_FAILED"
    category = "server"
    http_status = 503


class OTPMaxAttemptsExceededError(BusinessRuleViolation):
    code = "OTP_MAX_ATTEMPTS_EXCEEDED"
    http_status = 429
    category = "rate_limit"


class OTPResendTooSoonError(BusinessRuleViolation):
    code = "OTP_RESEND_TOO_SOON"
    http_status = 429
    category = "rate_limit"


class OTPInvalidError(BusinessRuleViolation):
    code = "OTP_INVALID"


class AccountBlockedError(AuthenticationRequired):
    code = "ACCOUNT_BLOCKED"


class InvalidProfileTransitionError(ConflictError):
    code = "INVALID_PROFILE_TRANSITION"


class TelegramSignatureInvalidError(AuthenticationRequired):
    code = "TELEGRAM_SIGNATURE_INVALID"


class RefreshTokenInvalidError(AuthenticationRequired):
    code = "TOKEN_INVALID"


class RefreshTokenReusedError(AuthenticationRequired):
    """
    A rotated-out refresh token was presented again -- per Architecture
    Review §14, this is treated as token theft: the entire session
    family is revoked, and a SuspiciousLoginDetected event is raised by
    the calling Application Service (not here -- raising the event is
    an orchestration concern, this exception only signals the security
    condition to the caller).
    """

    code = "TOKEN_REUSE_DETECTED"


class PermissionCodeUnknownError(PermissionDenied):
    code = "PERMISSION_CODE_UNKNOWN"


class RoleAlreadyAssignedError(ConflictError):
    code = "ROLE_ALREADY_ASSIGNED"
