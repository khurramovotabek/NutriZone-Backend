"""
Notifications `/api/v1/notifications/...` URL routing.
"""
from __future__ import annotations

from django.urls import path

from apps.notifications.interfaces.api.v1 import inbox_views, views

app_name = "notifications"

urlpatterns = [
    path("", views.NotificationListCreateView.as_view(), name="notification-list-create"),
    path("inbox", inbox_views.InboxView.as_view(), name="inbox"),
    path("news", inbox_views.NewsSubscriptionInfoView.as_view(), name="news-subscription-info"),
    path("inbox/unread-count", inbox_views.InboxUnreadCountView.as_view(), name="inbox-unread-count"),
    path("inbox/read", inbox_views.InboxReadView.as_view(), name="inbox-read"),
    path("statistics", views.NotificationStatisticsView.as_view(), name="notification-statistics"),
    path("preferences", views.NotificationPreferenceView.as_view(), name="notification-preference"),
    path("preferences/disable", views.DisablePreferenceView.as_view(), name="notification-preference-disable"),
    path("preferences/enable", views.EnablePreferenceView.as_view(), name="notification-preference-enable"),
    path("<str:notification_id>", views.NotificationDetailView.as_view(), name="notification-detail"),
    path("<str:notification_id>/seen", views.MarkNotificationSeenView.as_view(), name="notification-mark-seen"),
    path("<str:notification_id>/read", views.MarkNotificationReadView.as_view(), name="notification-mark-read"),
    path("<str:notification_id>/cancel", views.CancelNotificationView.as_view(), name="notification-cancel"),
]
