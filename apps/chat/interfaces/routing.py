"""
Chat WebSocket routing.

Matches the exact composition point `config/asgi.py` already
documents in its own comment
(`apps.chat.interfaces.routing.websocket_urlpatterns`) -- this
module was built to satisfy that pre-existing platform integration
point, not to invent a new one.
"""
from __future__ import annotations

from django.urls import re_path

from apps.chat.interfaces.consumers import ChatConsumer, ChatInboxConsumer

websocket_urlpatterns = [
    # Must come before the conversation-id pattern below -- "inbox" would
    # otherwise be captured as a (36-char-matching-failing, so harmless,
    # but still wrong-intent) conversation_id attempt.
    re_path(r"^ws/chat/inbox/$", ChatInboxConsumer.as_asgi()),
    re_path(r"^ws/chat/(?P<conversation_id>[0-9a-fA-F-]{36})/$", ChatConsumer.as_asgi()),
]
