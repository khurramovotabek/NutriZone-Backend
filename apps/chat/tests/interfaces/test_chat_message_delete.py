"""
Chat markazi → "unsend": a staff member deletes one of their own messages through DeleteMessage. The row stays
(status deleted + deleted_at, audit trail), the desk shows "Xabar o'chirilgan", the customer / store message list
leaves it out, live clients get a message.deleted push, and nobody can delete someone else's message.
"""
from __future__ import annotations

import json
import uuid
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.chat.domain.enums import ConversationType, MessageType, ParticipantRole
from apps.chat.domain.exceptions import MessageAlreadyDeleted, MessageNotOwnedBySender
from apps.chat.infrastructure import composition
from apps.chat.infrastructure import models as orm
from apps.identity.infrastructure.models import User
from common.exceptions import ResourceNotFound

pytestmark = pytest.mark.django_db


def _staff():
    user = get_user_model().objects.create(username=f"del_{uuid.uuid4().hex[:6]}", is_staff=True, is_superuser=True, first_name="Otabek")
    client = Client()
    client.force_login(user)
    return user, client


def _chat_with_reply(client):
    customer = User.objects.create(phone_number=f"+99893{uuid.uuid4().int % 10_000_000:07d}", full_name="Aziz", status="active")
    conv = composition.build_open_conversation(customer.id).execute(opened_by=customer.id, conversation_type=ConversationType.CUSTOMER_SUPPORT, opener_role=ParticipantRole.CUSTOMER)
    composition.build_send_message(customer.id).execute(conversation_id=conv.id, sender_id=customer.id, message_type=MessageType.TEXT, content="Salom")
    with mock.patch("apps.chat.infrastructure.realtime.push_message"):
        r = client.post(f"/django-admin/chat/conversations/{conv.id}/send", data=json.dumps({"kind": "text", "content": "NutriZone sizga sifatli xizmat ko'rsatadi"}), content_type="application/json")
    assert r.status_code == 201
    mine = orm.MessageModel.objects.get(conversation_id=conv.id, content__startswith="NutriZone")
    theirs = orm.MessageModel.objects.get(conversation_id=conv.id, sender_id=customer.id)
    return conv, mine, theirs


def _delete(client, conv, message_id):
    return client.post(f"/django-admin/chat/api/conversations/{conv.id}/do/delete", data=json.dumps({"message_id": str(message_id)}), content_type="application/json")


def test_staff_deletes_own_message_everywhere():
    _, client = _staff()
    conv, mine, _ = _chat_with_reply(client)
    with mock.patch("apps.chat.infrastructure.realtime.push_message_deleted") as push:
        r = _delete(client, conv, mine.id)
    assert r.status_code == 200 and r.json()["data"]["deleted"] is True
    push.assert_called_once()
    mine.refresh_from_db()
    assert mine.status == "deleted" and mine.message_deleted_at is not None
    thread = client.get(f"/django-admin/chat/api/conversations/{conv.id}").json()["data"]["messages"]
    row = next(m for m in thread if m["id"] == str(mine.id))
    assert row["deleted"] and row["content"] == ""
    rows, total = composition.build_message_selector().list_for_conversation(conv.id, 1, 50)
    assert total == 1 and [m["content"] for m in rows] == ["Salom"]  # the customer no longer sees it
    assert orm.ChatOutboxEvent.objects.filter(event_type="MessageDeleted").exists()


def test_cannot_delete_customer_message_or_twice_or_foreign_id():
    _, client = _staff()
    conv, mine, theirs = _chat_with_reply(client)
    r = _delete(client, conv, theirs.id)
    assert r.status_code == 403
    theirs.refresh_from_db()
    assert theirs.status != "deleted"
    assert _delete(client, conv, mine.id).status_code == 200
    assert _delete(client, conv, mine.id).status_code == 409
    assert _delete(client, conv, uuid.uuid4()).status_code == 404
    assert client.post(f"/django-admin/chat/api/conversations/{conv.id}/do/delete", data="{}", content_type="application/json").status_code == 404


def test_delete_message_service_rules():
    from apps.platform.infrastructure.chat_view import staff_uuid

    user, client = _staff()
    conv, mine, theirs = _chat_with_reply(client)
    me = staff_uuid(user.id)  # a staff member's chat identity
    svc = composition.build_delete_message(me)
    with pytest.raises(ResourceNotFound):
        svc.execute(conversation_id=uuid.uuid4(), message_id=mine.id, requested_by=me)  # wrong conversation
    with pytest.raises(MessageNotOwnedBySender):
        svc.execute(conversation_id=conv.id, message_id=theirs.id, requested_by=me)
    svc.execute(conversation_id=conv.id, message_id=mine.id, requested_by=me)
    with pytest.raises(MessageAlreadyDeleted):
        svc.execute(conversation_id=conv.id, message_id=mine.id, requested_by=me)


def test_desk_script_has_the_delete_button():
    _, client = _staff()
    html = client.get("/django-admin/chat/").content.decode()
    assert "nutrizone-chat-desk.js' %}" not in html and "nutrizone-chat-desk.js?v=7" in html


def test_archived_conversation_comes_back_with_unarchive_and_deleted_preview_is_hidden():
    _, client = _staff()
    conv, mine, _ = _chat_with_reply(client)
    assert client.post(f"/django-admin/chat/api/conversations/{conv.id}/do/archive").status_code == 200
    assert client.post(f"/django-admin/chat/api/conversations/{conv.id}/do/reopen").status_code == 409  # archive stays terminal for reopen
    _delete(client, conv, mine.id)
    rows = client.get("/django-admin/chat/api/queue?f=closed").json()["data"]["rows"]
    assert next(r for r in rows if r["id"] == str(conv.id))["last"] == "Salom"  # the deleted reply is not the preview
    r = client.post(f"/django-admin/chat/api/conversations/{conv.id}/do/unarchive")
    assert r.status_code == 200 and r.json()["data"]["conversation"]["status"] == "open"
    assert client.post(f"/django-admin/chat/api/conversations/{conv.id}/do/unarchive").status_code in (409, 422)
    assert orm.ChatOutboxEvent.objects.filter(event_type="ConversationReopened").exists()
