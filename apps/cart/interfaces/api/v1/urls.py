"""
Cart `/api/v1/cart/...` URL routing.

Matches the required endpoint list exactly. Every collection endpoint
(list+create) is ONE view class on ONE path -- verified below by a
duplicate-path check, matching every prior module's approach.
"""
from __future__ import annotations

from django.urls import path

from apps.cart.interfaces.api.v1 import views

app_name = "cart"

urlpatterns = [
    # --- Cart ---
    path("", views.CartListCreateView.as_view(), name="cart-list-create"),
    path("search", views.CartSearchView.as_view(), name="cart-search"),
    path("<str:code>", views.CartDetailView.as_view(), name="cart-detail"),
    # --- Items ---
    path("<str:code>/items", views.CartItemListCreateView.as_view(), name="cart-items-create"),
    path("<str:code>/items/<str:line_id>", views.CartItemDetailView.as_view(), name="cart-items-detail"),
    path("<str:code>/clear", views.ClearCartView.as_view(), name="cart-clear"),
    # --- Coupon ---
    path("<str:code>/coupon", views.CouponReferenceView.as_view(), name="cart-coupon"),
    path("<str:code>/checkout-coupon", views.CheckoutCouponView.as_view(), name="cart-checkout-coupon"),
    # --- Reservation ---
    path("<str:code>/reservation", views.ReservationReferenceView.as_view(), name="cart-reservation"),
    # --- Price Snapshot ---
    path("<str:code>/snapshot", views.PriceSnapshotReferenceView.as_view(), name="cart-snapshot"),
    path("<str:code>/items/<str:item_id>/price", views.PriceCartItemView.as_view(), name="cart-item-price"),
    # --- Merge ---
    path("<str:code>/merge", views.MergeCartView.as_view(), name="cart-merge"),
    # --- Lifecycle ---
    path("<str:code>/lock", views.LockCartView.as_view(), name="cart-lock"),
    path("<str:code>/unlock", views.UnlockCartView.as_view(), name="cart-unlock"),
    path("<str:code>/convert", views.ConvertCartView.as_view(), name="cart-convert"),
    # --- Validation ---
    path("<str:code>/validate", views.ValidateCartView.as_view(), name="cart-validate"),
    path("<str:code>/checkout-preview", views.CheckoutPreviewView.as_view(), name="cart-checkout-preview"),
    path("<str:code>/checkout", views.CheckoutCartView.as_view(), name="cart-checkout"),
    # --- Audit ---
    path("<str:code>/audit", views.CartAuditView.as_view(), name="cart-audit"),
    # --- Snapshot History ---
    path("<str:code>/snapshots", views.CartSnapshotHistoryView.as_view(), name="cart-snapshot-history"),
]
