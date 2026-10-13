"""
Chat WebSocket consumer.

Receive-only from the client's perspective: a message is still sent
over the existing, real HTTP `POST .../messages` endpoint (which
already has request validation, error handling, and retry semantics a
raw socket send would have to reinvent) -- this socket's job is to
push that same message (and any other participant's) back out live,
via `chat_message_broadcast` below, which `views.py` now actually
calls after a successful send. Every WS-side *mutation* command below
therefore still correctly reports `unsupported_operation`: building a
second, divergent send path over WS was never the actual gap (no
Application Service was ever missing for *sending* -- `SendMessage`
has existed and worked over HTTP since Phase 03B); the real, now-closed
gap was that nothing ever called `group_send` to push a sent message
back out to other connected participants in real time.

Presence: `mark_connected`/`mark_disconnected` (see
`infrastructure/presence.py`) make "online" mean exactly "holds an
open, authenticated socket right now" -- no separate heartbeat, no
fabricated status.
"""
from __future__ import annotations

import uuid

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.chat.infrastructure import composition, presence
from common.permissions import HasPermissionCode

_MISSING_APPLICATION_SERVICE = "Messages are sent over POST /api/v1/chat/conversations/{id}/messages, not over this socket -- this connection is for real-time delivery only."

_SUPPORTED_COMMAND_TYPES = ("message.send", "message.edit", "message.delete", "message.delivered", "message.read")
# Realtime signals handled directly on the socket: heartbeat (keeps presence
# alive, and the connection open through proxies), typing indicator, and
# read receipts (persisted via MarkConversationRead).
_REALTIME_COMMAND_TYPES = ("ping", "typing", "read")


def _group_name(conversation_id: str) -> str:
    return f"chat.conversation.{conversation_id}"


def _inbox_group_name(user_id) -> str:
    return f"chat.inbox.{user_id}"


class ChatConsumer(AsyncJsonWebsocketConsumer):
    """One consumer instance per WebSocket connection, scoped to a single conversation via the route parameter (see `routing.py`)."""

    async def connect(self) -> None:
        conversation_id_raw = self.scope["url_route"]["kwargs"]["conversation_id"]

        user = self.scope.get("user")
        if user is None or not getattr(user, "is_authenticated", False):
            await self.close(code=4401)  # unauthenticated
            return

        try:
            conversation_id = uuid.UUID(conversation_id_raw)
        except ValueError:
            await self.close(code=4400)  # invalid conversation id format
            return

        conversation = await self._load_conversation(conversation_id)
        if conversation is None:
            await self.close(code=4404)  # conversation not found
            return

        if not self._is_active_participant(conversation, user.id):
            await self.close(code=4403)  # authenticated, but not authorized for this conversation -- fail closed
            return

        self.conversation_id = str(conversation_id)
        self.user_id = user.id
        self.group_name = _group_name(self.conversation_id)
        self.other_participant_ids = [p.user_id for p in conversation.participants.values() if p.is_active and p.user_id != user.id]
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await database_sync_to_async(presence.mark_connected)(self.user_id)
        await self.accept()

        # Tell the others this participant is here, and tell this client who else is online right now.
        await self._broadcast({"type": "chat.presence", "user_id": str(self.user_id), "online": True})
        online = await database_sync_to_async(presence.is_online_bulk)(self.other_participant_ids)
        for other_id, is_online in online.items():
            await self.send_json({"type": "presence", "user_id": str(other_id), "online": is_online})

    async def disconnect(self, close_code: int) -> None:
        """Leaves the group safely -- tolerates being called even if `connect()` never actually joined a group (e.g. the connection was rejected before `group_add`). Never mutates Conversation status merely because a socket disconnected, per this phase's own explicit rule."""
        group_name = getattr(self, "group_name", None)
        user_id = getattr(self, "user_id", None)
        if user_id is not None:
            await database_sync_to_async(presence.mark_disconnected)(user_id)
            still_online = await database_sync_to_async(presence.is_online)(user_id)  # another tab may still be open
            if group_name is not None and not still_online:
                await self._broadcast({"type": "chat.presence", "user_id": str(user_id), "online": False})
        if group_name is not None:
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def receive_json(self, content, **kwargs) -> None:
        command_type = content.get("type")
        if not isinstance(command_type, str) or not command_type:
            await self._send_error("invalid_request", "MISSING_COMMAND_TYPE", "Every command must include a non-empty 'type' field.")
            return

        # Ephemeral realtime signals -- any active participant (checked at connect) may send them.
        if command_type == "ping":
            await database_sync_to_async(presence.touch)(self.user_id)
            await self.send_json({"type": "pong"})
            return
        if command_type == "typing":
            await self._broadcast({"type": "chat.typing", "user_id": str(self.user_id), "is_typing": bool(content.get("is_typing", True))})
            return
        if command_type == "read":
            read_at, changed = await database_sync_to_async(self._mark_read)()
            if changed:
                await self._broadcast({"type": "chat.read", "reader_id": str(self.user_id), "read_at": read_at.isoformat()})
            return

        if command_type not in _SUPPORTED_COMMAND_TYPES:
            await self._send_error("invalid_request", "UNKNOWN_COMMAND_TYPE", f"'{command_type}' is not a recognized command type. Supported: {(*_REALTIME_COMMAND_TYPES, *_SUPPORTED_COMMAND_TYPES)}.")
            return

        if not self._has_permission_for(command_type):
            await self._send_error("unauthorized", "PERMISSION_DENIED", f"You do not have permission to perform '{command_type}'.")
            return

        await self._send_error("unsupported_operation", "USE_HTTP_ENDPOINT", _MISSING_APPLICATION_SERVICE)

    # --- Internal helpers (transport concerns only, never business logic) ---

    async def _load_conversation(self, conversation_id: uuid.UUID):
        return await database_sync_to_async(composition.build_conversation_repository().get_by_id)(conversation_id)

    def _is_active_participant(self, conversation, user_id) -> bool:
        return any(p.user_id == user_id and p.is_active for p in conversation.participants.values())

    def _mark_read(self):
        return composition.build_mark_conversation_read(self.user_id).execute(uuid.UUID(self.conversation_id), self.user_id)

    def _has_permission_for(self, command_type: str) -> bool:
        resolver = HasPermissionCode.resolver
        if resolver is None:
            return False
        code = "chat.message.send" if command_type == "message.send" else "chat.message.edit"
        user = self.scope.get("user")
        return resolver.user_has_permission(user.id, code, None)

    async def _broadcast(self, event: dict) -> None:
        """Fan an ephemeral event out to every socket in this conversation; `sender_channel` lets each handler skip echoing it back to its own sender."""
        await self.channel_layer.group_send(self.group_name, {**event, "sender_channel": self.channel_name})

    async def _send_error(self, category: str, code: str, detail: str) -> None:
        await self.send_json({"type": "error", "category": category, "code": code, "detail": detail})

    # --- Group event handlers ---

    async def chat_message_broadcast(self, event: dict) -> None:
        """Handler name matches Channels' own `type` -> `snake_case-with-dots-replaced-by-underscores` dispatch convention (`chat.message.broadcast` -> `chat_message_broadcast`)."""
        await self.send_json(event.get("payload", {}))

    async def chat_typing(self, event: dict) -> None:
        if event.get("sender_channel") != self.channel_name:
            await self.send_json({"type": "typing", "user_id": event["user_id"], "is_typing": event["is_typing"]})

    async def chat_read(self, event: dict) -> None:
        if event.get("sender_channel") != self.channel_name:
            await self.send_json({"type": "messages.read", "reader_id": event["reader_id"], "read_at": event["read_at"]})

    async def chat_presence(self, event: dict) -> None:
        if event.get("sender_channel") != self.channel_name and event.get("user_id") != str(getattr(self, "user_id", "")):
            await self.send_json({"type": "presence", "user_id": event["user_id"], "online": event["online"]})


