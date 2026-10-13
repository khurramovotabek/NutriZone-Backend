"""
Base domain exception hierarchy.

Every `apps/<context>/domain/exceptions.py` subclasses one of these
(Django Implementation Blueprint §5). No business exception is raised as
a bare `Exception`/`ValueError` anywhere past the `domain/` boundary --
this hierarchy is what lets common/exceptions/handlers.py map any
business failure to the correct HTTP status/error code (REST API
Blueprint §7) without each app writing its own exception handler.
"""
from __future__ import annotations

from typing import Any


class DomainException(Exception):
    """
    Base class for every business-rule failure in the system.

    Attributes:
        code: machine-readable error code, e.g. "ORDER_ALREADY_CANCELLED"
              (REST API Blueprint §7). Defaults to the class name in
              SCREAMING_SNAKE_CASE if not overridden.
        category: one of authentication/authorization/validation/
              business/conflict/rate_limit/server.
        http_status: the status code common/exceptions/handlers.py maps
              this exception family to.
        details: optional structured extra data for the error envelope.
    """

    code: str = "DOMAIN_ERROR"
    category: str = "business"
    http_status: int = 422

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationFailed(DomainException):
    """A business (not structural) validation rule was violated."""

    code = "VALIDATION_FAILED"
    category = "validation"
    http_status = 422


class BusinessRuleViolation(DomainException):
    """A named business invariant was violated (MIC §8's Business Rule Tests target these)."""

    code = "BUSINESS_RULE_VIOLATION"
    category = "business"
    http_status = 422


class ConflictError(DomainException):
    """A state precondition was violated (e.g. cancel an already-shipped order)."""

    code = "CONFLICT"
    category = "conflict"
    http_status = 409


class ResourceNotFound(DomainException):
    """The referenced resource does not exist (or is soft-deleted and hidden by policy)."""

    code = "RESOURCE_NOT_FOUND"
    category = "business"
    http_status = 404


class PermissionDenied(DomainException):
    """Authenticated but not permitted -- RBAC or object-level denial (REST API Blueprint §5)."""

    code = "PERMISSION_DENIED"
    category = "authorization"
    http_status = 403


class AuthenticationRequired(DomainException):
    """Missing/invalid/expired authentication."""

    code = "AUTHENTICATION_REQUIRED"
    category = "authentication"
    http_status = 401


class RateLimitExceeded(DomainException):
    """A rate limit was exceeded (REST API Blueprint §18)."""

    code = "RATE_LIMIT_EXCEEDED"
    category = "rate_limit"
    http_status = 429


class IdempotencyKeyReusedWithDifferentPayload(ConflictError):
    """
    An Idempotency-Key was reused with a different request payload.

    REST API Blueprint §15 -- this is deliberately a ConflictError
    (409), not silently treated as a duplicate, since it usually
    indicates a client bug rather than a legitimate retry.
    """

    code = "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD"
