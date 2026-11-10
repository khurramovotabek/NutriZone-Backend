"""The Orders channel connection (orders_chat.py): env fallback, Telegram-side detection, dashboard connect/test/disconnect."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.telegram_bot.infrastructure import orders_chat
from apps.telegram_bot.infrastructure.models import OrdersChannelSettings, TelegramBotChat, TelegramOrdersChannelCursor, TelegramStaffMember

pytestmark = pytest.mark.django_db

SECRET = "test-orders-webhook-secret-only-not-real"
CHANNEL = {"id": -1001234567890, "title": "NutriZone Orders", "type": "channel"}


@pytest.fixture(autouse=True)
def _bot(settings):
    settings.TELEGRAM_ORDERS_BOT_TOKEN = "test-orders-token"
    settings.TELEGRAM_ORDERS_WEBHOOK_SECRET = SECRET
    settings.TELEGRAM_ORDERS_CHAT_ID = ""
    orders_chat._forget()
    yield
    orders_chat._forget()


@pytest.fixture
def api():
    calls = []

    def fake(token, method, *, data=None, json_body=None, files=None):
        calls.append((method, json_body or data))
        if method == "getChat":
            return {**CHANNEL, "username": "nz_orders"}
        if method == "getMe":
            return {"id": 777, "username": "nz_orders_bot"}
        if method == "getChatMember":
            return {"status": "administrator", "can_post_messages": True}
        return {"message_id": 1}

    with patch("apps.telegram_bot.infrastructure.rich._api", side_effect=fake):
        yield calls


def _hook(update):
    return Client().post("/api/v1/telegram/orders-webhook", data=json.dumps(update), content_type="application/json",
                         HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=SECRET)


def _member_update(status="administrator", can_post=True, from_id=42):
    return {"my_chat_member": {"chat": CHANNEL, "from": {"id": from_id, "first_name": "Owner"},
                               "new_chat_member": {"status": status, "can_post_messages": can_post, "user": {"id": 777, "is_bot": True}}}}


def test_env_fallback_and_dashboard_value_wins(settings):
    settings.TELEGRAM_ORDERS_CHAT_ID = "-100111"
    assert orders_chat.chat_id() == "-100111"
    OrdersChannelSettings.objects.create(pk=1, chat_id="-100222")
    orders_chat._forget()
    assert orders_chat.chat_id() == "-100222"


def test_bot_added_by_staff_connects_automatically_and_skips_history(api):
    TelegramStaffMember.objects.create(telegram_user_id=42, is_active=True)
    cursor = TelegramOrdersChannelCursor.objects.create(id=1)
    from apps.ordering.infrastructure.models import OrderingOutboxEvent

    old = OrderingOutboxEvent.objects.create(event_type="OrderCreated", payload={})
    assert _hook(_member_update()).status_code == 200
    assert orders_chat.chat_id() == str(CHANNEL["id"])
    cursor.refresh_from_db()
    assert cursor.last_processed_id == old.id  # old orders are not replayed into the new channel
    assert any(m == "sendMessage" and "ulandi" in body["text"] for m, body in api)


def test_bot_added_by_a_stranger_is_only_remembered(api):
    _hook(_member_update(from_id=999))
    assert orders_chat.chat_id() == ""
    row = TelegramBotChat.objects.get(chat_id=CHANNEL["id"])
    assert row.can_post and row.title == "NutriZone Orders"


def test_channel_post_never_connects(api):
    _hook({"channel_post": {"chat": CHANNEL, "message_id": 5, "text": "/ulash"}})
    assert orders_chat.chat_id() == ""
    assert TelegramBotChat.objects.filter(chat_id=CHANNEL["id"]).exists()


def test_losing_admin_rights_is_flagged(api):
    OrdersChannelSettings.objects.create(pk=1, chat_id=str(CHANNEL["id"]))
    _hook(_member_update(status="left", can_post=False))
    assert "chiqarildi" in OrdersChannelSettings.objects.get(pk=1).last_error
    assert orders_chat.chat_id() == str(CHANNEL["id"])  # kept, so the dashboard shows the problem


def test_supergroup_migration_keeps_the_channel(api):
    OrdersChannelSettings.objects.create(pk=1, chat_id="-555", chat_type="group")
    _hook({"message": {"chat": {"id": -555, "type": "group"}, "migrate_to_chat_id": -1009999}})
    orders_chat._forget()
    assert orders_chat.chat_id() == "-1009999"


@pytest.mark.parametrize("ref", ["@nz_orders", "nz_orders", "https://t.me/nz_orders", "-1001234567890"])
def test_connect_by_reference(api, ref):
    ok, _ = orders_chat.connect_ref(ref, "Dashboard: admin")
    assert ok and orders_chat.chat_id() == str(CHANNEL["id"])
    assert OrdersChannelSettings.objects.get(pk=1).username == "nz_orders"


def test_connect_refused_without_post_rights(api):
    with patch("apps.telegram_bot.infrastructure.orders_chat._can_post", return_value=False):
        ok, text = orders_chat.connect_ref("@nz_orders", "x")
    assert not ok and "admin" in text and orders_chat.chat_id() == ""


def test_dashboard_actions_superuser_only(api):
    User = get_user_model()
    staff = User.objects.create_user("staff_oc", password="x", is_staff=True)
    c = Client()
    c.force_login(staff)
    assert c.post("/django-admin/telegram/orders-channel/", {"op": "connect", "ref": "@nz_orders"}).status_code == 403
    root = User.objects.create_superuser("root_oc", "r@example.com", "x")
    c.force_login(root)
    r = c.post("/django-admin/telegram/orders-channel/", {"op": "connect", "ref": "@nz_orders"})
    assert r.status_code == 302 and orders_chat.chat_id() == str(CHANNEL["id"])
    page = c.get("/django-admin/telegram/status/")
    assert page.status_code == 200 and "NutriZone Orders" in page.content.decode()
    c.post("/django-admin/telegram/orders-channel/", {"op": "test"})
    assert sum(1 for m, _ in api if m == "sendMessage") >= 2
    c.post("/django-admin/telegram/orders-channel/", {"op": "disconnect"})
    assert orders_chat.chat_id() == ""


def test_orders_webhook_listens_for_chat_membership():
    from apps.telegram_bot.management.commands.telegram_set_webhook import ORDERS_ALLOWED_UPDATES

    assert {"my_chat_member", "channel_post", "callback_query", "message"} <= set(ORDERS_ALLOWED_UPDATES)
