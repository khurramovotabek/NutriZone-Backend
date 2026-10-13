"""
POS `/api/v1/pos/...` URL routing.

`search` added for the POS Search module -- a distinct top-level
segment, zero collision risk with the `sales/...` routes above it.

`pricing` added for POS Phase 11 -- exposes Phase 7's
`ResolveLineItemPrice`, previously Application-layer-only.
"""
from __future__ import annotations

from django.urls import path

from apps.pos.interfaces.api.v1 import views

app_name = "pos"

urlpatterns = [
    path("sales", views.SaleListCreateView.as_view(), name="sale-list-create"),
    path("sales/<str:sale_id>", views.SaleDetailView.as_view(), name="sale-detail"),
    path("sales/<str:sale_id>/line-items", views.AddLineItemView.as_view(), name="sale-add-line-item"),
    path("sales/<str:sale_id>/line-items/<str:line_item_id>", views.RemoveLineItemView.as_view(), name="sale-remove-line-item"),
    path("sales/<str:sale_id>/complete", views.CompleteSaleView.as_view(), name="sale-complete"),
    path("sales/<str:sale_id>/void", views.VoidSaleView.as_view(), name="sale-void"),
    path("search", views.SearchView.as_view(), name="search"),
    path("pricing", views.PriceResolutionView.as_view(), name="pricing"),
]
