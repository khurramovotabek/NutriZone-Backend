"""
Top-level pytest fixtures.

Only genuinely cross-app fixtures live here (Django Implementation
Blueprint §11) -- per-app fixtures/factories live inside
`apps/<context>/tests/factories.py` and are pulled in via
`tests/factories/__init__.py` re-exports as each module is built.
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api_client() -> APIClient:
    """An unauthenticated DRF test client using the standard envelope."""
    return APIClient()


@pytest.fixture
def actor_id() -> uuid.UUID:
    """A deterministic UUID standing in for 'the current user' in tests
    that need to assert created_by/updated_by population without a real
    `identity` user model existing yet."""
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture(autouse=True)
def _reset_audit_context():
    """
    Ensures common/middleware/audit_context.py's contextvars don't leak
    state between tests (each test should see a clean actor/request-id
    context unless it explicitly sets one).
    """
    from common.middleware.audit_context import _current_actor_id, _current_request_id

    actor_token = _current_actor_id.set(None)
    request_token = _current_request_id.set(None)
    yield
    _current_actor_id.reset(actor_token)
    _current_request_id.reset(request_token)


@pytest.fixture
def django_db_setup(django_db_setup, django_db_blocker):
    """
    Placeholder override point: once PostGIS-dependent models exist
    (stores.store_locations, fulfillment.delivery_zones per the
    Enterprise Database Blueprint §4.5/§4.7), the PostGIS extension must
    be created in the test database here. No-op at foundation stage
    since no such models exist yet.
    """
    with django_db_blocker.unblock():
        pass
    yield
