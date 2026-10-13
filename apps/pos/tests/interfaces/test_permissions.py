from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from apps.pos.interfaces.api.v1.permissions import BasePosPermission, ManageSale, SearchProducts, ViewSale
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


@pytest.mark.parametrize("permission_cls,expected_code", [(ViewSale, "pos.sale.view"), (ManageSale, "pos.sale.manage"), (SearchProducts, "pos.search.view")])
def test_permission_code_matches_expected(permission_cls, expected_code):
    assert permission_cls.permission_code == expected_code


def test_all_3_permission_codes_are_unique():
    codes = {ViewSale.permission_code, ManageSale.permission_code, SearchProducts.permission_code}
    assert len(codes) == 3


def test_search_products_denies_unauthenticated_user():
    HasPermissionCode.resolver = _FakeResolver({"pos.search.view"})
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=False))
    assert SearchProducts().has_permission(request, view=None) is False


def test_search_products_allows_when_resolver_grants_the_code():
    user_id = uuid.uuid4()
    HasPermissionCode.resolver = _FakeResolver({"pos.search.view"})
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, id=user_id))
    assert SearchProducts().has_permission(request, view=None) is True


def test_denies_unauthenticated_user():
    HasPermissionCode.resolver = _FakeResolver({"pos.sale.view"})
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=False))
    assert ViewSale().has_permission(request, view=None) is False


def test_allows_when_resolver_grants_the_code():
    user_id = uuid.uuid4()
    HasPermissionCode.resolver = _FakeResolver({"pos.sale.manage"})
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, id=user_id))
    assert ManageSale().has_permission(request, view=None) is True


def test_denies_when_resolver_unconfigured():
    HasPermissionCode.resolver = None
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, id=uuid.uuid4()))
    assert ManageSale().has_permission(request, view=None) is False


def test_base_permission_fails_closed_with_no_code():
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, id=uuid.uuid4()))
    assert BasePosPermission().has_permission(request, view=None) is False
