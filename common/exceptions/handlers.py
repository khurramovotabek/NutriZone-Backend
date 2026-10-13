"""
The single custom DRF exception handler.

Wired via REST_FRAMEWORK["EXCEPTION_HANDLER"] in config/settings/base.py.
Translates DomainException subclasses, DRF's own exceptions, and raw
Django/DB exceptions into the one error envelope shape defined in
common/responses/envelope.py -- no other code path is permitted to
construct an error response (Django Implementation Blueprint §5).
"""
from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response

from common.exceptions.exceptions import DomainException
from common.responses.envelope import error_response

logger = logging.getLogger("nutrizone.errors")


def nutrizone_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    # 1. Our own domain exception hierarchy -- the common case.
    if isinstance(exc, DomainException):
        return error_response(
            code=exc.code,
            message=exc.message,
            category=exc.category,
            status_code=exc.http_status,
            details=exc.details,
        )

    # 2. DRF validation errors -- structural (serializer) validation, per
    #    the 400-vs-422 split in Django Implementation Blueprint §6.
    if isinstance(exc, drf_exceptions.ValidationError):
        fields = []
        detail = exc.detail
        if isinstance(detail, dict):
            for field, errors in detail.items():
                for err in errors if isinstance(errors, list) else [errors]:
                    fields.append({"field": field, "code": "INVALID", "message": str(err)})
        else:
            fields.append({"field": "non_field_errors", "code": "INVALID", "message": str(detail)})
        return error_response(
            code="VALIDATION_FAILED",
            message="One or more fields are invalid",
            category="validation",
            status_code=422,
            details={"fields": fields},
        )

    # 3. Standard DRF exceptions (auth, throttling, method not allowed, 404).
    if isinstance(exc, drf_exceptions.APIException):
        # Deliberate local import, not a style violation: importing
        # `rest_framework.views.exception_handler` at module level
        # triggers DRF's eager `DEFAULT_AUTHENTICATION_CLASSES`
        # settings resolution during Django app startup (via
        # `rest_framework.schemas`), which can race against
        # in-progress app `ready()` hooks and raise a genuine
        # circular-import error -- confirmed directly by running
        # `manage.py check`, not assumed. Deferring this import until
        # the handler actually runs (well after Django's own app
        # registry has fully populated) avoids that race entirely.
        from rest_framework.views import exception_handler as drf_default_handler

        response = drf_default_handler(exc, context)
        code_map = {
            drf_exceptions.NotAuthenticated: ("AUTHENTICATION_REQUIRED", "authentication"),
            drf_exceptions.AuthenticationFailed: ("TOKEN_INVALID", "authentication"),
            drf_exceptions.PermissionDenied: ("PERMISSION_DENIED", "authorization"),
            drf_exceptions.NotFound: ("RESOURCE_NOT_FOUND", "business"),
            drf_exceptions.Throttled: ("RATE_LIMIT_EXCEEDED", "rate_limit"),
            drf_exceptions.MethodNotAllowed: ("MALFORMED_REQUEST", "authentication"),
        }
        error_code, category = code_map.get(type(exc), ("API_ERROR", "server"))
        return error_response(
            code=error_code,
            message=str(exc.detail) if hasattr(exc, "detail") else str(exc),
            category=category,
            status_code=response.status_code if response is not None else 500,
        )

    # 4. Django-native exceptions that can surface through DRF views.
    if isinstance(exc, Http404):
        return error_response("RESOURCE_NOT_FOUND", "The requested resource was not found.", "business", 404)
    if isinstance(exc, DjangoPermissionDenied):
        return error_response("PERMISSION_DENIED", str(exc) or "Permission denied.", "authorization", 403)
    if isinstance(exc, DjangoValidationError):
        return error_response("VALIDATION_FAILED", "; ".join(exc.messages), "validation", 422)

    # 5. Integrity errors -- a repository should normally translate these
    #    into a DomainException before they get here (MIC §6 "Database
    #    Validation" tier); this is the last-resort safety net.
    if isinstance(exc, IntegrityError):
        logger.warning("Unhandled IntegrityError reached the exception handler", exc_info=exc)
        return error_response("CONFLICT", "A database constraint was violated.", "conflict", 409)

    # 6. Anything else is a genuine unhandled server error -- log with full
    #    context and return the generic envelope, never leak internals.
    logger.exception("Unhandled exception", exc_info=exc)
    return error_response("INTERNAL_ERROR", "An unexpected error occurred.", "server", 500)
