from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from apps.notifications.interfaces.api.v1.permissions import (
    BaseNotificationPermission, CreateNotification, ManageOwnNotifications, ManageOwnPreferences, ViewOwnNotifications,
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
        (ViewOwnNotifications, "notifications.notification.view_own"), (ManageOwnNotifications, "notifications.notification.manage_own"),
        (ManageOwnPreferences, "notifications.preference.manage_own"), (CreateNotification, "notifications.notification.create"),
    ],
)
def test_permission_code_matches_expected(permission_cls, expected_code):
    assert permission_cls.permission_code == expected_code


def test_all_4_permission_codes_are_unique():
    codes = {ViewOwnNotifications.permission_code, ManageOwnNotifications.permission_code, ManageOwnPreferences.permission_code, CreateNotification.permission_code}
    assert len(codes) == 4


def test_denies_unauthenticated_user():
    HasPermissionCode.resolver = _FakeResolver({"notifications.notification.view_own"})
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=False))
    assert ViewOwnNotifications().has_permission(request, view=None) is False


def test_allows_when_resolver_grants_the_code():
    user_id = uuid.uuid4()
    HasPermissionCode.resolver = _FakeResolver({"notifications.notification.manage_own"})
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, id=user_id))
    assert ManageOwnNotifications().has_permission(request, view=None) is True


def test_denies_when_resolver_unconfigured():
    HasPermissionCode.resolver = None
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, id=uuid.uuid4()))
    assert ManageOwnPreferences().has_permission(request, view=None) is False


def test_base_permission_fails_closed_with_no_code():
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, id=uuid.uuid4()))
    assert BaseNotificationPermission().has_permission(request, view=None) is False
