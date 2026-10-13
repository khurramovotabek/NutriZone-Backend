"""
Real, live-verified regression test for Phase D: Chat admin premium
interface. Every scenario here was proven live -- a real customer
opens a conversation and sends a message via the real REST API, a
real admin views it and replies via the new admin-only view, and the
reply appears in the real message list -- before being formalized.
"""
from __future__ import annotations

import json
import uuid

import pytest
from django.contrib.auth.models import User as AuthUser
from django.test import Client

from apps.identity.infrastructure import models as identity_orm
from apps.identity.infrastructure.security import hash_otp_code

pytestmark = pytest.mark.django_db


def _register_real_customer_with_conversation(name: str) -> tuple[Client, str]:
    client = Client()
    phone = f"+99890{uuid.uuid4().int % 10000000:07d}"
    client.post("/api/v1/identity/auth/request-otp", data=json.dumps({"phone_number": phone}), content_type="application/json")
    challenge = identity_orm.OTPCodeChallenge.objects.filter(phone_number=phone).order_by("-created_at").first()
    challenge.code_hash = hash_otp_code("999999")
    challenge.save(update_fields=["code_hash"])
    response = client.post("/api/v1/identity/auth/verify-otp", data=json.dumps({"phone_number": phone, "code": "999999"}), content_type="application/json")
    access_token = json.loads(response.content)["data"]["access_token"]
    auth = {"HTTP_AUTHORIZATION": f"Bearer {access_token}"}
    me = client.get("/api/v1/identity/users/me", **auth)
    customer_id = json.loads(me.content)["data"]["id"]
    identity_orm.User.objects.filter(id=customer_id).update(full_name=name)

    conv_response = client.post("/api/v1/chat/conversations", data=json.dumps({"conversation_type": "customer_support", "opener_role": "customer"}), content_type="application/json", **auth)
    conversation_id = json.loads(conv_response.content)["data"]["id"]
    client.post(f"/api/v1/chat/conversations/{conversation_id}/messages", data=json.dumps({"message_type": "text", "content": "Real customer question"}), content_type="application/json", **auth)
    return client, conversation_id


@pytest.fixture
def staff_client():
    user = AuthUser.objects.create_superuser(username=f"admin_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
    client = Client()
    client.force_login(user)
    return client


class TestChatAdminInterface:
    def test_admin_home_shows_real_customer_name(self, staff_client):
        _, _ = _register_real_customer_with_conversation("Ali Karimov")
        response = staff_client.get("/django-admin/chat/")
        assert response.status_code == 200
        assert "Ali Karimov" in response.content.decode()

    def test_admin_can_view_real_customer_message(self, staff_client):
        _, conversation_id = _register_real_customer_with_conversation("Madina Qurbonova")
        response = staff_client.get(f"/django-admin/chat/conversations/{conversation_id}/messages")
        assert response.status_code == 200
        body = json.loads(response.content)
        assert any("Real customer question" in m["content"] for m in body["data"])

    def test_admin_can_reply_and_reply_appears_in_thread(self, staff_client):
        _, conversation_id = _register_real_customer_with_conversation("Jasurbek Aslanov")
        response = staff_client.post(f"/django-admin/chat/conversations/{conversation_id}/send", data=json.dumps({"content": "Hello, how can I help?"}), content_type="application/json")
        assert response.status_code == 201

        follow_up = staff_client.get(f"/django-admin/chat/conversations/{conversation_id}/messages")
        body = json.loads(follow_up.content)
        assert any("Hello, how can I help?" in m["content"] for m in body["data"])
