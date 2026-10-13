from __future__ import annotations

from django.urls import path

from apps.loyalty.interfaces.api.v1 import views

app_name = "loyalty"

urlpatterns = [
    path("tiers", views.LoyaltyTierListView.as_view(), name="tier-list"),
    path("me", views.MyLoyaltyView.as_view(), name="me"),
    path("me/rate", views.MyLoyaltyRateView.as_view(), name="my-rate"),
    path("me/transactions", views.MyWalletTransactionsView.as_view(), name="my-transactions"),
    path("referral/claim", views.ReferralClaimView.as_view(), name="referral-claim"),
]
