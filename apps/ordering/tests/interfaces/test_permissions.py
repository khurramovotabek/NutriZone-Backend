from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from apps.ordering.interfaces.api.v1.permissions import (
    AdminOrder, ApproveCancellation, ApproveReturn, ArchiveOrder, CreateOrder, IssueInvoice, LockOrder,
    RefundReturn, RejectCancellation, RejectReturn, ReceiveReturn, RestoreOrder, UnlockOrder, UpdateOrder,
    ViewAnyOrder, ViewOwnOrder,
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
        (CreateOrder, "ordering.order.create"), (ViewOwnOrder, "ordering.order.view_own"), (ViewAnyOrder, "ordering.order.view_any"),
        (UpdateOrder, "ordering.order.update"), (ArchiveOrder, "ordering.order.archive"), (RestoreOrder, "ordering.order.restore"),
        (LockOrder, "ordering.order.lock"), (UnlockOrder, "ordering.order.unlock"), (ApproveReturn, "ordering.return.approve"),
        (RejectReturn, "ordering.return.reject"), (ReceiveReturn, "ordering.return.receive"), (RefundReturn, "ordering.return.refund"),
        (ApproveCancellation, "ordering.cancellation.approve"), (RejectCancellation, "ordering.cancellation.reject"),
        (IssueInvoice, "ordering.invoice.issue"), (AdminOrder, "ordering.admin.manage"),
    ],
)
def test_permission_code_matches_expected(permission_cls, expected_code):
    assert permission_cls.permission_code == expected_code


def test_all_16_permission_codes_are_unique():
    codes = {
        CreateOrder.permission_code, ViewOwnOrder.permission_code, ViewAnyOrder.permission_code, UpdateOrder.permission_code,
        ArchiveOrder.permission_code, RestoreOrder.permission_code, LockOrder.permission_code, UnlockOrder.permission_code,
        ApproveReturn.permission_code, RejectReturn.permission_code, ReceiveReturn.permission_code, RefundReturn.permission_code,
        ApproveCancellation.permission_code, RejectCancellation.permission_code, IssueInvoice.permission_code, AdminOrder.permission_code,
    }
    assert len(codes) == 16


def test_denies_unauthenticated_user():
    HasPermissionCode.resolver = _FakeResolver({"ordering.order.create"})
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=False))
    assert CreateOrder().has_permission(request, view=None) is False


def test_allows_when_resolver_grants_the_code():
    user_id = uuid.uuid4()
    HasPermissionCode.resolver = _FakeResolver({"ordering.order.lock"})
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, id=user_id))
    assert LockOrder().has_permission(request, view=None) is True


def test_denies_when_resolver_unconfigured():
    HasPermissionCode.resolver = None
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, id=uuid.uuid4()))
    assert AdminOrder().has_permission(request, view=None) is False
