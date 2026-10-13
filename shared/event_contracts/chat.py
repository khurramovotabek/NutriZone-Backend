"""
Chat's Domain Event Catalogue registration.

Imported once from `apps/chat/apps.py::ChatConfig.ready()`, matching
every prior module's `shared/event_contracts/*.py` pattern.
"""
from __future__ import annotations

from apps.chat.domain.events import (
    ConversationArchivedEvent,
    ConversationAssigned,
    ConversationClosedEvent,
    ConversationOpened,
    ConversationReopened,
    MessageDeleted,
    MessageDelivered,
    MessageEdited,
    MessageRead,
    MessageSent,
    ParticipantAdded,
    ParticipantRemoved,
)
from core.events import EventContract, registry

for _event_type, _payload_cls in (
    ("ConversationOpened", ConversationOpened),
    ("ParticipantAdded", ParticipantAdded),
    ("ParticipantRemoved", ParticipantRemoved),
    ("ConversationAssigned", ConversationAssigned),
    ("ConversationClosedEvent", ConversationClosedEvent),
    ("ConversationReopened", ConversationReopened),
    ("ConversationArchivedEvent", ConversationArchivedEvent),
    ("MessageSent", MessageSent),
    ("MessageEdited", MessageEdited),
    ("MessageDeleted", MessageDeleted),
    ("MessageDelivered", MessageDelivered),
    ("MessageRead", MessageRead),
):
    try:
        registry.register(EventContract(event_type=_event_type, emitted_by="chat", payload_schema=_payload_cls))
    except Exception:  # noqa: BLE001 - EventContractError on duplicate registration (e.g. Django autoreload re-importing this module)
        pass
