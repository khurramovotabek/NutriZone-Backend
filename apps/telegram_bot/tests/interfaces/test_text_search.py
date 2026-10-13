"""Typing in a private chat with the bot searches the catalog with the website's smart search."""
from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import pytest
from django.test import Client

from apps.search.infrastructure.models import SearchTerm
from apps.telegram_bot.tests.interfaces.test_product_browsing import _WEBHOOK_AUTH, _callback, _make_customer, _make_product

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _bot(settings):
    from core.caching.redis_client import get_redis_client

    settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
    settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"
    get_redis_client().flushall()


def _text(client, tg_user_id, text, chat_type="private", chat_id=None):
    update = {"update_id": 2, "message": {"message_id": 5, "from": {"id": tg_user_id}, "chat": {"id": chat_id or tg_user_id, "type": chat_type}, "text": text}}
    return client.post("/api/v1/telegram/webhook", data=json.dumps(update), content_type="application/json", **_WEBHOOK_AUTH)


def _sent(mock_send):
    return [c[0][1] for c in mock_send.call_args_list]


def test_a_misspelled_cyrillic_query_finds_the_product_and_is_counted():
    customer = _make_customer()
    _make_product(f"Zorvex{uuid.uuid4().hex[:4]} Creatine Monohydrate")
    with patch("apps.telegram_bot.interfaces.callback_router._send") as mock_send:
        _text(Client(), customer.telegram_user_id, "креатн")
    texts = _sent(mock_send)
    assert "1" in texts[0] and "креатн" in texts[0]  # "found N for ..." header
    assert "Creatine Monohydrate" in texts[1]  # the product card (no image -> text card)
    assert SearchTerm.objects.get(term="kreatn").last_results == 1


def test_nothing_found_offers_the_catalog_and_support_and_escapes_html():
    customer = _make_customer()
    with patch("apps.telegram_bot.interfaces.callback_router._send") as mock_send:
        _text(Client(), customer.telegram_user_id, "<b>qwzxv</b>")
    text, keyboard = mock_send.call_args[0][1], mock_send.call_args[0][2]
    assert "&lt;b&gt;qwzxv&lt;/b&gt;" in text
    assert {"pm:all", "menu:chat", "menu:home"} <= {b["callback_data"] for row in keyboard for b in row}


def test_group_chats_and_commands_are_not_searched():
    customer = _make_customer()
    with patch("apps.telegram_bot.interfaces.callback_router._send") as mock_send:
        _text(Client(), customer.telegram_user_id, "protein", chat_type="group", chat_id=-100123)
        _text(Client(), customer.telegram_user_id, "/help")
    assert mock_send.call_count == 0


def test_unregistered_users_are_asked_to_register():
    with patch("apps.telegram_bot.interfaces.callback_router._send") as mock_send:
        _text(Client(), 987654321, "protein")
    assert "/start" in mock_send.call_args[0][1]


def test_paging_and_clearing_filters_keep_the_search():
    customer = _make_customer()
    tag = uuid.uuid4().hex[:4]
    _make_product(f"Quorna{tag} Whey Alpha")
    _make_product(f"Quorna{tag} Whey Beta")
    _make_product("Unrelated Vitamin C")
    client = Client()
    with patch("apps.telegram_bot.interfaces.callback_router._send") as mock_send, \
            patch("apps.telegram_bot.interfaces.callback_router._edit_photo", return_value=False), \
            patch("apps.notifications.infrastructure.gateways.LiveTelegramGateway.edit_message_text", side_effect=Exception("force the _send fallback")), \
            patch("apps.telegram_bot.interfaces.api.v1.views._answer_callback_query"):
        _text(client, customer.telegram_user_id, f"quorna{tag}")
        first = mock_send.call_args[0][1]
        _callback(client, customer.telegram_user_id, "pc:next")
        second = mock_send.call_args[0][1]
        _callback(client, customer.telegram_user_id, "flt:clear")
        after_clear = mock_send.call_args[0][1]
    assert {f"Quorna{tag} Whey Alpha" in first, f"Quorna{tag} Whey Alpha" in second} == {True, False}
    assert "Unrelated Vitamin C" not in after_clear and f"Quorna{tag}" in after_clear


def test_price_band_filter_is_stored_and_survives_a_brand_change():
    from apps.telegram_bot.interfaces import catalog_state
    from apps.telegram_bot.interfaces.callback_router import _price_band_label

    assert _price_band_label(0, 200_000, "uz") == "\U0001F4B0 ≤ 200 000 so'm"
    assert _price_band_label(1_000_000, None, "ru") == "\U0001F4B0 1 000 000+ сум"

    customer = _make_customer()
    _make_product("Any Product")
    client = Client()
    chat = customer.telegram_user_id
    with patch("apps.telegram_bot.interfaces.callback_router._send"), \
            patch("apps.notifications.infrastructure.gateways.LiveTelegramGateway.edit_message_text", side_effect=Exception("force the _send fallback")), \
            patch("apps.telegram_bot.interfaces.api.v1.views._answer_callback_query"):
        _callback(client, chat, "pm:all")
        _callback(client, chat, "flt:setprice:200000-500000")
        assert (catalog_state.get_browsing(chat)["price_min"], catalog_state.get_browsing(chat)["price_max"]) == (200000, 500000)
        _callback(client, chat, f"flt:setbrand:{uuid.uuid4()}")
        assert catalog_state.get_browsing(chat)["price_max"] == 500000
        _callback(client, chat, "flt:setprice:1000000-")
        assert (catalog_state.get_browsing(chat)["price_min"], catalog_state.get_browsing(chat)["price_max"]) == (1000000, None)
