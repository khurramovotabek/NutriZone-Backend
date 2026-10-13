"""
Dashboard → Chat markazi (the support desk) and the conversation / message registers: the queue and its filters,
a thread with the customer profile, replies (text / sticker) through SendMessage with a real-time push, store
chats stay read-only for staff, take / close / reopen through the services, and old attachment URLs on a dead
tunnel host are rebuilt on today's hosts.
"""
from __future__ import annotations

import json
import uuid
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.chat.domain.enums import ConversationType, MessageType, ParticipantRole
from apps.chat.infrastructure import composition
from apps.chat.infrastructure import models as orm
from apps.identity.infrastructure.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff():
    user = get_user_model().objects.create(username=f"desk_{uuid.uuid4().hex[:6]}", is_staff=True, is_superuser=True, first_name="Malika")
    client = Client()
    client.force_login(user)
    return client


def _customer(name="Jasur Rahimov"):
    return User.objects.create(phone_number=f"+99895{uuid.uuid4().int % 10_000_000:07d}", full_name=name, status="active")


def _support_chat(customer, text="Buyurtmam qachon keladi?"):
    conv = composition.build_open_conversation(customer.id).execute(opened_by=customer.id, conversation_type=ConversationType.CUSTOMER_SUPPORT, opener_role=ParticipantRole.CUSTOMER)
    composition.build_send_message(customer.id).execute(conversation_id=conv.id, sender_id=customer.id, message_type=MessageType.TEXT, content=text)
    return conv


class TestQueue:
    def test_desk_renders_with_the_waiting_customer(self, staff):
        _support_chat(_customer("Jasur Rahimov"))
        html = staff.get("/django-admin/chat/").content.decode()
        assert "Chat markazi" in html and "Jasur Rahimov" in html and "nutrizone-chat-desk.js" in html

    def test_queue_filters(self, staff):
        c = _support_chat(_customer())
        rows = staff.get("/django-admin/chat/api/queue?f=waiting").json()["data"]["rows"]
        assert [r["id"] for r in rows] == [str(c.id)] and rows[0]["unread"] == 1 and rows[0]["last_from_customer"]
        assert staff.get("/django-admin/chat/api/queue?f=mine").json()["data"]["rows"] == []
        assert staff.get("/django-admin/chat/api/queue?f=waiting&q=nobody").json()["data"]["rows"] == []


class TestThreadAndReplies:
    def test_thread_has_messages_and_profile(self, staff):
        c = _support_chat(_customer("Dilnoza"))
        data = staff.get(f"/django-admin/chat/api/conversations/{c.id}").json()["data"]
        assert data["messages"][0]["kind"] == "customer" and "qachon" in data["messages"][0]["content"]
        assert data["profile"]["customer"]["name"] == "Dilnoza" and data["conversation"]["can_reply"]

    def test_reply_joins_assigns_pushes_and_marks_read(self, staff):
        customer = _customer()
        c = _support_chat(customer)
        with mock.patch("apps.chat.infrastructure.realtime.push_message") as push:
            r = staff.post(f"/django-admin/chat/conversations/{c.id}/send", data=json.dumps({"kind": "text", "content": "Bugun yetkaziladi"}), content_type="application/json")
        assert r.status_code == 201
        assert r.json()["data"]["messages"][0]["kind"] == "staff" and r.json()["data"]["conversation"]["assigned"] == "me"
        assert push.called and str(customer.id) in {str(u) for u in push.call_args[0][3]}
        assert orm.MessageModel.objects.get(conversation_id=c.id, sender_id=customer.id).read_at is not None  # the customer sees ✓✓
        assert staff.get("/django-admin/chat/api/queue?f=waiting").json()["data"]["rows"] == []

    def test_sticker_reply(self, staff):
        c = _support_chat(_customer())
        r = staff.post(f"/django-admin/chat/conversations/{c.id}/send", data=json.dumps({"kind": "sticker", "content": "thanks"}), content_type="application/json")
        assert r.status_code == 201 and r.json()["data"]["messages"][0]["sticker"]["emoji"] == "🙏"
        assert staff.post(f"/django-admin/chat/conversations/{c.id}/send", data=json.dumps({"kind": "sticker", "content": "nope"}), content_type="application/json").status_code == 422

    def test_store_chats_are_read_only_for_staff(self, staff):
        customer = _customer()
        c = _support_chat(customer)
        orm.ConversationModel.objects.filter(pk=c.id).update(conversation_type="customer_sales")
        r = staff.post(f"/django-admin/chat/conversations/{c.id}/send", data=json.dumps({"content": "Salom"}), content_type="application/json")
        assert r.status_code == 409

    def test_take_close_reopen(self, staff):
        c = _support_chat(_customer())
        for action, status in (("take", "open"), ("close", "closed"), ("reopen", "open")):
            r = staff.post(f"/django-admin/chat/api/conversations/{c.id}/do/{action}")
            assert r.status_code == 200 and r.json()["data"]["conversation"]["status"] == status
        orm.ConversationModel.objects.filter(pk=c.id).update(status="closed")
        r = staff.post(f"/django-admin/chat/conversations/{c.id}/send", data=json.dumps({"content": "Salom"}), content_type="application/json")
        assert r.status_code >= 400 and "qayta oching" in r.json()["error"]["message"]


class TestRegisters:
    def test_conversation_and_message_lists(self, staff):
        c = _support_chat(_customer("Kamola"))
        assert "Kamola" in staff.get("/django-admin/chat/conversationmodel/").content.decode()
        assert "qachon" in staff.get("/django-admin/chat/messagemodel/").content.decode()
        r = staff.get(f"/django-admin/chat/conversationmodel/{c.id}/change/")
        assert r.status_code == 302 and r["Location"].endswith(f"?c={c.id}")

    def test_close_action(self, staff):
        c = _support_chat(_customer())
        staff.post("/django-admin/chat/conversationmodel/", {"action": "close_selected", "_selected_action": [c.id], "index": 0})
        assert orm.ConversationModel.objects.get(pk=c.id).status == "closed"


def test_old_tunnel_attachment_urls_are_rebuilt(settings):
    from apps.chat.infrastructure.realtime import attachment_url

    settings.PUBLIC_BASE_URL = "https://api.nutrizone.uz"
    settings.FRONTEND_URL = "https://nutrizone.uz"
    old = f"https://dead-tunnel.trycloudflare.com{settings.MEDIA_URL}image/ab/cd/x.jpeg"
    assert attachment_url(old) == f"https://api.nutrizone.uz{settings.MEDIA_URL}image/ab/cd/x.jpeg"
    assert attachment_url(old, absolute=False) == f"{settings.MEDIA_URL}image/ab/cd/x.jpeg"
    assert attachment_url("https://old.trycloudflare.com/stickers/fire.svg") == "https://nutrizone.uz/stickers/fire.svg"
