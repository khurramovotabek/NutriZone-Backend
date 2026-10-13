"""
WebSocket consumer tests.

**A deliberate, disclosed testing strategy, stated plainly rather
than left implicit**: these tests use `channels.testing.
WebsocketCommunicator` with a directly-injected `scope["user"]`,
bypassing the real `core.channels_auth.JWTAuthMiddleware` entirely.
This is not a workaround for that middleware's own foundation-stage
placeholder behavior (confirmed in Phase 3's own Step 1: it always
returns `AnonymousUser` regardless of token) -- it is the standard,
correct way to unit-test a consumer's OWN authorization logic in
isolation from a separate upstream concern, the exact same principle
already applied throughout every HTTP test in this build (which
monkeypatches `JWTIdentityAuthentication.authenticate` to inject a
fake authenticated identity rather than depending on a real token
issuer). `TestUnauthenticatedConnection` below specifically verifies
the unauthenticated-rejection path using the SAME
`AnonymousUser`-shaped scope the real middleware currently always
produces -- proving this consumer's fail-closed check is itself
correct, even though this file cannot exercise the real middleware
end-to-end (that would require the real middleware to actually work,
which per Phase 3's own disclosed finding, it currently does not).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser

from apps.chat.domain.enums import ParticipantRole
from apps.chat.infrastructure.repositories import DjangoConversationRepository
from apps.chat.interfaces.consumers import ChatConsumer
from apps.chat.tests.factories import make_conversation
from common.permissions import HasPermissionCode

pytestmark = [pytest.mark.django_db, pytest.mark.asyncio, pytest.mark.integration]


def _authenticated_scope_user(user_id):
    return SimpleNamespace(id=user_id, is_authenticated=True)


class _AllowAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return True


class _DenyAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return False


class TestUnauthenticatedConnection:
    async def test_anonymous_user_is_rejected_with_4401(self):
        """Uses the exact AnonymousUser shape the real, currently-non-functional core.channels_auth middleware always produces -- proving the consumer's own fail-closed check is correct against the real upstream behavior, not a hypothetical one."""
        conversation = make_conversation()
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{conversation.id}/")
        communicator.scope["user"] = AnonymousUser()
        communicator.scope["url_route"] = {"kwargs": {"conversation_id": str(conversation.id)}}

        connected, subprotocol_or_close_code = await communicator.connect()
        assert connected is False

        await communicator.disconnect()

    async def test_missing_user_in_scope_is_rejected(self):
        conversation = make_conversation()
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{conversation.id}/")
        communicator.scope["user"] = None
        communicator.scope["url_route"] = {"kwargs": {"conversation_id": str(conversation.id)}}

        connected, _ = await communicator.connect()
        assert connected is False

        await communicator.disconnect()


