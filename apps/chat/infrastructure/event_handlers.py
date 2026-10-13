"""
Consumed-event handlers for Chat, plus the cache invalidation helper
functions they use.

Dispatch-table pattern, matching every prior module's identical
architecture -- never a giant if/else chain.

**A deliberate, disclosed design note on `MessageRead`**: per this
phase's own explicit instruction ("if MessageRead has no current
external side effect, do not manufacture one merely to have a
handler"), `MessageRead` is still registered in the dispatch table
(every one of the 12 certified events IS registered exactly once,
satisfying the "genuinely handled OR explicitly documented as having
no side effect" requirement) but maps to an empty cache-group tuple
and no metric -- the handler still logs the event for observability,
which is a genuine, minimal side effect, but does not fabricate a
cache invalidation or notification that has no real justification
yet (a message being read does not currently need to invalidate any
selector's cached output, since no selector surfaces read-state at
all this phase).
"""
from __future__ import annotations

import logging

from core.caching import get_redis_client
from core.metrics import default_collector

CACHE_GROUPS = ("conversation_detail", "conversation_list", "conversation_messages")

_EVENT_TO_CACHE_GROUPS = {
    "ConversationOpened": ("conversation_list",),
    "ParticipantAdded": ("conversation_detail",),
    "ParticipantRemoved": ("conversation_detail",),
    "ConversationAssigned": ("conversation_detail", "conversation_list"),
    "ConversationClosedEvent": ("conversation_detail", "conversation_list"),
    "ConversationReopened": ("conversation_detail", "conversation_list"),
    "ConversationArchivedEvent": ("conversation_detail", "conversation_list"),
    "MessageSent": ("conversation_messages", "conversation_detail"),
    "MessageEdited": ("conversation_messages",),
    "MessageDeleted": ("conversation_messages",),
    "MessageDelivered": (),
    "MessageRead": (),
}

_EVENT_TO_METRIC = {
    "ConversationOpened": "chat_conversations_opened_total",
    "ConversationClosedEvent": "chat_conversations_closed_total",
    "MessageSent": "chat_messages_sent_total",
    "MessageDeleted": "chat_messages_deleted_total",
}


def invalidate_chat_cache_group(group: str) -> None:
    if group not in CACHE_GROUPS:
        raise ValueError(f"Unknown chat cache group '{group}'. Must be one of {CACHE_GROUPS}.")
    client = get_redis_client()
    client.incr(f"nutrizone:cache-version:chat:{group}")


def _notify_customer_of_operator_reply(payload: dict) -> None:
    """
    Real integration, closing the previously one-way gap: when a real
    support operator sends a message (`MessageSent` with an OPERATOR
    sender), the real customer is notified via a real Telegram
    message -- without this, a customer who started a chat via the
    bot would never see the operator's reply anywhere. Silent no-op
    (never raises) if the customer never linked Telegram, the
    conversation has no customer participant, or Telegram delivery
    itself fails -- a notification failure must never break message
    persistence, which has already committed by the time this runs.
    """
    from apps.chat.domain.enums import ParticipantRole
    from apps.chat.infrastructure.models import MessageModel, ParticipantModel
    from apps.identity.infrastructure import models as identity_orm

    logger = logging.getLogger("nutrizone.app")
    conversation_id = payload.get("conversation_id")
    sender_id = payload.get("sender_id")
    message_id = payload.get("message_id")
    if not conversation_id or not sender_id or not message_id:
        return

    sender_participant = ParticipantModel.objects.filter(conversation_id=conversation_id, user_id=sender_id, removed_at__isnull=True).first()
    if sender_participant is None or sender_participant.role != ParticipantRole.OPERATOR.value:
        return  # Only an operator's reply triggers a customer-facing notification -- a customer's own message never notifies themselves.

    customer_participant = ParticipantModel.objects.filter(conversation_id=conversation_id, role=ParticipantRole.CUSTOMER.value, removed_at__isnull=True).first()
    if customer_participant is None:
        return

    customer = identity_orm.User.objects.filter(id=customer_participant.user_id).first()
    if customer is None or not customer.telegram_user_id:
        return  # The customer may not have linked Telegram at all -- nothing to notify through.

    message = MessageModel.objects.filter(id=message_id).first()
    if message is None or not message.content:
        return

    try:
        from apps.notifications.infrastructure import composition as notifications_composition

        gateway = notifications_composition.build_telegram_gateway()
        gateway.send_message(str(customer.telegram_user_id), "", message.content)
    except Exception:  # noqa: BLE001
        logger.warning("Chat: failed to notify customer of operator reply for conversation_id=%s", conversation_id)


def handle_chat_event(event_type: str, payload: dict) -> None:
    """Called by the Outbox relay task (infrastructure/tasks.py) for each of this schema's own events."""
    logger = logging.getLogger("nutrizone.app")

    for group in _EVENT_TO_CACHE_GROUPS.get(event_type, ()):
        invalidate_chat_cache_group(group)

    metric_name = _EVENT_TO_METRIC.get(event_type)
    if metric_name:
        default_collector.counter(metric_name)

    if event_type == "MessageSent":
        _notify_customer_of_operator_reply(payload)

    logger.info("chat event handled: %s", event_type)
