from core.openapi.hooks import add_standard_headers
from core.openapi.schemas import (
    ERROR_RESPONSE_SCHEMA,
    STANDARD_ERROR_RESPONSES,
    auth_examples,
    error_examples,
    pagination_examples,
)

__all__ = [
    "ERROR_RESPONSE_SCHEMA",
    "STANDARD_ERROR_RESPONSES",
    "add_standard_headers",
    "auth_examples",
    "error_examples",
    "pagination_examples",
]
