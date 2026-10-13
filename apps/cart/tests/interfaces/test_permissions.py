from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from apps.cart.interfaces.api.v1.permissions import (
    CanAttachCoupon, CanAttachPriceSnapshot, CanAttachReservation, CanConvertCart, CanCreateCart, CanDeleteCart,
    CanLockCart, CanManageCart, CanManageCartItems, CanManageGuestCart, CanMergeCart, CanSearchCart,
    CanUpdateCart, CanValidateCart, CanViewCart, CanViewCartAudit,
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
        (CanViewCart, "cart.item.view"),
        (CanManageCart, "cart.item.manage"),
        (CanCreateCart, "cart.item.create"),
        (CanUpdateCart, "cart.item.update"),
        (CanDeleteCart, "cart.item.delete"),
        (CanManageCartItems, "cart.line_item.manage"),
        (CanMergeCart, "cart.merge.execute"),
        (CanLockCart, "cart.lock.manage"),
        (CanConvertCart, "cart.convert.execute"),
        (CanAttachCoupon, "cart.coupon_reference.manage"),
        (CanAttachReservation, "cart.reservation_reference.manage"),
        (CanAttachPriceSnapshot, "cart.price_reference.manage"),
        (CanValidateCart, "cart.validation.execute"),
        (CanViewCartAudit, "cart.audit.view"),
        (CanManageGuestCart, "cart.guest.manage"),
        (CanSearchCart, "cart.search.execute"),
    ],
)
def test_permission_code_matches_expected(permission_cls, expected_code):
    assert permission_cls.permission_code == expected_code


def test_all_sixteen_permission_codes_are_unique():
    codes = {
        CanViewCart.permission_code, CanManageCart.permission_code, CanCreateCart.permission_code, CanUpdateCart.permission_code,
        CanDeleteCart.permission_code, CanManageCartItems.permission_code, CanMergeCart.permission_code, CanLockCart.permission_code,
        CanConvertCart.permission_code, CanAttachCoupon.permission_code, CanAttachReservation.permission_code,
        CanAttachPriceSnapshot.permission_code, CanValidateCart.permission_code, CanViewCartAudit.permission_code,
        CanManageGuestCart.permission_code, CanSearchCart.permission_code,
    }
    assert len(codes) == 16


def test_allows_unauthenticated_user_for_a_guest_permitted_action():
    """Real, product-required behavior: CanCreateCart.allow_anonymous=True lets an anonymous visitor create their own guest cart -- real per-object ownership is enforced separately, by _require_cart_ownership()'s X-Cart-Token check."""
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=False))
    assert CanCreateCart().has_permission(request, view=None) is True


def test_still_denies_unauthenticated_user_for_an_admin_only_action():
    """CanManageCart (the admin "umbrella" permission) is deliberately NOT guest-permitted -- confirms the fix above didn't loosen every Cart permission, only the ones a guest genuinely needs."""
    HasPermissionCode.resolver = _FakeResolver({"cart.item.manage"})
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=False))
    assert CanManageCart().has_permission(request, view=None) is False


def test_allows_when_resolver_grants_the_code():
    user_id = uuid.uuid4()
    HasPermissionCode.resolver = _FakeResolver({"cart.lock.manage"})
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, id=user_id))
    assert CanLockCart().has_permission(request, view=None) is True


def test_denies_when_resolver_unconfigured():
    HasPermissionCode.resolver = None
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, id=uuid.uuid4()))
    assert CanManageCart().has_permission(request, view=None) is False
