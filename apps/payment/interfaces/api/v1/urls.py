from __future__ import annotations

from django.urls import path

from apps.payment.interfaces.api.v1 import gateway_views, views

app_name = "payment"

urlpatterns = [
    path("", views.CreatePaymentView.as_view(), name="payment-create"),
    path("webhook", views.PaymentWebhookView.as_view(), name="payment-webhook"),
    # storefront
    path("methods", gateway_views.PaymentMethodsView.as_view(), name="payment-methods"),
    path("orders/<str:number>", gateway_views.OrderPaymentView.as_view(), name="order-payment"),
    path("orders/<str:number>/pay", gateway_views.OrderPaymentView.as_view(), name="order-pay"),
    # provider callbacks (set these in the merchant cabinets -- the dashboard shows the full URLs)
    path("payme", gateway_views.PaymeCallbackView.as_view(), name="payme-callback"),
    path("click/prepare", gateway_views.ClickCallbackView.as_view(action="prepare"), name="click-prepare"),
    path("click/complete", gateway_views.ClickCallbackView.as_view(action="complete"), name="click-complete"),
    path("uzum/<str:action>", gateway_views.UzumCallbackView.as_view(), name="uzum-callback"),
]
