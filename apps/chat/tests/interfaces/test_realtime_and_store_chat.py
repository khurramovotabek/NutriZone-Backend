"""
Tests for this phase's own real additions: customer -> store-owner
conversation routing, the read-side attachment/presence fields, the
attachment upload endpoint, and the WebSocket auth ticket. Auth is
simulated the same way every other Chat/Stores interface test in this
build already does (monkeypatching `JWTIdentityAuthentication.
authenticate`), not a new pattern.
"""
from __future__ import annotations

import io
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from PIL import Image
from rest_framework.test import APIClient

from apps.chat.domain.enums import ConversationType, ParticipantRole
from apps.chat.infrastructure import presence
from apps.chat.infrastructure.repositories import DjangoConversationRepository
from apps.chat.tests.factories import make_conversation
from apps.identity.infrastructure import models as identity_orm
from apps.stores.infrastructure.models import Store
from common.permissions import HasPermissionCode

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class _AllowAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return True


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


def _make_user(**overrides) -> identity_orm.User:
    defaults = {"id": uuid.uuid4(), "phone_number": f"+99890{uuid.uuid4().int % 10000000:07d}", "full_name": "Test User", "status": "active", "language": "uz"}
    defaults.update(overrides)
    return identity_orm.User.objects.create(**defaults)


def _make_store(owner: identity_orm.User, **overrides) -> Store:
    defaults = {"id": uuid.uuid4(), "owner": owner, "name": f"Store {uuid.uuid4().hex[:8]}"}
    defaults.update(overrides)
    return Store.objects.create(**defaults)


@pytest.fixture(autouse=True)
def _permissive_rbac():
    original = HasPermissionCode.resolver
    HasPermissionCode.resolver = _AllowAllResolver()
    yield
    HasPermissionCode.resolver = original


def _authenticate_as(monkeypatch, user_id):
    fake_user = SimpleNamespace(id=user_id, is_authenticated=True, store_ids=set())
    monkeypatch.setattr("apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate", lambda self, request: (fake_user, None))


class TestOpenStoreConversation:
    def test_opens_a_new_conversation_with_the_store_owner_seated(self, api_client, monkeypatch):
        customer = _make_user()
        owner = _make_user()
        store = _make_store(owner)
        _authenticate_as(monkeypatch, customer.id)
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")

        response = api_client.post(f"/api/v1/chat/conversations/store/{store.id}")
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["conversation_type"] == ConversationType.CUSTOMER_SALES.value
        participant_ids = {p["user_id"] for p in data["participants"]}
        assert str(customer.id) in participant_ids
        assert str(owner.id) in participant_ids

    def test_repeat_call_resumes_the_same_conversation(self, api_client, monkeypatch):
        customer = _make_user()
        owner = _make_user()
        store = _make_store(owner)
        _authenticate_as(monkeypatch, customer.id)
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")

        first = api_client.post(f"/api/v1/chat/conversations/store/{store.id}").json()["data"]
        second = api_client.post(f"/api/v1/chat/conversations/store/{store.id}").json()["data"]
        assert first["id"] == second["id"]

    def test_store_not_found_returns_404(self, api_client, monkeypatch):
        _authenticate_as(monkeypatch, uuid.uuid4())
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post(f"/api/v1/chat/conversations/store/{uuid.uuid4()}")
        assert response.status_code == 404

    def test_cannot_open_a_conversation_with_your_own_store(self, api_client, monkeypatch):
        owner = _make_user()
        store = _make_store(owner)
        _authenticate_as(monkeypatch, owner.id)
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post(f"/api/v1/chat/conversations/store/{store.id}")
        assert response.status_code == 422


