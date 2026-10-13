"""
A new chat message -> the other side's notification bell (and badge), when they aren't online to see it live.

Hooked on MessageModel post_save (the chat outbox relay isn't scheduled, so its MessageSent handler can't be relied
on). At most one notification per conversation per recipient every 15 minutes -- a burst of messages is one alert,
not ten. The link opens the right inbox: the customer's Support chat, or the store owner's Customer inquiries.
"""
from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger("nutrizone.app")
BUCKET_MINUTES = 15


@receiver(post_save, sender="chat.MessageModel", dispatch_uid="chat.inbox_notify")
def _on_message(sender, instance, created: bool, **kwargs) -> None:
    if not created or instance.message_type == "system":
        return
    try:
        _notify(instance)
    except Exception:  # noqa: BLE001 - a notification never breaks sending a message
        logger.exception("chat: inbox notification failed for message %s", instance.pk)


def _notify(message) -> None:
    from django.utils import timezone

    from apps.chat.infrastructure import presence
    from apps.chat.infrastructure.models import ConversationModel, ParticipantModel
    from apps.identity.infrastructure.models import User
    from apps.notifications.infrastructure.notify import notify

    conversation = ConversationModel.objects.filter(id=message.conversation_id).first()
    if conversation is None:
        return
    recipients = list(ParticipantModel.objects.filter(conversation_id=message.conversation_id, removed_at__isnull=True).exclude(user_id=message.sender_id))
    if not recipients:
        return
    sender = User.objects.filter(id=message.sender_id).only("full_name", "phone_number").first()
    store_name = None
    if conversation.store_id:
        from apps.stores.infrastructure.models import Store

        store_name = Store.objects.filter(id=conversation.store_id).values_list("name", flat=True).first()
    preview = (message.content or "").strip()[:120] if message.message_type == "text" else {"sticker": "🎨 Stiker", "attachment": "📎 Fayl", "card": "🛍️ Mahsulot / buyurtma"}.get(message.message_type, "Xabar")
    bucket = timezone.now().strftime("%Y%m%d%H") + str(timezone.now().minute // BUCKET_MINUTES)
    for p in recipients:
        if not User.objects.filter(id=p.user_id).exists() or presence.is_online(p.user_id):
            continue  # staff operators have no customer account; an online user sees the message live
        if p.role == "customer":
            who = store_name or "NutriZone Support"
            link = f"/account/chat?conversation={conversation.id}"
        else:  # the store owner answering customer inquiries
            who = (sender.full_name or sender.phone_number) if sender else "Mijoz"
            link = f"/profile/store/inquiries?conversation={conversation.id}"
        notify(p.user_id, "chat_message", {"sender": who, "preview": preview}, link=link,
               dedupe_key=f"chat:{conversation.id}:{p.user_id}:{bucket}", telegram=False)
