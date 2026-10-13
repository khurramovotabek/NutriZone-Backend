"""
The universal response envelope (Enterprise REST API Blueprint §6).

Every endpoint in the platform returns one of these shapes -- success,
paginated collection, or error. No view constructs a raw DRF `Response`
bypassing this module (Django Implementation Blueprint §5).
"""
from __future__ import annotations

import uuid
from typing import Any

from django.utils import timezone
from rest_framework.response import Response

from common.middleware.audit_context import get_current_request_id


def _meta(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    meta = {
        "request_id": get_current_request_id() or str(uuid.uuid4()),
        "timestamp": timezone.now().isoformat(),
    }
    if extra:
        meta.update(extra)
    return meta


def success_response(
    data: Any,
    status_code: int = 200,
    meta_extra: dict[str, Any] | None = None,
) -> Response:
    """Single-resource / action-result success envelope."""
    return Response(
        {"success": True, "data": data, "meta": _meta(meta_extra)},
        status=status_code,
    )


def paginated_response(
    data: list[Any],
    pagination: dict[str, Any],
    status_code: int = 200,
    meta_extra: dict[str, Any] | None = None,
) -> Response:
    """Collection success envelope (page-number or cursor strategy)."""
    return Response(
        {
            "success": True,
            "data": data,
            "pagination": pagination,
            "meta": _meta(meta_extra),
        },
        status=status_code,
    )


def error_response(
    code: str,
    message: str,
    category: str,
    status_code: int,
    details: dict[str, Any] | None = None,
) -> Response:
    """
    Uniform error envelope (REST API Blueprint §6/§7).

    `category` must be one of: authentication, authorization,
    validation, business, conflict, rate_limit, server -- enforced by
    common/exceptions/exceptions.py's exception hierarchy, not re-validated
    here, to keep this a pure serialization helper.
    """
    return Response(
        {
            "success": False,
            "error": {
                "code": code,
                "message": message,
                "category": category,
                "details": details or {},
            },
            "meta": _meta(),
        },
        status=status_code,
    )


def bulk_response(
    succeeded: list[dict[str, Any]],
    failed: list[dict[str, Any]],
    status_code: int = 200,
) -> Response:
    """Bulk create/update envelope (REST API Blueprint §6) -- partial-success by design."""
    return Response(
        {
            "success": True,
            "data": {"succeeded": succeeded, "failed": failed},
            "meta": _meta(
                {
                    "total": len(succeeded) + len(failed),
                    "succeeded_count": len(succeeded),
                    "failed_count": len(failed),
                }
            ),
        },
        status=status_code,
    )
