from __future__ import annotations

import pytest

from core.openapi import (
    ERROR_RESPONSE_SCHEMA,
    STANDARD_ERROR_RESPONSES,
    add_standard_headers,
    auth_examples,
    error_examples,
    pagination_examples,
)

pytestmark = pytest.mark.unit


def test_error_response_schema_has_required_top_level_fields():
    assert set(ERROR_RESPONSE_SCHEMA["required"]) == {"success", "error", "meta"}


def test_error_response_schema_error_object_has_category_enum():
    category_prop = ERROR_RESPONSE_SCHEMA["properties"]["error"]["properties"]["category"]
    assert "validation" in category_prop["enum"]
    assert "business" in category_prop["enum"]
    assert "rate_limit" in category_prop["enum"]


def test_standard_error_responses_cover_documented_status_codes():
    expected = {400, 401, 403, 404, 409, 422, 429, 500}
    assert expected.issubset(set(STANDARD_ERROR_RESPONSES.keys()))


def test_error_examples_produce_at_least_one_example_per_common_status():
    examples = error_examples()
    status_codes = {code for ex in examples for code in (ex.status_codes or [])}
    assert {"422", "409", "403", "429"}.issubset(status_codes)


def test_pagination_examples_cover_both_strategies():
    examples = pagination_examples()
    strategies = {ex.value["pagination"]["strategy"] for ex in examples}
    assert strategies == {"page", "cursor"}


def test_auth_examples_are_request_only():
    examples = auth_examples()
    assert all(ex.request_only for ex in examples)


def test_add_standard_headers_injects_headers_into_every_response():
    schema = {
        "paths": {
            "/api/v1/catalog/products": {
                "get": {
                    "responses": {
                        "200": {"description": "OK"},
                        "422": {"description": "Validation failed"},
                    }
                }
            }
        }
    }
    result = add_standard_headers(schema, generator=None, request=None, public=True)
    headers_200 = result["paths"]["/api/v1/catalog/products"]["get"]["responses"]["200"]["headers"]
    assert "X-Request-ID" in headers_200
    assert "X-Correlation-ID" in headers_200


def test_add_standard_headers_does_not_overwrite_existing_header_definition():
    schema = {
        "paths": {
            "/x": {
                "get": {
                    "responses": {
                        "200": {"headers": {"X-Request-ID": {"description": "custom", "schema": {"type": "string"}}}}
                    }
                }
            }
        }
    }
    result = add_standard_headers(schema, generator=None, request=None, public=True)
    assert result["paths"]["/x"]["get"]["responses"]["200"]["headers"]["X-Request-ID"]["description"] == "custom"


def test_add_standard_headers_handles_empty_schema_gracefully():
    result = add_standard_headers({}, generator=None, request=None, public=True)
    assert result == {}
