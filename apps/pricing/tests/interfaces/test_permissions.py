from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from apps.pricing.interfaces.api.v1.permissions import (
    CanCalculatePrices, CanManageCampaigns, CanManageCashback, CanManageCoupons,
    CanManageMembershipPricing, CanManagePriceLists, CanManagePricing, CanManagePricingRules,
    CanManageRegionalPricing, CanManageSnapshots, CanPreviewPrices, CanViewPricing, CanViewPriceHistory,
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
        (CanViewPricing, "pricing.item.view"),
        (CanManagePricing, "pricing.item.manage"),
        (CanManagePriceLists, "pricing.price_list.manage"),
        (CanManagePricingRules, "pricing.rule.manage"),
        (CanManageCampaigns, "pricing.campaign.manage"),
        (CanManageCoupons, "pricing.coupon.manage"),
        (CanManageSnapshots, "pricing.snapshot.manage"),
        (CanCalculatePrices, "pricing.calculation.execute"),
        (CanPreviewPrices, "pricing.calculation.preview"),
        (CanViewPriceHistory, "pricing.history.view"),
        (CanManageRegionalPricing, "pricing.rule.regional.manage"),
        (CanManageMembershipPricing, "pricing.rule.membership.manage"),
        (CanManageCashback, "pricing.cashback.manage"),
    ],
)
def test_permission_code_matches_expected(permission_cls, expected_code):
    assert permission_cls.permission_code == expected_code


def test_all_thirteen_permission_codes_are_unique():
    codes = {
        CanViewPricing.permission_code, CanManagePricing.permission_code, CanManagePriceLists.permission_code,
        CanManagePricingRules.permission_code, CanManageCampaigns.permission_code, CanManageCoupons.permission_code,
        CanManageSnapshots.permission_code, CanCalculatePrices.permission_code,
        CanPreviewPrices.permission_code, CanViewPriceHistory.permission_code, CanManageRegionalPricing.permission_code,
        CanManageMembershipPricing.permission_code, CanManageCashback.permission_code,
    }
    assert len(codes) == 13


def test_denies_unauthenticated_user():
    HasPermissionCode.resolver = _FakeResolver({"pricing.price_list.manage"})
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=False))
    assert CanManagePriceLists().has_permission(request, view=None) is False


def test_allows_when_resolver_grants_the_code():
    user_id = uuid.uuid4()
    HasPermissionCode.resolver = _FakeResolver({"pricing.calculation.execute"})
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, id=user_id))
    assert CanCalculatePrices().has_permission(request, view=None) is True


def test_denies_when_resolver_unconfigured():
    HasPermissionCode.resolver = None
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, id=uuid.uuid4()))
    assert CanManageCampaigns().has_permission(request, view=None) is False
