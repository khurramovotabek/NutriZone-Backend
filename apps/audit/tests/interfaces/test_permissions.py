from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.audit.interfaces.api.v1.permissions import BaseAuditPermission, ViewActivityTimeline
from common.permissions import HasPermissionCode

pytestmark = pytest.mark.unit


class _FakeResolver:
    def __init__(self, granted_codes: set[str]) -> None:
        self.granted_codes = granted_codes

    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return permission_code in self.granted_codes


@pytest.fixture(autouse=True)
def _reset_resolver():
    original = HasPermissionCode.resolver
    yield
    HasPermissionCode.resolver = original


def test_view_activity_timeline_code():
    assert ViewActivityTimeline.permission_code == "audit.log.view"


def test_base_permission_fails_closed_with_no_code():
    perm = BaseAuditPermission()
    request = SimpleNamespace(user=SimpleNamespace(id="u1", is_authenticated=True))
    assert perm.has_permission(request, view=None) is False


def test_unauthenticated_denied():
    HasPermissionCode.resolver = _FakeResolver(granted_codes={"audit.log.view"})
    request = SimpleNamespace(user=SimpleNamespace(id="u1", is_authenticated=False))
    assert ViewActivityTimeline().has_permission(request, view=None) is False


def test_authenticated_with_code_granted():
    HasPermissionCode.resolver = _FakeResolver(granted_codes={"audit.log.view"})
    request = SimpleNamespace(user=SimpleNamespace(id="u1", is_authenticated=True))
    assert ViewActivityTimeline().has_permission(request, view=None) is True


def test_authenticated_without_code_denied():
    HasPermissionCode.resolver = _FakeResolver(granted_codes=set())
    request = SimpleNamespace(user=SimpleNamespace(id="u1", is_authenticated=True))
    assert ViewActivityTimeline().has_permission(request, view=None) is False


def test_no_resolver_configured_fails_closed():
    HasPermissionCode.resolver = None
    request = SimpleNamespace(user=SimpleNamespace(id="u1", is_authenticated=True))
    assert ViewActivityTimeline().has_permission(request, view=None) is False
