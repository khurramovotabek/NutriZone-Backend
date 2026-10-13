from __future__ import annotations

from django.urls import path

from apps.assistant.interfaces import views

app_name = "assistant"

urlpatterns = [
    path("status", views.status_view, name="status"),
    path("chat", views.chat_view, name="chat"),
    path("conversations/<str:conversation_id>", views.conversation_view, name="conversation"),
    path("conversations/<str:conversation_id>/feedback", views.feedback_view, name="feedback"),
]
