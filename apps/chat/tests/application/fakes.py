"""
Fake implementations of Chat's two Application-layer Ports.
"""
from __future__ import annotations


class FakeConversationRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, conversation_id):
        return self.by_id.get(conversation_id)

    def save(self, conversation):
        self.by_id[conversation.id] = conversation
        return conversation

    def list_for_user(self, user_id, status, page, page_size):
        results = [c for c in self.by_id.values() if any(p.user_id == user_id and p.is_active for p in c.participants.values())]
        if status:
            results = [c for c in results if c.status.value == status]
        return results[(page - 1) * page_size : page * page_size], len(results)

    def list_unassigned(self, conversation_type, page, page_size):
        results = [c for c in self.by_id.values() if c.assigned_operator_id is None and c.status.value == "open"]
        if conversation_type:
            results = [c for c in results if c.conversation_type.value == conversation_type]
        return results[(page - 1) * page_size : page * page_size], len(results)


class FakeMessageRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, message_id):
        return self.by_id.get(message_id)

    def save(self, message):
        self.by_id[message.id] = message
        return message

    def list_for_conversation(self, conversation_id, page, page_size):
        results = [m for m in self.by_id.values() if m.conversation_id == conversation_id]
        return results[(page - 1) * page_size : page * page_size], len(results)

    def list_unread_from_others(self, conversation_id, reader_id, limit):
        results = [m for m in self.by_id.values() if m.conversation_id == conversation_id and m.sender_id != reader_id and m.read_at is None]
        return sorted(results, key=lambda m: m.created_at)[:limit]
