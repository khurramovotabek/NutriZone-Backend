from __future__ import annotations

from django.urls import path

from apps.assistant.interfaces import views

app_name = "assistant"

urlpatterns = [
    path("status", views.status_view, name="status"),
    path("chat", views.chat_view, name="chat"),
    path("tts", views.tts_view, name="tts"),
    path("guides", views.guides_view, name="guides"),
    path("guides/<slug:slug>", views.guide_view, name="guide"),
    path("conversations/<str:conversation_id>", views.conversation_view, name="conversation"),
    path("conversations/<str:conversation_id>/feedback", views.feedback_view, name="feedback"),
]
