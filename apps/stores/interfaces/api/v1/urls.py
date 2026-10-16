from __future__ import annotations

from django.urls import path

from apps.stores.interfaces.api.v1 import order_views, pos_views, transfer_views, views

app_name = "stores"

urlpatterns = [
    path("stores", views.StoreListView.as_view(), name="store-list"),
    path("stores/pickup-options", order_views.PickupOptionsView.as_view(), name="store-pickup-options"),
    path("stores/<slug:slug>", views.StoreDetailView.as_view(), name="store-detail"),
    path("stores/<slug:slug>/rating", views.StoreRatingView.as_view(), name="store-rating"),
    path("my-store", views.MyStoreView.as_view(), name="my-store"),
    path("my-store/transfers", transfer_views.MyStoreTransfersView.as_view(), name="my-store-transfers"),
    path("my-store/transfers/lookup", transfer_views.MyStoreTransferLookupView.as_view(), name="my-store-transfer-lookup"),
    path("my-store/transfers/<str:transfer_id>", transfer_views.MyStoreTransferDetailView.as_view(), name="my-store-transfer"),
    path("my-store/transfers/<str:transfer_id>/receive", transfer_views.MyStoreTransferReceiveView.as_view(), name="my-store-transfer-receive"),
    path("my-store/transfers/<str:transfer_id>/document.xlsx", transfer_views.MyStoreTransferDocumentView.as_view(), name="my-store-transfer-document"),
    path("my-store/orders", order_views.MyStoreOrdersView.as_view(), name="my-store-orders"),
    path("my-store/report", order_views.MyStoreReportView.as_view(), name="my-store-report"),
    path("my-store/receipts", order_views.MyStoreReceiptsView.as_view(), name="my-store-receipts"),
    path("my-store/orders/<str:number>/action", order_views.MyStoreOrderActionView.as_view(), name="my-store-order-action"),
    path("my-store/logo", views.MyStoreLogoUploadView.as_view(), name="my-store-logo"),
    path("my-store/cover-image", views.MyStoreCoverUploadView.as_view(), name="my-store-cover"),
    path("my-store/media", views.MyStoreMediaView.as_view(), name="my-store-media"),
    path("my-store/media/<int:media_id>", views.MyStoreMediaDetailView.as_view(), name="my-store-media-detail"),
    path("my-store/products", views.MyStoreProductsView.as_view(), name="my-store-products"),
    path("my-store/products/<int:entry_id>", views.MyStoreProductDetailView.as_view(), name="my-store-product-detail"),
    # Store POS terminal
    path("my-store/pos/config", pos_views.PosConfigView.as_view(), name="my-store-pos-config"),
    path("my-store/pos/catalog", pos_views.PosCatalogView.as_view(), name="my-store-pos-catalog"),
    path("my-store/pos/sales", pos_views.PosHistoryView.as_view(), name="my-store-pos-history"),
    path("my-store/pos/customers", pos_views.PosCustomerSearchView.as_view(), name="my-store-pos-customers"),
    path("my-store/pos/session", pos_views.PosSessionView.as_view(), name="my-store-pos-session"),
    path("my-store/pos/session/open", pos_views.PosSessionOpenView.as_view(), name="my-store-pos-session-open"),
    path("my-store/pos/session/close", pos_views.PosSessionCloseView.as_view(), name="my-store-pos-session-close"),
    path("my-store/pos/sessions", pos_views.PosSessionListView.as_view(), name="my-store-pos-sessions"),
    path("my-store/pos/analytics", pos_views.PosAnalyticsView.as_view(), name="my-store-pos-analytics"),
    path("my-store/pos/stock", pos_views.PosStockView.as_view(), name="my-store-pos-stock"),
    path("my-store/pos/top", pos_views.PosTopView.as_view(), name="my-store-pos-top"),
    path("my-store/pos/cashier", pos_views.PosCashierSwitchView.as_view(), name="my-store-pos-cashier"),
    path("my-store/pos/sales/current", pos_views.PosCurrentSaleView.as_view(), name="my-store-pos-current"),
    path("my-store/pos/sales/parked", pos_views.PosParkedView.as_view(), name="my-store-pos-parked"),
    path("my-store/pos/sales/<str:sale_id>", pos_views.PosSaleView.as_view(), name="my-store-pos-sale"),
    path("my-store/pos/sales/<str:sale_id>/park", pos_views.PosSaleParkView.as_view(), name="my-store-pos-park"),
    path("my-store/pos/sales/<str:sale_id>/resume", pos_views.PosSaleResumeView.as_view(), name="my-store-pos-resume"),
    path("my-store/pos/sales/<str:sale_id>/items", pos_views.PosSaleItemsView.as_view(), name="my-store-pos-items"),
    path("my-store/pos/sales/<str:sale_id>/items/<str:line_id>", pos_views.PosSaleItemView.as_view(), name="my-store-pos-item"),
    path("my-store/pos/sales/<str:sale_id>/customer", pos_views.PosSaleCustomerView.as_view(), name="my-store-pos-customer"),
    path("my-store/pos/sales/<str:sale_id>/complete", pos_views.PosSaleCompleteView.as_view(), name="my-store-pos-complete"),
    path("my-store/pos/sales/<str:sale_id>/void", pos_views.PosSaleVoidView.as_view(), name="my-store-pos-void"),
    path("my-store/pos/sales/<str:sale_id>/refund", pos_views.PosSaleRefundView.as_view(), name="my-store-pos-refund"),
]
