"""
Standard OpenAPI schemas and examples.

Provides the reusable building blocks every module's
`interfaces/api/v1/views.py` composes into its own `@extend_schema(...)`
calls (drf-spectacular), so the error/pagination/auth documentation
shape is defined once here rather than re-typed per endpoint --
matching Enterprise REST API Blueprint §17's "generated from code,
matched against this blueprint" documentation standard.
"""
from __future__ import annotations

from drf_spectacular.utils import OpenApiExample, OpenApiResponse

# --- Standard error response schema, matching common/responses/envelope.py ---

ERROR_RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean", "example": False},
        "error": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "example": "VALIDATION_FAILED"},
                "message": {"type": "string", "example": "One or more fields are invalid"},
                "category": {
                    "type": "string",
                    "enum": [
                        "authentication",
                        "authorization",
                        "validation",
                        "business",
                        "conflict",
                        "rate_limit",
                        "server",
                    ],
                },
                "details": {"type": "object"},
            },
            "required": ["code", "message", "category"],
        },
        "meta": {
            "type": "object",
            "properties": {
                "request_id": {"type": "string", "format": "uuid"},
                "timestamp": {"type": "string", "format": "date-time"},
            },
        },
    },
    "required": ["success", "error", "meta"],
}


def error_examples() -> list[OpenApiExample]:
    return [
        OpenApiExample(
            "ValidationError",
            value={
                "success": False,
                "error": {
                    "code": "VALIDATION_FAILED",
                    "message": "One or more fields are invalid",
                    "category": "validation",
                    "details": {"fields": [{"field": "phone_number", "code": "INVALID_FORMAT", "message": "..."}]},
                },
                "meta": {"request_id": "3f1b1e2a-0000-4000-8000-000000000000", "timestamp": "2026-08-01T09:00:00Z"},
            },
            response_only=True,
            status_codes=["422"],
        ),
        OpenApiExample(
            "BusinessError",
            value={
                "success": False,
                "error": {
                    "code": "ORDER_ALREADY_CANCELLED",
                    "message": "This order has already been cancelled.",
                    "category": "business",
                    "details": {},
                },
                "meta": {"request_id": "3f1b1e2a-0000-4000-8000-000000000001", "timestamp": "2026-08-01T09:00:01Z"},
            },
            response_only=True,
            status_codes=["409"],
        ),
        OpenApiExample(
            "PermissionDenied",
            value={
                "success": False,
                "error": {"code": "PERMISSION_DENIED", "message": "You do not have permission to perform this action.", "category": "authorization", "details": {}},
                "meta": {"request_id": "3f1b1e2a-0000-4000-8000-000000000002", "timestamp": "2026-08-01T09:00:02Z"},
            },
            response_only=True,
            status_codes=["403"],
        ),
        OpenApiExample(
            "RateLimitExceeded",
            value={
                "success": False,
                "error": {"code": "RATE_LIMIT_EXCEEDED", "message": "Too many requests.", "category": "rate_limit", "details": {}},
                "meta": {"request_id": "3f1b1e2a-0000-4000-8000-000000000003", "timestamp": "2026-08-01T09:00:03Z"},
            },
            response_only=True,
            status_codes=["429"],
        ),
    ]


def pagination_examples() -> list[OpenApiExample]:
    return [
        OpenApiExample(
            "PageNumberPagination",
            value={
                "success": True,
                "data": [{"id": "..."}],
                "pagination": {"strategy": "page", "page": 2, "page_size": 20, "total_pages": 14, "total_count": 274},
                "meta": {"request_id": "...", "timestamp": "2026-08-01T09:00:00Z"},
            },
            response_only=True,
        ),
        OpenApiExample(
            "CursorPagination",
            value={
                "success": True,
                "data": [{"id": "..."}],
                "pagination": {"strategy": "cursor", "next_cursor": "cD0yMDI2LTA4LTAxKzA5JTNBMDAlM0EwMA%3D%3D", "has_more": True},
                "meta": {"request_id": "...", "timestamp": "2026-08-01T09:00:00Z"},
            },
            response_only=True,
        ),
    ]


def auth_examples() -> list[OpenApiExample]:
    return [
        OpenApiExample(
            "BearerToken",
            value={"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."},
            request_only=True,
            media_type="application/json",
        ),
    ]


STANDARD_ERROR_RESPONSES: dict[int, OpenApiResponse] = {
    400: OpenApiResponse(description="Malformed request", response=ERROR_RESPONSE_SCHEMA),
    401: OpenApiResponse(description="Authentication required or token invalid/expired", response=ERROR_RESPONSE_SCHEMA),
    403: OpenApiResponse(description="Permission denied", response=ERROR_RESPONSE_SCHEMA),
    404: OpenApiResponse(description="Resource not found", response=ERROR_RESPONSE_SCHEMA),
    409: OpenApiResponse(description="Conflict with current resource state", response=ERROR_RESPONSE_SCHEMA),
    422: OpenApiResponse(description="Business or field validation failed", response=ERROR_RESPONSE_SCHEMA),
    429: OpenApiResponse(description="Rate limit exceeded", response=ERROR_RESPONSE_SCHEMA),
    500: OpenApiResponse(description="Unexpected server error", response=ERROR_RESPONSE_SCHEMA),
    503: OpenApiResponse(description="Service temporarily unavailable (e.g. upstream delivery provider failure or a feature disabled)", response=ERROR_RESPONSE_SCHEMA),
}
