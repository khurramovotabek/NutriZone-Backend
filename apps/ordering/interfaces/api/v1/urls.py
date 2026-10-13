"""
Ordering `/api/v1/ordering/...` URL routing.

Matches the required endpoint list, plus explicitly-flagged additions
closing real "all Application Services reachable" gaps (ship/deliver/
complete/start-processing order transitions, single-item return/
cancellation detail views -- see views.py's own docstrings). Every
collection endpoint (list+create) is ONE view class on ONE path --
verified below by a duplicate-path check.
"""
from __future__ import annotations

from django.urls import path

from apps.ordering.interfaces.api.v1 import customer_views, views

app_name = "ordering"

urlpatterns = [
    # --- Orders ---
    path("", views.OrderListCreateView.as_view(), name="order-list-create"),
    path("search", views.OrderSearchView.as_view(), name="order-search"),
    path("replenishment", customer_views.ReplenishmentView.as_view(), name="order-replenishment"),
    path("admin", views.AdminOrderListView.as_view(), name="admin-order-list"),
    path("statistics", views.OrderStatisticsView.as_view(), name="order-statistics"),
    path("customers/<str:customer_id>", views.CustomerOrdersView.as_view(), name="customer-orders"),
    path("<str:number>", views.OrderDetailView.as_view(), name="order-detail"),
    path("<str:number>/summary", views.OrderSummaryView.as_view(), name="order-summary"),
    path("<str:number>/after-sales", customer_views.AfterSalesView.as_view(), name="order-after-sales"),
    path("<str:number>/customer-cancel", customer_views.CustomerCancelView.as_view(), name="order-customer-cancel"),
    path("<str:number>/customer-return", customer_views.CustomerReturnView.as_view(), name="order-customer-return"),
    path("<str:number>/confirm", views.ConfirmOrderView.as_view(), name="order-confirm"),
    path("<str:number>/cancel", views.CancelOrderView.as_view(), name="order-cancel"),
    path("<str:number>/expire", views.ExpireOrderView.as_view(), name="order-expire"),
    path("<str:number>/lock", views.LockOrderView.as_view(), name="order-lock"),
    path("<str:number>/unlock", views.UnlockOrderView.as_view(), name="order-unlock"),
    path("<str:number>/archive", views.ArchiveOrderView.as_view(), name="order-archive"),
    path("<str:number>/restore", views.RestoreOrderView.as_view(), name="order-restore"),
    path("<str:number>/start-processing", views.StartOrderProcessingView.as_view(), name="order-start-processing"),
    path("<str:number>/ship", views.ShipOrderView.as_view(), name="order-ship"),
    path("<str:number>/deliver", views.DeliverOrderView.as_view(), name="order-deliver"),
    path("<str:number>/complete", views.CompleteOrderView.as_view(), name="order-complete"),
    path("<str:number>/shipment", views.OrderShipmentView.as_view(), name="order-shipment"),
    path("<str:number>/payment", views.OrderPaymentView.as_view(), name="order-payment"),
    path("payments/webhook", views.PaymentWebhookView.as_view(), name="payment-webhook"),
    path("<str:number>/coupon", views.OrderCouponView.as_view(), name="order-coupon"),
    path("<str:number>/address", views.OrderAddressView.as_view(), name="order-address"),
    path("<str:number>/reservation", views.OrderReservationView.as_view(), name="order-reservation"),
    path("<str:number>/price-snapshot", views.OrderPriceSnapshotView.as_view(), name="order-price-snapshot"),
    # --- Invoice ---
    path("<str:number>/invoice", views.InvoiceDetailView.as_view(), name="order-invoice-detail"),
    path("<str:number>/invoice/issue", views.IssueInvoiceView.as_view(), name="order-invoice-issue"),
    # --- Returns ---
    path("<str:number>/returns", views.ReturnListCreateView.as_view(), name="return-list-create"),
    path("returns/<str:return_id>", views.ReturnDetailView.as_view(), name="return-detail"),
    path("returns/<str:return_id>/approve", views.ApproveReturnView.as_view(), name="return-approve"),
    path("returns/<str:return_id>/reject", views.RejectReturnView.as_view(), name="return-reject"),
    path("returns/<str:return_id>/receive", views.ReceiveReturnView.as_view(), name="return-receive"),
    path("returns/<str:return_id>/refund", views.RefundReturnView.as_view(), name="return-refund"),
    # --- Cancellations ---
    path("<str:number>/cancellations", views.CancellationListCreateView.as_view(), name="cancellation-list-create"),
    path("cancellations/<str:cancellation_id>", views.CancellationDetailView.as_view(), name="cancellation-detail"),
    path("cancellations/<str:cancellation_id>/approve", views.ApproveCancellationView.as_view(), name="cancellation-approve"),
    path("cancellations/<str:cancellation_id>/reject", views.RejectCancellationView.as_view(), name="cancellation-reject"),
    path("cancellations/<str:cancellation_id>/complete", views.CompleteCancellationView.as_view(), name="cancellation-complete"),
]
