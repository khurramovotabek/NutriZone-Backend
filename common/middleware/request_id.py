"""
Request-ID correlation middleware.

Every response carries an `X-Request-ID` header, and every structured
log line emitted during the request includes the same ID (see
common/utils/logging_filters.py) -- this is the "request/task
correlation ID" referenced in Django Implementation Blueprint §6/§12.
"""
from __future__ import annotations

import uuid
from typing import Callable

from django.http import HttpRequest, HttpResponse

from common.middleware.audit_context import _current_request_id

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.headers.get(REQUEST_ID_HEADER)
        request_id = incoming or str(uuid.uuid4())
        request.request_id = request_id  # type: ignore[attr-defined]
        token = _current_request_id.set(request_id)
        try:
            response = self.get_response(request)
            response[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            _current_request_id.reset(token)