class ChatInboxConsumer(AsyncJsonWebsocketConsumer):
    """
    Real, closed gap: `ChatConsumer` only ever pushes into the one
    conversation's own group -- a participant who isn't currently
    looking at that exact conversation (sitting on the conversation
    LIST instead, or on a different thread) never learned a new
    message arrived at all short of a manual reload. This is the
    per-USER counterpart: one connection per authenticated participant
    (customer or store owner alike, whichever role they're logged in
    as), joined to `chat.inbox.{user_id}` -- every real message send
    now also notifies every one of its conversation's OTHER active
    participants here (see `views.py`'s own `SendMessageView.post`),
    so the conversation list can refresh itself live the moment a
    reply lands, exactly like a real chat app's inbox.

    Receive-only, same as `ChatConsumer` -- the payload is deliberately
    a bare pointer (`conversation_id`), never a duplicated conversation-
    card shape: the real card data (status, last_activity_at, ...)
    stays sourced from the one real REST list endpoint, never
    reconstructed a second, divergent way inside a WS payload.
    """

    async def connect(self) -> None:
        user = self.scope.get("user")
        if user is None or not getattr(user, "is_authenticated", False):
            await self.close(code=4401)  # unauthenticated
            return

        self.user_id = user.id
        self.group_name = _inbox_group_name(self.user_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code: int) -> None:
        group_name = getattr(self, "group_name", None)
        if group_name is not None:
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def receive_json(self, content, **kwargs) -> None:
        await self.send_json(
            {
                "type": "error", "category": "unsupported_operation", "code": "RECEIVE_ONLY",
                "detail": "This socket is receive-only -- conversations are listed and messages are sent over the real HTTP endpoints.",
            }
        )

    async def chat_inbox_broadcast(self, event: dict) -> None:
        """Handler name matches Channels' dispatch convention (`chat.inbox.broadcast` -> `chat_inbox_broadcast`)."""
        await self.send_json(event.get("payload", {}))
