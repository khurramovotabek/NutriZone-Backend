from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from apps.geo.interfaces.api.v1.permissions import (
    AddressOwnerPermission,
    GeoAddressPermission,
    GeoManagePermission,
    GeoViewPermission,
)
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


@pytest.mark.parametrize(
    "permission_cls,expected_code",
    [
        (GeoViewPermission, "geo.hierarchy.view"),
        (GeoManagePermission, "geo.hierarchy.manage"),
        (GeoAddressPermission, "geo.address.manage_any"),
    ],
)
def test_permission_code_matches_expected(permission_cls, expected_code):
    assert permission_cls.permission_code == expected_code


def test_denies_unauthenticated_user():
    HasPermissionCode.resolver = _FakeResolver({"geo.hierarchy.view"})
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=False))
    assert GeoViewPermission().has_permission(request, view=None) is False


def test_allows_when_resolver_grants_the_code():
    user_id = uuid.uuid4()
    HasPermissionCode.resolver = _FakeResolver({"geo.hierarchy.manage"})
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, id=user_id))
    assert GeoManagePermission().has_permission(request, view=None) is True


class TestAddressOwnerPermission:
    def test_has_permission_requires_authentication(self):
        request = SimpleNamespace(user=SimpleNamespace(is_authenticated=False))
        assert AddressOwnerPermission().has_permission(request, view=None) is False

    def test_object_permission_allows_owner(self):
        user_id = uuid.uuid4()
        request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, id=user_id))
        address = SimpleNamespace(owner_type="user", owner_id=user_id)
        assert AddressOwnerPermission().has_object_permission(request, view=None, obj=address) is True

    def test_object_permission_denies_non_owner(self):
        request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, id=uuid.uuid4()))
        address = SimpleNamespace(owner_type="user", owner_id=uuid.uuid4())
        assert AddressOwnerPermission().has_object_permission(request, view=None, obj=address) is False
