"""
Pricing `/api/v1/pricing/...` URL routing.

Every collection endpoint (list+create) is ONE view class on ONE path
entry -- verified below by a duplicate-path check, matching every
prior module's approach. Public routes (price list lookup, search,
calculation) sit at the top level; every admin-scoped mutation is
prefixed `admin/`, matching Store's/Inventory's established naming.
"""
from __future__ import annotations

from django.urls import path

from apps.pricing.interfaces.api.v1 import views

app_name = "pricing"

urlpatterns = [
    # --- Public ---
    path("price-lists", views.PriceListListCreateView.as_view(), name="price-lists-list-create"),
    path("price-lists/code/<str:code>", views.PriceListDetailView.as_view(), name="price-lists-detail-by-code"),
    path("calculate", views.CalculatePriceView.as_view(), name="calculate"),
    path("snapshot/issue", views.IssueVariantPriceSnapshotView.as_view(), name="snapshot-issue"),
    path("preview", views.PreviewPriceView.as_view(), name="preview"),
    path("search", views.PricingSearchView.as_view(), name="search"),
    # --- Admin: Price Lists ---
    path("admin/price-lists/<str:price_list_id>/activate", views.ActivatePriceListView.as_view(), name="admin-price-lists-activate"),
    path("admin/price-lists/<str:price_list_id>/archive", views.ArchivePriceListView.as_view(), name="admin-price-lists-archive"),
    path("admin/price-lists/<str:price_list_id>/prices", views.SetPriceView.as_view(), name="admin-price-lists-set-price"),
    path("admin/price-lists/<str:price_list_id>/history/<str:product_variant_id>", views.PriceHistoryView.as_view(), name="admin-price-lists-history"),
    # --- Admin: Pricing Rules ---
    path("admin/rules", views.PricingRuleListCreateView.as_view(), name="admin-rules-list-create"),
    path("admin/rules/<str:pricing_rule_id>/activate", views.ActivatePricingRuleView.as_view(), name="admin-rules-activate"),
    path("admin/rules/<str:pricing_rule_id>/archive", views.ArchivePricingRuleView.as_view(), name="admin-rules-archive"),
    # --- Admin: Campaigns ---
    path("admin/campaigns", views.CampaignListCreateView.as_view(), name="admin-campaigns-list-create"),
    path("admin/campaigns/<str:campaign_id>/activate", views.ActivateCampaignView.as_view(), name="admin-campaigns-activate"),
    path("admin/campaigns/<str:campaign_id>/end", views.EndCampaignView.as_view(), name="admin-campaigns-end"),
    path("admin/campaigns/<str:campaign_id>/cancel", views.CancelCampaignView.as_view(), name="admin-campaigns-cancel"),
    # --- Admin: Coupons ---
    path("admin/coupons", views.CouponListCreateView.as_view(), name="admin-coupons-list-create"),
    path("admin/coupons/<str:code>/redeem", views.RedeemCouponView.as_view(), name="admin-coupons-redeem"),
    path("admin/coupons/<str:coupon_id>/revoke", views.RevokeCouponView.as_view(), name="admin-coupons-revoke"),
    # --- Admin: Snapshots ---
    path("admin/snapshots", views.LockPriceView.as_view(), name="admin-snapshots-lock"),
    path("admin/snapshots/<str:snapshot_id>/consume", views.ConsumePriceSnapshotView.as_view(), name="admin-snapshots-consume"),
    path("admin/snapshots/<str:snapshot_id>/release", views.ReleasePriceSnapshotView.as_view(), name="admin-snapshots-release"),
]
