from __future__ import annotations

from django.urls import path

from apps.support.interfaces.api.v1.views import CancelProductRequestView, MyProductRequestsView

urlpatterns = [
    path("product-requests", MyProductRequestsView.as_view(), name="product-requests"),
    path("product-requests/<uuid:request_id>/cancel", CancelProductRequestView.as_view(), name="product-request-cancel"),
]
