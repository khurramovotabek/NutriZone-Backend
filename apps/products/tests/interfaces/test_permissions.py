from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from apps.products.interfaces.api.v1.permissions import (
    BrandPermission,
    CatalogArchivePermission,
    CatalogManagePermission,
    CatalogMediaPermission,
    CatalogPublishPermission,
    CatalogSEOPermission,
    CatalogViewPermission,
    CategoryPermission,
    VariantPermission,
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
        (CatalogViewPermission, "products.product.view"),
        (CatalogManagePermission, "products.product.manage"),
        (CatalogPublishPermission, "products.product.publish"),
        (CatalogArchivePermission, "products.product.archive"),
        (CatalogMediaPermission, "products.media.manage"),
        (CatalogSEOPermission, "products.seo.manage"),
        (VariantPermission, "products.variant.manage"),
        (CategoryPermission, "products.category.manage"),
        (BrandPermission, "products.brand.manage"),
    ],
)
def test_permission_code_matches_expected(permission_cls, expected_code):
    assert permission_cls.permission_code == expected_code


def test_denies_unauthenticated_user():
    HasPermissionCode.resolver = _FakeResolver({"products.product.view"})
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=False))
    assert CatalogViewPermission().has_permission(request, view=None) is False


def test_denies_when_resolver_unconfigured():
    HasPermissionCode.resolver = None
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, id=uuid.uuid4()))
    assert CatalogViewPermission().has_permission(request, view=None) is False


def test_allows_when_resolver_grants_the_code():
    user_id = uuid.uuid4()
    HasPermissionCode.resolver = _FakeResolver({"products.product.manage"})
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, id=user_id))
    assert CatalogManagePermission().has_permission(request, view=None) is True


def test_denies_when_resolver_does_not_grant_the_code():
    user_id = uuid.uuid4()
    HasPermissionCode.resolver = _FakeResolver({"products.product.view"})  # granted a different code
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, id=user_id))
    assert CatalogManagePermission().has_permission(request, view=None) is False


def test_publish_and_manage_are_distinct_permission_codes():
    """Verifies the deliberate design choice that publish requires a narrower grant than general manage (higher blast radius)."""
    assert CatalogPublishPermission.permission_code != CatalogManagePermission.permission_code
