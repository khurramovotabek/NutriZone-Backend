"""Telegram-style inbox: unread counters + last message per conversation, one support chat per customer, and a
notification-bell entry when a message arrives for someone who's offline."""
from __future__ import annotations

import uuid
from unittest import mock

import pytest
from rest_framework.test import APIClient

from apps.chat.domain.enums import MessageType
from apps.chat.infrastructure import composition
from apps.chat.tests.interfaces.test_realtime_and_store_chat import _authenticate_as, _make_store, _make_user, _permissive_rbac  # noqa: F401
from apps.notifications.infrastructure.models import NotificationModel

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.integration]


def _client(monkeypatch, user) -> APIClient:
    _authenticate_as(monkeypatch, user.id)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
    return c


def _send(conversation_id, sender_id, text):
    return composition.build_send_message(sender_id).execute(conversation_id=uuid.UUID(str(conversation_id)), sender_id=sender_id, message_type=MessageType.TEXT, content=text)


def test_list_carries_unread_count_and_last_message(monkeypatch):
    customer, owner = _make_user(full_name="Ali Valiyev"), _make_user()
    store = _make_store(owner, name="LifeSport Test")
    conv = _client(monkeypatch, customer).post(f"/api/v1/chat/conversations/store/{store.id}").json()["data"]
    _send(conv["id"], customer.id, "Salom, Whey bormi?")
    _send(conv["id"], customer.id, "Chocolate ta'mi kerak")

    rows = _client(monkeypatch, owner).get("/api/v1/chat/conversations").json()["data"]
    row = next(r for r in rows if r["id"] == conv["id"])
    assert row["unread_count"] == 2
    assert row["last_message"]["content"] == "Chocolate ta'mi kerak" and row["last_message"]["is_mine"] is False
    assert row["other_participant_full_name"] == "Ali Valiyev"  # the owner sees who they answer
    assert _client(monkeypatch, owner).get("/api/v1/chat/unread-count").json()["data"] == {"total": 2, "conversations": 1}

    mine = next(r for r in _client(monkeypatch, customer).get("/api/v1/chat/conversations").json()["data"] if r["id"] == conv["id"])
    assert mine["unread_count"] == 0 and mine["last_message"]["is_mine"] is True and mine["store"]["name"] == "LifeSport Test"


def test_one_support_chat_per_customer(monkeypatch):
    customer = _make_user()
    c = _client(monkeypatch, customer)
    first = c.post("/api/v1/chat/conversations", {"conversation_type": "customer_support", "opener_role": "customer"}, format="json")
    second = c.post("/api/v1/chat/conversations", {"conversation_type": "customer_support", "opener_role": "customer"}, format="json")
    assert first.status_code == 201 and second.status_code == 200
    assert first.json()["data"]["id"] == second.json()["data"]["id"]


def test_offline_recipient_gets_one_bell_notification_per_burst(monkeypatch):
    customer, owner = _make_user(full_name="Ali Valiyev"), _make_user()
    store = _make_store(owner)
    conv = _client(monkeypatch, customer).post(f"/api/v1/chat/conversations/store/{store.id}").json()["data"]
    with mock.patch("apps.chat.infrastructure.presence.is_online", return_value=False):
        _send(conv["id"], customer.id, "Salom")
        _send(conv["id"], customer.id, "Javob kutaman")
    rows = NotificationModel.objects.filter(recipient_id=owner.id, kind="chat_message")
    assert rows.count() == 1
    row = rows.get()
    assert row.i18n["uz"]["title"] == "Ali Valiyev: yangi xabar" and row.link == f"/profile/store/inquiries?conversation={conv['id']}"
    with mock.patch("apps.chat.infrastructure.presence.is_online", return_value=True):
        _send(conv["id"], owner.id, "Bor!")  # the customer is online: no bell entry
    assert not NotificationModel.objects.filter(recipient_id=customer.id, kind="chat_message").exists()
