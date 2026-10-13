from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from apps.chat.interfaces.api.v1.permissions import (
    BaseChatPermission, EditMessage, ManageConversation, SendMessage, ViewOwnConversations, ViewStatistics,
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
        (ViewOwnConversations, "chat.conversation.view_own"), (ManageConversation, "chat.conversation.manage"),
        (SendMessage, "chat.message.send"), (EditMessage, "chat.message.edit"), (ViewStatistics, "chat.statistics.view"),
    ],
)
def test_permission_code_matches_expected(permission_cls, expected_code):
    assert permission_cls.permission_code == expected_code


def test_all_5_permission_codes_are_unique():
    codes = {ViewOwnConversations.permission_code, ManageConversation.permission_code, SendMessage.permission_code, EditMessage.permission_code, ViewStatistics.permission_code}
    assert len(codes) == 5


def test_denies_unauthenticated_user():
    HasPermissionCode.resolver = _FakeResolver({"chat.conversation.view_own"})
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=False))
    assert ViewOwnConversations().has_permission(request, view=None) is False


def test_allows_when_resolver_grants_the_code():
    user_id = uuid.uuid4()
    HasPermissionCode.resolver = _FakeResolver({"chat.conversation.manage"})
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, id=user_id))
    assert ManageConversation().has_permission(request, view=None) is True


def test_denies_when_resolver_unconfigured():
    HasPermissionCode.resolver = None
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, id=uuid.uuid4()))
    assert ViewStatistics().has_permission(request, view=None) is False


def test_base_permission_fails_closed_with_no_code():
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, id=uuid.uuid4()))
    assert BaseChatPermission().has_permission(request, view=None) is False
