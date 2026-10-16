"""
`/api/v1/` namespace root.

Composes each bounded-context app's `interfaces/api/v1/urls.py` under
its module path (REST API Blueprint §3: `/api/{version}/{module}/...`).
No business app has endpoints yet (foundation phase) -- this file is
the stable include point every module's URLs are wired into once built,
so a new module is added here as a one-line `path(...)` addition, never
by editing another module's block.
"""
from __future__ import annotations

from django.urls import include, path

from apps.pos.interfaces.api.v1.receipt_views import MyReceiptsView, PublicReceiptView

app_name = "v1"

urlpatterns: list = [
    path("identity/", include("apps.identity.interfaces.api.v1.urls")),
    path("", include("apps.products.interfaces.api.v1.urls")),
    path("geo/", include("apps.geo.interfaces.api.v1.urls")),
    path("inventory/", include("apps.inventory.interfaces.api.v1.urls")),
    path("pricing/", include("apps.pricing.interfaces.api.v1.urls")),
    path("cart/", include("apps.cart.interfaces.api.v1.urls")),
    path("orders/", include("apps.ordering.interfaces.api.v1.urls")),
    path("telegram/", include("apps.telegram_bot.interfaces.api.v1.urls")),
    path("payments/", include("apps.payment.interfaces.api.v1.urls")),
    path("reviews/", include("apps.reviews.interfaces.api.v1.urls")),
    path("content/", include("apps.content.interfaces.api.v1.urls")),
    path("chat/", include("apps.chat.interfaces.api.v1.urls")),
    path("notifications/", include("apps.notifications.interfaces.api.v1.urls")),
    path("loyalty/", include("apps.loyalty.interfaces.api.v1.urls")),
    path("", include("apps.stores.interfaces.api.v1.urls")),
    path("pos/", include("apps.pos.interfaces.api.v1.urls")),
    path("receipts/mine", MyReceiptsView.as_view(), name="my-receipts"),
    path("receipts/<str:token>", PublicReceiptView.as_view(), name="public-receipt"),
    path("", include("apps.platform.interfaces.api.v1.urls")),
    path("", include("apps.audit.interfaces.api.v1.urls")),
    path("assistant/", include("apps.assistant.interfaces.urls")),
    # path("catalog/", include("apps.catalog.interfaces.api.v1.urls")),
    # ... one entry per module, added when that module ships its API layer
    # (Universal Module Implementation Contract §1, step 14).
]
