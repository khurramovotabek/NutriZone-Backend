"""
Pricing API permission classes.

Reuses Identity's RBAC engine exactly, matching every prior module's
`interfaces/api/v1/permissions.py` pattern -- every class below is a
thin, named wrapper calling `common.permissions.HasPermissionCode.
resolver` with a Pricing-specific permission code. No authorization
logic is duplicated here.
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission


class _PricingPermission(BasePermission):
    """Base class -- subclasses set `permission_code`."""

    permission_code: str = ""

    def has_permission(self, request, view) -> bool:
        if not self.permission_code:
            return False  # fail closed
        if not request.user or not getattr(request.user, "is_authenticated", False):
            return False

        from common.permissions import HasPermissionCode

        resolver = HasPermissionCode.resolver
        if resolver is None:
            return False

        store_id = getattr(view, "get_permission_store_id", lambda: None)()
        return resolver.user_has_permission(request.user.id, self.permission_code, store_id)


class CanViewPricing(_PricingPermission):
    permission_code = "pricing.item.view"


class CanManagePricing(_PricingPermission):
    """Umbrella admin permission -- used only where no narrower code applies (e.g. cross-cutting admin listing)."""

    permission_code = "pricing.item.manage"


class CanManagePriceLists(_PricingPermission):
    permission_code = "pricing.price_list.manage"


class CanManagePricingRules(_PricingPermission):
    permission_code = "pricing.rule.manage"


class CanManageCampaigns(_PricingPermission):
    permission_code = "pricing.campaign.manage"


class CanManageCoupons(_PricingPermission):
    permission_code = "pricing.coupon.manage"


class CanManageSnapshots(_PricingPermission):
    permission_code = "pricing.snapshot.manage"


class CanCalculatePrices(_PricingPermission):
    permission_code = "pricing.calculation.execute"


class CanIssuePriceSnapshot(_PricingPermission):
    """Phase 09.4: a new, narrow, customer-safe permission for the new snapshot-issuance endpoint -- deliberately distinct from CanCalculatePrices, which requires full pricing-admin access and a caller-supplied price_list_id (unsafe to expose to ordinary customers)."""

    permission_code = "pricing.snapshot.issue"


class CanPreviewPrices(_PricingPermission):
    permission_code = "pricing.calculation.preview"


class CanViewPriceHistory(_PricingPermission):
    permission_code = "pricing.history.view"


class CanManageRegionalPricing(_PricingPermission):
    """Covers REGIONAL-type PricingRule management -- distinct from CanManagePricingRules so regional-pricing authority can be delegated separately from the broader rule set (e.g. to a regional ops lead)."""

    permission_code = "pricing.rule.regional.manage"


class CanManageMembershipPricing(_PricingPermission):
    """Covers MEMBERSHIP-type PricingRule management -- same delegation rationale as CanManageRegionalPricing."""

    permission_code = "pricing.rule.membership.manage"


class CanManageCashback(_PricingPermission):
    """Covers cashback-rate configuration -- Pricing only computes cashback amounts (domain/services.py::CashbackPolicy); this permission gates who can configure the rate/policy inputs, not any Wallet-side crediting action."""

    permission_code = "pricing.cashback.manage"