class TestMessageAttachments:
    def test_send_message_with_a_real_uploaded_attachment_round_trips(self, api_client, monkeypatch, settings):
        # Same real, disclosed testing-settings gap every other module's own
        # media-URL tests already work around (apps/products/tests/infrastructure/
        # test_media_serving_and_url_resolution.py, apps/products/tests/interfaces/
        # test_brand_logo_url.py): config/settings/testing.py pins PUBLIC_BASE_URL
        # to None, so the URL this endpoint builds would otherwise be root-relative
        # -- SendMessageSerializer.attachment_url is a real URLField (absolute
        # URLs only), matching this deployment's real, non-test environment.
        settings.PUBLIC_BASE_URL = "https://nutrizone.uz"
        customer = _make_user()
        conversation = make_conversation(opened_by=customer.id)
        DjangoConversationRepository().save(conversation)
        _authenticate_as(monkeypatch, customer.id)
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")

        buf = io.BytesIO()
        Image.new("RGB", (64, 64), color="blue").save(buf, format="JPEG")
        from django.core.files.uploadedfile import SimpleUploadedFile

        upload_response = api_client.post(
            f"/api/v1/chat/conversations/{conversation.id}/attachments",
            {"file": SimpleUploadedFile("photo.jpg", buf.getvalue(), content_type="image/jpeg")},
            format="multipart",
        )
        assert upload_response.status_code == 201
        attachment = upload_response.json()["data"]
        assert attachment["attachment_type"] == "image"
        assert attachment["attachment_url"]

        send_response = api_client.post(
            f"/api/v1/chat/conversations/{conversation.id}/messages",
            {"message_type": "attachment", **{k: attachment[k] for k in ("attachment_type", "attachment_url", "attachment_filename", "attachment_size_bytes")}},
            format="json",
        )
        assert send_response.status_code == 201
        sent = send_response.json()["data"]
        assert sent["attachment_url"] == attachment["attachment_url"]
        assert sent["attachment_type"] == "image"

        # Real, closed read-side gap this phase fixed: the message list must return the same attachment fields, not just the send response.
        list_response = api_client.get(f"/api/v1/chat/conversations/{conversation.id}/messages")
        assert list_response.json()["data"][0]["attachment_url"] == attachment["attachment_url"]

    def test_send_message_rejects_an_unverified_attachment_url(self, api_client, monkeypatch):
        """A client-supplied URL that this deployment's own media pipeline never produced must never be accepted -- see RealMediaStorageGateway."""
        customer = _make_user()
        conversation = make_conversation(opened_by=customer.id)
        DjangoConversationRepository().save(conversation)
        _authenticate_as(monkeypatch, customer.id)
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")

        response = api_client.post(
            f"/api/v1/chat/conversations/{conversation.id}/messages",
            {"message_type": "attachment", "attachment_type": "image", "attachment_url": "https://evil.example.com/not-ours.jpg", "attachment_filename": "x.jpg", "attachment_size_bytes": 100},
            format="json",
        )
        assert response.status_code == 422

    def test_send_message_accepts_a_known_sticker_url(self, api_client, monkeypatch, settings):
        """Stickers live in the frontend's own /public/stickers/, not backend media storage -- see RealMediaStorageGateway.STICKER_SLUGS, a closed allow-list rather than a prefix match."""
        settings.FRONTEND_URL = "https://nutrizone.uz"
        customer = _make_user()
        conversation = make_conversation(opened_by=customer.id)
        DjangoConversationRepository().save(conversation)
        _authenticate_as(monkeypatch, customer.id)
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")

        response = api_client.post(
            f"/api/v1/chat/conversations/{conversation.id}/messages",
            {"message_type": "attachment", "attachment_type": "image", "attachment_url": "https://nutrizone.uz/stickers/fire.svg", "attachment_filename": "fire.svg", "attachment_size_bytes": 900},
            format="json",
        )
        assert response.status_code == 201

    def test_send_message_rejects_an_unknown_sticker_filename(self, api_client, monkeypatch, settings):
        settings.FRONTEND_URL = "https://nutrizone.uz"
        customer = _make_user()
        conversation = make_conversation(opened_by=customer.id)
        DjangoConversationRepository().save(conversation)
        _authenticate_as(monkeypatch, customer.id)
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")

        response = api_client.post(
            f"/api/v1/chat/conversations/{conversation.id}/messages",
            {"message_type": "attachment", "attachment_type": "image", "attachment_url": "https://nutrizone.uz/stickers/../../etc/passwd.svg", "attachment_filename": "x.svg", "attachment_size_bytes": 100},
            format="json",
        )
        assert response.status_code == 422


class TestPresence:
    def test_reference_counted_across_multiple_connections(self):
        user_id = uuid.uuid4()
        assert presence.is_online(user_id) is False
        presence.mark_connected(user_id)
        presence.mark_connected(user_id)  # a second tab/device
        assert presence.is_online(user_id) is True
        presence.mark_disconnected(user_id)
        assert presence.is_online(user_id) is True  # first tab still open
        presence.mark_disconnected(user_id)
        assert presence.is_online(user_id) is False

    def test_conversation_detail_reflects_participant_presence(self, api_client, monkeypatch):
        customer = _make_user()
        owner = _make_user()
        conversation = make_conversation(opened_by=customer.id, conversation_type=ConversationType.CUSTOMER_SALES)
        conversation.add_participant(owner.id, ParticipantRole.OPERATOR, datetime.utcnow())
        DjangoConversationRepository().save(conversation)
        presence.mark_connected(owner.id)
        try:
            _authenticate_as(monkeypatch, customer.id)
            api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
            response = api_client.get(f"/api/v1/chat/conversations/{conversation.id}")
            participants = {p["user_id"]: p["is_online"] for p in response.json()["data"]["participants"]}
            assert participants[str(owner.id)] is True
            assert participants[str(customer.id)] is False
        finally:
            presence.mark_disconnected(owner.id)


class TestWsTicket:
    def test_requires_authentication(self, api_client):
        response = api_client.post("/api/v1/identity/auth/ws-ticket")
        assert response.status_code == 401

    def test_issues_a_short_lived_real_token(self, api_client, monkeypatch):
        user_id = uuid.uuid4()
        _authenticate_as(monkeypatch, user_id)
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post("/api/v1/identity/auth/ws-ticket")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["expires_in"] == 60

        from rest_framework_simplejwt.tokens import AccessToken

        decoded = AccessToken(data["ticket"])
        assert decoded["user_id"] == str(user_id)
