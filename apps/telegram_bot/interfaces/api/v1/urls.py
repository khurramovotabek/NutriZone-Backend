from __future__ import annotations

from django.urls import path

from apps.telegram_bot.interfaces import webapp
from apps.telegram_bot.interfaces.api.v1 import views

urlpatterns = [
    path("webhook", views.telegram_webhook_view, name="telegram-webhook"),
    path("orders-webhook", views.telegram_orders_webhook_view, name="telegram-orders-webhook"),
    path("analytics-webhook", views.telegram_analytics_webhook_view, name="telegram-analytics-webhook"),
    path("webapp/session", webapp.TelegramWebAppSessionView.as_view(), name="telegram-webapp-session"),
]
