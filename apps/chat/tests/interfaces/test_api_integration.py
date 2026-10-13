"""
Full-stack HTTP API integration tests -- real URL routing,
serializers, views, and repository/selector layer together against a
real database.

**Every conversation-lifecycle mutation endpoint tested here is
expected to return HTTP 501**, since zero Application Services exist
for conversation lifecycle management. Message-sending is the one
exception (Phase 03B's own first real Chat Application Service,
`SendMessage`) -- see `TestSendMessage` below for its own real,
working tests.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.chat.infrastructure.repositories import DjangoConversationRepository, DjangoMessageRepository
from apps.chat.domain.enums import ConversationType, ParticipantRole
from apps.chat.tests.factories import make_conversation, make_conversation_with_operator, make_message
from common.permissions import HasPermissionCode

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


class _AllowAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return True


class _DenyAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return False


class TestUnauthenticatedAccess:
    def test_conversation_list_requires_auth(self, api_client):
        response = api_client.get("/api/v1/chat/conversations")
        assert response.status_code == 401


class TestPermissionDenial:
    @pytest.fixture(autouse=True)
    def _authenticated_but_unauthorized(self, monkeypatch):
        original = HasPermissionCode.resolver
        HasPermissionCode.resolver = _DenyAllResolver()
        fake_user = SimpleNamespace(id=uuid.uuid4(), is_authenticated=True, store_ids=set())
        monkeypatch.setattr(
            "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
            lambda self, request: (fake_user, None),
        )
        yield
        HasPermissionCode.resolver = original

    def test_conversation_list_denied(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.get("/api/v1/chat/conversations")
        assert response.status_code == 403


class TestAuthorizedFlows:
    @pytest.fixture(autouse=True)
    def _authenticated_and_authorized(self, monkeypatch):
        original = HasPermissionCode.resolver
        HasPermissionCode.resolver = _AllowAllResolver()
        self.fake_user_id = uuid.uuid4()
        fake_user = SimpleNamespace(id=self.fake_user_id, is_authenticated=True, store_ids=set())
        monkeypatch.setattr(
            "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
            lambda self, request: (fake_user, None),
        )
        yield
        HasPermissionCode.resolver = original

    # --- Working (read) endpoints, all 4 ---------------------------------

    def test_list_own_conversations(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        conversation = make_conversation(opened_by=self.fake_user_id)
        DjangoConversationRepository().save(conversation)
        response = api_client.get("/api/v1/chat/conversations")
        assert response.status_code == 200
        assert "pagination" in response.json()

    def test_conversation_detail(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        conversation = make_conversation(opened_by=self.fake_user_id)
        DjangoConversationRepository().save(conversation)
        response = api_client.get(f"/api/v1/chat/conversations/{conversation.id}")
        assert response.status_code == 200
        assert len(response.json()["data"]["participants"]) == 1

    def test_conversation_detail_forbidden_for_non_participant(self, api_client):
        """The object-level authorization check -- generic permission code alone is not enough; the requester must actually be a participant of THIS conversation."""
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        conversation = make_conversation()  # opened by someone else, not self.fake_user_id
        DjangoConversationRepository().save(conversation)
        response = api_client.get(f"/api/v1/chat/conversations/{conversation.id}")
        assert response.status_code == 403

    def test_conversation_detail_not_found(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.get(f"/api/v1/chat/conversations/{uuid.uuid4()}")
        assert response.status_code == 404

    def test_conversation_message_list(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        conversation = make_conversation(opened_by=self.fake_user_id)
        DjangoConversationRepository().save(conversation)
        message = make_message(conversation_id=conversation.id)
        DjangoMessageRepository().save(message)
        response = api_client.get(f"/api/v1/chat/conversations/{conversation.id}/messages")
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    def test_statistics(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        DjangoConversationRepository().save(make_conversation())
        response = api_client.get("/api/v1/chat/statistics")
        assert response.status_code == 200
        assert "conversation_counts_by_status" in response.json()["data"]

    # --- Send Message (Phase 03B's own first real Application Service) ----

    def test_send_message_succeeds_for_active_participant(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        conversation = make_conversation(opened_by=self.fake_user_id)
        DjangoConversationRepository().save(conversation)

        response = api_client.post(f"/api/v1/chat/conversations/{conversation.id}/messages", {"message_type": "text", "content": "Hello there"}, format="json")
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["content"] == "Hello there"
        assert data["sender_id"] == str(self.fake_user_id)  # derived from identity, not a client-suppliable field
        assert data["conversation_id"] == str(conversation.id)

    def test_send_message_blocked_for_non_participant(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        conversation = make_conversation()  # opened by someone else, not self.fake_user_id
        DjangoConversationRepository().save(conversation)

        response = api_client.post(f"/api/v1/chat/conversations/{conversation.id}/messages", {"message_type": "text", "content": "Hello there"}, format="json")
        assert response.status_code == 403

    def test_send_message_empty_content_rejected(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        conversation = make_conversation(opened_by=self.fake_user_id)
        DjangoConversationRepository().save(conversation)

        response = api_client.post(f"/api/v1/chat/conversations/{conversation.id}/messages", {"message_type": "text"}, format="json")
        assert response.status_code == 422

    def test_send_message_to_closed_conversation_rejected(self, api_client):
        """A closed store chat and an archived support chat stay closed. (A customer writing into their own CLOSED
        support chat reopens it -- a new question; see test_support_automation.py.)"""
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        store_chat = make_conversation(opened_by=self.fake_user_id, conversation_type=ConversationType.CUSTOMER_SALES)
        store_chat.close()
        DjangoConversationRepository().save(store_chat)
        archived = make_conversation(opened_by=self.fake_user_id)
        archived.close()
        archived.archive()
        DjangoConversationRepository().save(archived)

        for conversation in (store_chat, archived):
            response = api_client.post(f"/api/v1/chat/conversations/{conversation.id}/messages", {"message_type": "text", "content": "Hello there"}, format="json")
            assert response.status_code == 409

    def test_send_message_persists_and_is_listable(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        conversation = make_conversation(opened_by=self.fake_user_id)
        DjangoConversationRepository().save(conversation)
        api_client.post(f"/api/v1/chat/conversations/{conversation.id}/messages", {"message_type": "text", "content": "First message"}, format="json")

        response = api_client.get(f"/api/v1/chat/conversations/{conversation.id}/messages")
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    # --- Honest 501 mutation endpoints, all 7 -----------------------------

    def test_open_conversation_succeeds(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post("/api/v1/chat/conversations", {"conversation_type": "customer_support", "opener_role": "customer"}, format="json")
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["conversation_type"] == "customer_support"
        assert data["status"] == "open"
        assert len(data["participants"]) == 1
        assert data["participants"][0]["user_id"] == str(self.fake_user_id)  # derived from identity, not a client-suppliable field

        # Verify real persistence, not just the HTTP response.
        saved = DjangoConversationRepository().get_by_id(uuid.UUID(data["id"]))
        assert saved is not None
        assert saved.conversation_type.value == "customer_support"

    def test_open_conversation_validates_input(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post("/api/v1/chat/conversations", {"conversation_type": "not_a_real_type", "opener_role": "customer"}, format="json")
        assert response.status_code == 422

    def test_open_conversation_rejects_invalid_role_for_type(self, api_client):
        """Conversation.open()'s own domain rule (ParticipantPolicy.is_role_valid_for_conversation_type) is exercised through the real HTTP path, not bypassed."""
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post("/api/v1/chat/conversations", {"conversation_type": "internal_support", "opener_role": "customer"}, format="json")
        assert response.status_code == 422

    def test_add_participant_succeeds(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        conversation = make_conversation()
        DjangoConversationRepository().save(conversation)
        new_user_id = uuid.uuid4()

        response = api_client.post(f"/api/v1/chat/conversations/{conversation.id}/participants", {"user_id": str(new_user_id), "role": "operator"}, format="json")
        assert response.status_code == 201
        participants = response.json()["data"]["participants"]
        assert any(p["user_id"] == str(new_user_id) and p["role"] == "operator" for p in participants)

        # Verify real persistence, not just the HTTP response.
        saved = DjangoConversationRepository().get_by_id(conversation.id)
        assert any(p.user_id == new_user_id and p.role.value == "operator" for p in saved.participants.values())

    def test_add_duplicate_active_participant_rejected(self, api_client):
        """Conversation.add_participant()'s own real domain rule (ParticipantAlreadyExists) is exercised through the real HTTP path, not bypassed."""
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        conversation, operator_id = make_conversation_with_operator()
        DjangoConversationRepository().save(conversation)

        response = api_client.post(f"/api/v1/chat/conversations/{conversation.id}/participants", {"user_id": str(operator_id), "role": "operator"}, format="json")
        assert response.status_code == 409

    def test_add_participant_invalid_role_for_conversation_type_rejected(self, api_client):
        """Conversation.add_participant()'s own real domain rule (ParticipantPolicy) is exercised, matching the same rejection already proven for OpenConversation."""
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        conversation = make_conversation(conversation_type=ConversationType.INTERNAL_SUPPORT, opener_role=ParticipantRole.OPERATOR)
        DjangoConversationRepository().save(conversation)

        response = api_client.post(f"/api/v1/chat/conversations/{conversation.id}/participants", {"user_id": str(uuid.uuid4()), "role": "customer"}, format="json")
        assert response.status_code == 422

    def test_add_participant_conversation_not_found(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post(f"/api/v1/chat/conversations/{uuid.uuid4()}/participants", {"user_id": str(uuid.uuid4()), "role": "operator"}, format="json")
        assert response.status_code == 404

    def test_remove_participant_succeeds(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        conversation, operator_id = make_conversation_with_operator()
        DjangoConversationRepository().save(conversation)

        response = api_client.delete(f"/api/v1/chat/conversations/{conversation.id}/participants/{operator_id}")
        assert response.status_code == 200
        participants = response.json()["data"]["participants"]
        removed = next(p for p in participants if p["user_id"] == str(operator_id))
        assert removed["removed_at"] is not None

        saved = DjangoConversationRepository().get_by_id(conversation.id)
        removed_participant = next(p for p in saved.participants.values() if p.user_id == operator_id)
        assert removed_participant.removed_at is not None

    def test_remove_participant_not_a_participant_rejected(self, api_client):
        """Conversation.remove_participant()'s own real domain rule (ParticipantNotFound) is exercised through the real HTTP path."""
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        conversation = make_conversation()
        DjangoConversationRepository().save(conversation)

        response = api_client.delete(f"/api/v1/chat/conversations/{conversation.id}/participants/{uuid.uuid4()}")
        assert response.status_code == 422

    def test_assign_operator_succeeds(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        conversation = make_conversation()
        DjangoConversationRepository().save(conversation)
        operator_id = uuid.uuid4()

        response = api_client.post(f"/api/v1/chat/conversations/{conversation.id}/assign", {"operator_user_id": str(operator_id)}, format="json")
        assert response.status_code == 200
        assert response.json()["data"]["assigned_operator_id"] == str(operator_id)

        saved = DjangoConversationRepository().get_by_id(conversation.id)
        assert saved.assigned_operator_id == operator_id

    def test_close_conversation_succeeds(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        conversation = make_conversation()
        DjangoConversationRepository().save(conversation)

        response = api_client.post(f"/api/v1/chat/conversations/{conversation.id}/close", {}, format="json")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "closed"

        saved = DjangoConversationRepository().get_by_id(conversation.id)
        assert saved.status.value == "closed"

    def test_close_already_closed_conversation_rejected(self, api_client):
        """Conversation.close()'s own real domain rule (InvalidConversationTransition) is exercised through the real HTTP path."""
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        conversation = make_conversation()
        conversation.close()
        DjangoConversationRepository().save(conversation)

        response = api_client.post(f"/api/v1/chat/conversations/{conversation.id}/close", {}, format="json")
        assert response.status_code == 409

    def test_reopen_closed_conversation_succeeds(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        conversation = make_conversation()
        conversation.close()
        DjangoConversationRepository().save(conversation)

        response = api_client.post(f"/api/v1/chat/conversations/{conversation.id}/reopen", {}, format="json")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "open"

    def test_reopen_open_conversation_rejected(self, api_client):
        """Conversation.reopen()'s own real domain rule (only CLOSED conversations can reopen) is exercised through the real HTTP path."""
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        conversation = make_conversation()
        DjangoConversationRepository().save(conversation)

        response = api_client.post(f"/api/v1/chat/conversations/{conversation.id}/reopen", {}, format="json")
        assert response.status_code == 409

    def test_archive_conversation_succeeds(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        conversation = make_conversation()
        DjangoConversationRepository().save(conversation)

        response = api_client.post(f"/api/v1/chat/conversations/{conversation.id}/archive", {}, format="json")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "archived"

        saved = DjangoConversationRepository().get_by_id(conversation.id)
        assert saved.status.value == "archived"

    def test_archive_already_archived_conversation_rejected(self, api_client):
        """Conversation.archive()'s own real domain rule (InvalidConversationTransition) is exercised through the real HTTP path."""
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        conversation = make_conversation()
        conversation.archive()
        DjangoConversationRepository().save(conversation)

        response = api_client.post(f"/api/v1/chat/conversations/{conversation.id}/archive", {}, format="json")
        assert response.status_code == 409

    def test_all_resource_scoped_mutations_404_when_conversation_missing(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        missing_id = uuid.uuid4()
        assert api_client.post(f"/api/v1/chat/conversations/{missing_id}/participants", {"user_id": str(uuid.uuid4()), "role": "operator"}, format="json").status_code == 404
        assert api_client.delete(f"/api/v1/chat/conversations/{missing_id}/participants/{uuid.uuid4()}").status_code == 404
        assert api_client.post(f"/api/v1/chat/conversations/{missing_id}/assign", {"operator_user_id": str(uuid.uuid4())}, format="json").status_code == 404
        assert api_client.post(f"/api/v1/chat/conversations/{missing_id}/close", {}, format="json").status_code == 404
        assert api_client.post(f"/api/v1/chat/conversations/{missing_id}/reopen", {}, format="json").status_code == 404
        assert api_client.post(f"/api/v1/chat/conversations/{missing_id}/archive", {}, format="json").status_code == 404
