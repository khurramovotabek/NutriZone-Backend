"""Inline mode (`@bot protein` in any chat) and the product deep link its cards carry (`/start p_<id>`)."""
from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import pytest
from django.test import Client

from apps.telegram_bot.interfaces import inline_search
from apps.telegram_bot.tests.interfaces.test_product_browsing import _WEBHOOK_AUTH, _make_customer, _make_product

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _bot(settings):
    from core.caching.redis_client import get_redis_client

    settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
    settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"
    settings.TELEGRAM_BOT_USERNAME = "nutrizone_test_bot"
    settings.FRONTEND_URL = "https://shop.example"
    get_redis_client().flushall()


def _inline(query: str, offset: str = "", tg_id: int = 555, language_code: str = "ru") -> dict:
    return {"id": "iq1", "from": {"id": tg_id, "language_code": language_code}, "query": query, "offset": offset}


def test_answer_carries_cards_with_bot_and_website_links_and_html_escaped_names():
    product = _make_product(f"Vexo{uuid.uuid4().hex[:4]} <Creatine> Monohydrate")
    payload = inline_search.build_answer(_inline("креатин"))

    hit = next(r for r in payload["results"] if r["id"] == str(product.id))
    assert "&lt;Creatine&gt;" in hit["input_message_content"]["message_text"]
    urls = [b["url"] for row in hit["reply_markup"]["inline_keyboard"] for b in row]
    assert f"https://t.me/nutrizone_test_bot?start=p_{product.id}" in urls
    assert any(u.startswith("https://shop.example/products/") for u in urls)
    assert payload["button"]["start_parameter"] == "inline"
    assert "Нет в наличии" in hit["description"]  # unlinked user -> Telegram app language (ru)


def test_pages_ten_at_a_time():
    tag = uuid.uuid4().hex[:4]
    for i in range(12):
        _make_product(f"Pagina{tag} Whey {i}")
    first = inline_search.build_answer(_inline(f"pagina{tag}"))
    second = inline_search.build_answer(_inline(f"pagina{tag}", offset=first["next_offset"]))
    assert (len(first["results"]), first["next_offset"], len(second["results"]), second["next_offset"]) == (10, "10", 2, "")


def test_webhook_routes_inline_queries_to_answer_inline_query():
    _make_product("Any Whey")
    update = {"update_id": 9, "inline_query": _inline("whey")}
    with patch("requests.post") as post:
        Client().post("/api/v1/telegram/webhook", data=json.dumps(update), content_type="application/json", **_WEBHOOK_AUTH)
    assert post.call_args[0][0].endswith("/answerInlineQuery")
    assert post.call_args[1]["json"]["inline_query_id"] == "iq1"


def test_start_with_a_product_link_opens_that_product_not_the_login_flow():
    customer = _make_customer()
    product = _make_product("Linked Whey Isolate")
    update = {"update_id": 3, "message": {"message_id": 1, "from": {"id": customer.telegram_user_id}, "chat": {"id": customer.telegram_user_id, "type": "private"}, "text": f"/start p_{product.id}"}}
    with patch("apps.telegram_bot.interfaces.callback_router._send") as mock_send, \
            patch("apps.telegram_bot.interfaces.api.v1.views._handle_telegram_auth_start") as auth_start:
        Client().post("/api/v1/telegram/webhook", data=json.dumps(update), content_type="application/json", **_WEBHOOK_AUTH)
    auth_start.assert_not_called()
    assert "Linked Whey Isolate" in mock_send.call_args[0][1]
    assert any(b.get("callback_data", "").startswith("cart:add:") for row in mock_send.call_args[0][2] for b in row)


@pytest.mark.parametrize("payload", ["inline", "webapp"])
def test_plain_entry_payloads_show_the_menu_not_the_auto_login_flow(payload):
    customer = _make_customer()
    update = {"update_id": 4, "message": {"message_id": 1, "from": {"id": customer.telegram_user_id}, "chat": {"id": customer.telegram_user_id, "type": "private"}, "text": f"/start {payload}"}}
    with patch("apps.telegram_bot.interfaces.callback_router._send") as mock_send, \
            patch("apps.telegram_bot.interfaces.api.v1.views._handle_telegram_auth_start") as auth_start:
        Client().post("/api/v1/telegram/webhook", data=json.dumps(update), content_type="application/json", **_WEBHOOK_AUTH)
    auth_start.assert_not_called()
    assert "NUTRIZONE" in mock_send.call_args[0][1]  # the main menu