class TestAuthenticatedConnection:
    """Uses a directly-injected authenticated scope -- see this module's own docstring for the full rationale."""

    async def test_active_participant_can_connect(self):
        user_id = uuid.uuid4()
        conversation = make_conversation(opened_by=user_id)
        await database_sync_to_async(DjangoConversationRepository().save)(conversation)

        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{conversation.id}/")
        communicator.scope["user"] = _authenticated_scope_user(user_id)
        communicator.scope["url_route"] = {"kwargs": {"conversation_id": str(conversation.id)}}

        connected, _ = await communicator.connect()
        assert connected is True

        await communicator.disconnect()

    async def test_non_participant_is_rejected_with_4403(self):
        """Object-level authorization -- authenticated, but not an active participant of THIS specific conversation."""
        conversation = make_conversation()  # opened by someone else
        await database_sync_to_async(DjangoConversationRepository().save)(conversation)

        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{conversation.id}/")
        communicator.scope["user"] = _authenticated_scope_user(uuid.uuid4())
        communicator.scope["url_route"] = {"kwargs": {"conversation_id": str(conversation.id)}}

        connected, _ = await communicator.connect()
        assert connected is False

        await communicator.disconnect()

    async def test_removed_participant_is_rejected(self):
        """A participant who was removed (soft) must not be able to connect -- `is_active` is checked, not merely membership history."""
        user_id = uuid.uuid4()
        conversation = make_conversation()
        conversation.add_participant(user_id, ParticipantRole.OPERATOR, datetime.utcnow())
        conversation.remove_participant(user_id, datetime.utcnow())
        await database_sync_to_async(DjangoConversationRepository().save)(conversation)

        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{conversation.id}/")
        communicator.scope["user"] = _authenticated_scope_user(user_id)
        communicator.scope["url_route"] = {"kwargs": {"conversation_id": str(conversation.id)}}

        connected, _ = await communicator.connect()
        assert connected is False

        await communicator.disconnect()

    async def test_nonexistent_conversation_is_rejected_with_4404(self):
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{uuid.uuid4()}/")
        communicator.scope["user"] = _authenticated_scope_user(uuid.uuid4())
        communicator.scope["url_route"] = {"kwargs": {"conversation_id": str(uuid.uuid4())}}

        connected, _ = await communicator.connect()
        assert connected is False

        await communicator.disconnect()

    async def test_malformed_conversation_id_is_rejected_with_4400(self):
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), "/ws/chat/not-a-uuid/")
        communicator.scope["user"] = _authenticated_scope_user(uuid.uuid4())
        communicator.scope["url_route"] = {"kwargs": {"conversation_id": "not-a-uuid"}}

        connected, _ = await communicator.connect()
        assert connected is False

        await communicator.disconnect()


class TestCommandDispatch:
    """Connection established via a directly-injected authenticated, authorized scope -- see this module's own docstring."""

    async def _connect(self, resolver):
        original = HasPermissionCode.resolver
        HasPermissionCode.resolver = resolver
        user_id = uuid.uuid4()
        conversation = make_conversation(opened_by=user_id)
        await database_sync_to_async(DjangoConversationRepository().save)(conversation)

        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{conversation.id}/")
        communicator.scope["user"] = _authenticated_scope_user(user_id)
        communicator.scope["url_route"] = {"kwargs": {"conversation_id": str(conversation.id)}}
        connected, _ = await communicator.connect()
        assert connected is True
        return communicator, original

    async def test_missing_type_returns_invalid_request(self):
        communicator, original = await self._connect(_AllowAllResolver())
        await communicator.send_json_to({})
        response = await communicator.receive_json_from()
        assert response["category"] == "invalid_request"
        assert response["code"] == "MISSING_COMMAND_TYPE"
        HasPermissionCode.resolver = original
        await communicator.disconnect()

    async def test_unknown_type_returns_invalid_request(self):
        communicator, original = await self._connect(_AllowAllResolver())
        await communicator.send_json_to({"type": "conversation.delete_everything"})
        response = await communicator.receive_json_from()
        assert response["category"] == "invalid_request"
        assert response["code"] == "UNKNOWN_COMMAND_TYPE"
        HasPermissionCode.resolver = original
        await communicator.disconnect()

    async def test_recognized_but_unpermitted_command_returns_unauthorized(self):
        communicator, original = await self._connect(_DenyAllResolver())
        await communicator.send_json_to({"type": "message.send", "payload": {}})
        response = await communicator.receive_json_from()
        assert response["category"] == "unauthorized"
        HasPermissionCode.resolver = original
        await communicator.disconnect()

    @pytest.mark.parametrize("command_type", ["message.send", "message.edit", "message.delete", "message.delivered", "message.read"])
    async def test_every_supported_command_returns_unsupported_operation(self, command_type):
        """Every one of the 5 supported command types must return the honest unsupported_operation error -- the direct, disclosed consequence of zero Application Services existing for Chat."""
        communicator, original = await self._connect(_AllowAllResolver())
        await communicator.send_json_to({"type": command_type, "payload": {}})
        response = await communicator.receive_json_from()
        assert response["category"] == "unsupported_operation"
        assert response["type"] == "error"
        HasPermissionCode.resolver = original
        await communicator.disconnect()
