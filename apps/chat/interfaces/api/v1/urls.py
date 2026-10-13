"""
Chat `/api/v1/chat/...` HTTP URL routing.
"""
from __future__ import annotations

from django.urls import path

from apps.chat.interfaces.api.v1 import views

app_name = "chat"

urlpatterns = [
    path("conversations", views.ConversationListCreateView.as_view(), name="conversation-list-create"),
    path("conversations/store/<str:store_id>", views.OpenStoreConversationView.as_view(), name="conversation-open-store"),
    path("statistics", views.ChatStatisticsView.as_view(), name="chat-statistics"),
    path("unread-count", views.UnreadCountView.as_view(), name="chat-unread-count"),
    path("conversations/<str:conversation_id>", views.ConversationDetailView.as_view(), name="conversation-detail"),
    path("conversations/<str:conversation_id>/messages", views.ConversationMessageListView.as_view(), name="conversation-message-list"),
    path("conversations/<str:conversation_id>/customer-profile", views.CustomerProfileView.as_view(), name="conversation-customer-profile"),
    path("conversations/<str:conversation_id>/rating", views.ConversationRatingView.as_view(), name="conversation-rating"),
    path("conversations/<str:conversation_id>/attachments", views.ConversationAttachmentUploadView.as_view(), name="conversation-attachment-upload"),
    path("conversations/<str:conversation_id>/participants", views.AddParticipantView.as_view(), name="conversation-add-participant"),
    path("conversations/<str:conversation_id>/participants/<str:user_id>", views.RemoveParticipantView.as_view(), name="conversation-remove-participant"),
    path("conversations/<str:conversation_id>/assign", views.AssignOperatorView.as_view(), name="conversation-assign"),
    path("conversations/<str:conversation_id>/close", views.CloseConversationView.as_view(), name="conversation-close"),
    path("conversations/<str:conversation_id>/reopen", views.ReopenConversationView.as_view(), name="conversation-reopen"),
    path("conversations/<str:conversation_id>/archive", views.ArchiveConversationView.as_view(), name="conversation-archive"),
]
