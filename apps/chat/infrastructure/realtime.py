"""
Real-time fan-out of a sent chat message, shared by every send path (the customer / store REST API and the
dashboard's Chat markazi): the open thread's group gets the message itself, every other active participant's
personal inbox group a "conversation.updated" pointer so their list refreshes live. Best effort: the message is
already persisted, so a channel-layer hiccup never fails a send (the next poll / reconnect still sees it).
"""
from __future__ import annotations

import logging

logger = logging.getLogger("nutrizone.app")


def attachment_url(url: str | None, absolute: bool = True) -> str | None:
    """
    A stored attachment URL rebuilt on today's hosts. Uploads were saved as absolute URLs on whatever public host the
    backend had at the time (often a temporary tunnel), so old photos broke as soon as it changed. The path is what
    identifies the file: /media/... is served by this backend (current PUBLIC_BASE_URL, or relative for the
    dashboard on the same host), /stickers/... by the storefront (current FRONTEND_URL).
    """
    if not url:
        return url
    from urllib.parse import urlparse

    from django.conf import settings

    path = urlparse(url).path or ""
    if path.startswith(settings.MEDIA_URL):
        base = (getattr(settings, "PUBLIC_BASE_URL", None) or "").rstrip("/")
        return f"{base}{path}" if absolute and base else path
    if path.startswith("/stickers/"):
        base = (getattr(settings, "FRONTEND_URL", None) or "").rstrip("/")
        return f"{base}{path}" if base else url
    return url


def message_payload(message) -> dict:
    """The wire shape of a domain `Message` (REST responses, socket pushes, the dashboard)."""
    return {
        "id": str(message.id), "conversation_id": str(message.conversation_id), "sender_id": str(message.sender_id),
        "message_type": message.message_type.value, "content": message.content.value if message.content else None,
        "attachment_type": message.attachment.attachment_type.value if message.attachment else None,
        "attachment_url": attachment_url(message.attachment.url) if message.attachment else None,
        "attachment_filename": message.attachment.filename if message.attachment else None,
        "attachment_size_bytes": message.attachment.size_bytes if message.attachment else None,
        "reply_to_message_id": str(message.reply_to_message_id) if message.reply_to_message_id else None,
        "status": message.status.value, "created_at": message.created_at.isoformat() if message.created_at else None,
        "read_at": message.read_at.isoformat() if message.read_at else None,  # read receipts (✓✓), set via the socket's "read" command
        "card": _card(message),  # a product / order card for CARD messages (automation.card_payload)
    }


def _card(message):
    if message.message_type.value != "card":
        return None
    from apps.chat.infrastructure.automation import card_payload

    return card_payload(message.content.value if message.content else None)


def push_message(conversation_id, payload: dict, sender_id, recipient_ids) -> None:
    """Push `payload` to the conversation's group and a list-refresh pointer to each recipient's inbox."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(f"chat.conversation.{conversation_id}", {"type": "chat.message.broadcast", "payload": {"type": "message.created", "message": payload}})
        for user_id in recipient_ids:
            if str(user_id) != str(sender_id):
                async_to_sync(layer.group_send)(f"chat.inbox.{user_id}", {"type": "chat.inbox.broadcast", "payload": {"type": "conversation.updated", "conversation_id": str(conversation_id)}})
    except Exception:  # noqa: BLE001 - best effort, see module docstring
        logger.warning("chat realtime push failed for %s", conversation_id, exc_info=True)
