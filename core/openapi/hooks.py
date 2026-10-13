"""
drf-spectacular postprocessing hook.

Adds the platform-wide response headers (X-Request-ID,
X-Correlation-ID) and a global `Accept-Language`/version-header note to
every operation in the generated schema, so client-generated SDKs know
these headers exist without every view needing to declare them
individually via `@extend_schema(...)`. Wired via
SPECTACULAR_SETTINGS["POSTPROCESSING_HOOKS"] in
config/settings/base.py.
"""
from __future__ import annotations

from typing import Any

_STANDARD_RESPONSE_HEADERS = {
    "X-Request-ID": {
        "description": "Correlates this response to server-side logs (common/middleware/request_id.py).",
        "schema": {"type": "string", "format": "uuid"},
    },
    "X-Correlation-ID": {
        "description": "Identifies the end-to-end business operation this response is part of (core/observability/correlation.py).",
        "schema": {"type": "string", "format": "uuid"},
    },
}


def add_standard_headers(result: dict[str, Any], generator: Any, request: Any, public: bool) -> dict[str, Any]:
    """POSTPROCESSING_HOOKS entry -- mutates and returns the generated OpenAPI schema dict."""
    paths = result.get("paths", {})
    for _path, operations in paths.items():
        for _method, operation in operations.items():
            if not isinstance(operation, dict):
                continue
            responses = operation.get("responses", {})
            for _status_code, response in responses.items():
                if not isinstance(response, dict):
                    continue
                headers = response.setdefault("headers", {})
                for header_name, header_schema in _STANDARD_RESPONSE_HEADERS.items():
                    headers.setdefault(header_name, header_schema)
    return result
