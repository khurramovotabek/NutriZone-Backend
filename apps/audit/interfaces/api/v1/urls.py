"""
Audit `/api/v1/internal/audit/...` URL routing. Matches REST API
Blueprint §13's exact confirmed path `/internal/audit/activity`.
"""
from __future__ import annotations

from django.urls import path

from apps.audit.interfaces.api.v1 import views

app_name = "audit"

urlpatterns = [
    path("internal/audit/activity", views.ActivityTimelineListView.as_view(), name="activity-timeline-list"),
]
