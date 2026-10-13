"""
Identity `/api/v1/identity/...` URL routing.

Included from `config/urls/v1.py` under the `identity/` prefix (REST
API Blueprint §3: `/api/{version}/{module}/{resource}`). Kept RESTful
per this phase's explicit instruction -- resources are nouns
(`sessions/{id}`), actions are POST-verbed sub-paths only where no
plain CRUD verb fits (`auth/request-otp`, not a bare `/auth`).
"""
from __future__ import annotations

from django.urls import path

from apps.identity.interfaces.api.v1 import views

app_name = "identity"

urlpatterns = [
    # --- Authentication ---
    path("auth/request-otp", views.RequestOTPView.as_view(), name="auth-request-otp"),
    path("auth/request-telegram-code", views.RequestTelegramLoginCodeView.as_view(), name="auth-request-telegram-code"),
    path("auth/telegram/session", views.CreateTelegramAuthSessionView.as_view(), name="auth-telegram-session-create"),
    path("auth/telegram/session/<str:session_id>", views.GetTelegramAuthSessionStatusView.as_view(), name="auth-telegram-session-status"),
    path("auth/verify-otp", views.VerifyOTPView.as_view(), name="auth-verify-otp"),
    path("auth/verify-code", views.VerifyCodeOnlyView.as_view(), name="auth-verify-code"),
    path("auth/refresh", views.RefreshTokenView.as_view(), name="auth-refresh"),
    path("auth/logout", views.LogoutView.as_view(), name="auth-logout"),
    path("auth/logout-all", views.LogoutAllView.as_view(), name="auth-logout-all"),
    path("auth/ws-ticket", views.WsTicketView.as_view(), name="auth-ws-ticket"),
    # --- Profile ---
    path("users/me", views.MeView.as_view(), name="users-me"),
    path("users/me/avatar", views.AvatarUploadView.as_view(), name="users-me-avatar"),
    path("users/me/sessions", views.SessionsListView.as_view(), name="users-me-sessions"),
    path("users/me/sessions/<str:session_id>", views.SessionRevokeView.as_view(), name="users-me-sessions-revoke"),
    # --- Admin ---
    path("admin/users", views.AdminUserListView.as_view(), name="admin-users-list"),
    path("admin/users/statistics", views.UserStatisticsView.as_view(), name="admin-users-statistics"),
    path("admin/users/<str:user_id>", views.AdminUserDetailView.as_view(), name="admin-users-detail"),
    path("admin/users/<str:user_id>/status", views.AdminUpdateUserStatusView.as_view(), name="admin-users-status"),
    path("admin/users/<str:user_id>/roles", views.AdminUpdateUserRolesView.as_view(), name="admin-users-roles"),
]
