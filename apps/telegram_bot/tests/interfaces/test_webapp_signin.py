"""Telegram Mini App sign-in: only genuine, fresh initData of a registered customer yields an auto-login session."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from django.test import Client

from apps.telegram_bot.interfaces.webapp import MAX_AGE_SECONDS, verified_user
from apps.telegram_bot.tests.interfaces.test_product_browsing import _make_customer

pytestmark = pytest.mark.django_db
TOKEN = "123456:TEST-TOKEN"


def _init_data(tg_id: int, *, token: str = TOKEN, auth_date: int | None = None, tamper: bool = False, username: str | None = None) -> str:
    user = {"id": tg_id, "first_name": "Ali", **({"username": username} if username else {})}
    fields = {"auth_date": str(auth_date or int(time.time())), "query_id": "AAH", "user": json.dumps(user)}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if tamper:
        fields["user"] = json.dumps({"id": tg_id + 1, "first_name": "Ali"})
    return urlencode(fields)


@pytest.fixture(autouse=True)
def _bot(settings):
    from core.caching.redis_client import get_redis_client

    settings.TELEGRAM_BOT_TOKEN = TOKEN
    get_redis_client().flushdb()  # own database only (testing.py gives each xdist worker one); flushall wiped the other workers


def test_signature_age_and_tampering_are_checked():
    assert verified_user(_init_data(42), TOKEN)["id"] == 42
    assert verified_user(_init_data(42, token="999:OTHER"), TOKEN) is None  # signed for another bot
    assert verified_user(_init_data(42, tamper=True), TOKEN) is None  # user swapped after signing
    assert verified_user(_init_data(42, auth_date=int(time.time()) - MAX_AGE_SECONDS - 5), TOKEN) is None  # stale
    assert verified_user("user=%7B%7D&auth_date=1", TOKEN) is None  # no hash at all


def test_registered_customer_gets_a_verified_auto_login_session():
    from apps.identity.infrastructure.models import TelegramAuthSession

    customer = _make_customer()
    response = Client().post("/api/v1/telegram/webapp/session", {"init_data": _init_data(customer.telegram_user_id)}, content_type="application/json")

    assert response.status_code == 200
    session = TelegramAuthSession.objects.get(id=response.json()["data"]["session_id"])
    assert (session.user_id, session.status) == (customer.id, "verified")


def test_sign_in_fills_an_empty_telegram_username_but_never_overwrites_one():
    customer = _make_customer()
    customer.telegram_username = None
    customer.save(update_fields=["telegram_username"])
    Client().post("/api/v1/telegram/webapp/session", {"init_data": _init_data(customer.telegram_user_id, username="ali_fit")}, content_type="application/json")
    customer.refresh_from_db()
    assert customer.telegram_username == "ali_fit"  # checkout's recipient form comes prefilled

    Client().post("/api/v1/telegram/webapp/session", {"init_data": _init_data(customer.telegram_user_id, username="someone_else")}, content_type="application/json")
    customer.refresh_from_db()
    assert customer.telegram_username == "ali_fit"


def test_forged_data_and_unregistered_users_are_refused():
    client = Client()
    forged = client.post("/api/v1/telegram/webapp/session", {"init_data": _init_data(77, token="999:OTHER")}, content_type="application/json")
    unknown = client.post("/api/v1/telegram/webapp/session", {"init_data": _init_data(77)}, content_type="application/json")
    assert (forged.status_code, forged.json()["error"]["code"]) == (401, "INVALID_INIT_DATA")
    assert (unknown.status_code, unknown.json()["error"]["code"]) == (404, "NOT_REGISTERED")


def test_main_menu_and_menu_button_open_the_mini_app_only_over_https(settings):
    from unittest.mock import MagicMock, patch

    from django.core.management import call_command

    from apps.telegram_bot.interfaces.callback_router import _main_menu_keyboard

    settings.FRONTEND_URL = "https://shop.example/"
    assert _main_menu_keyboard("uz")[0][0]["web_app"] == {"url": "https://shop.example/tg"}
    ok = MagicMock(content=b"1")
    ok.json.return_value = {"ok": True}
    with patch("requests.post", return_value=ok) as post:
        call_command("telegram_set_menu_button")
    menu_call = next(c for c in post.call_args_list if c[0][0].endswith("/setChatMenuButton"))
    assert menu_call[1]["json"]["menu_button"]["web_app"]["url"] == "https://shop.example/tg"
    assert any(c[0][0].endswith("/setMyCommands") for c in post.call_args_list)  # the "/" list, per language

    settings.FRONTEND_URL = "http://localhost:3000"
    assert all("web_app" not in b for row in _main_menu_keyboard("uz") for b in row)
    with patch("requests.post") as post:
        call_command("telegram_set_menu_button")
    post.assert_not_called()


def test_mini_app_gets_the_bot_cart_so_both_share_one_cart():
    from apps.identity.infrastructure.models import User

    customer = _make_customer()
    data = Client().post("/api/v1/telegram/webapp/session", {"init_data": _init_data(customer.telegram_user_id)}, content_type="application/json").json()["data"]
    cart = data["cart"]
    user = User.objects.get(id=customer.id)
    assert user.telegram_cart_id is not None and cart["code"] and cart["token"]
    # the same cart, readable with the owner's token through the normal cart API
    again = Client().post("/api/v1/telegram/webapp/session", {"init_data": _init_data(customer.telegram_user_id)}, content_type="application/json").json()["data"]["cart"]
    assert again == cart


def test_contact_shared_from_the_mini_app_registers_in_the_shoppers_telegram_language(settings):
    from unittest.mock import patch

    from apps.identity.infrastructure.models import User

    settings.TELEGRAM_WEBHOOK_SECRET = "s"
    update = {"update_id": 1, "message": {"message_id": 1, "date": 0, "chat": {"id": 5551234, "type": "private"},
                                          "from": {"id": 5551234, "first_name": "Ivan", "language_code": "ru"},
                                          "contact": {"phone_number": "998901112233", "first_name": "Ivan", "user_id": 5551234}}}
    with patch("apps.telegram_bot.interfaces.callback_router._send") as send:
        r = Client().post("/api/v1/telegram/webhook", json.dumps(update), content_type="application/json", HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="s")
    assert r.status_code == 200
    user = User.objects.get(telegram_user_id=5551234)
    assert (user.full_name, user.phone_number, user.language) == ("Ivan", "+998901112233", "ru")
    welcome = send.call_args_list[0][0][1]
    assert "Добро пожаловать, Ivan" in welcome
    # and the shopper can now sign in from the Mini App
    ok = Client().post("/api/v1/telegram/webapp/session", {"init_data": _init_data(5551234)}, content_type="application/json")
    assert ok.status_code == 200


def test_bot_commands_need_a_registered_shopper():
    from unittest.mock import patch

    from apps.telegram_bot.interfaces.callback_router import run_command

    with patch("apps.telegram_bot.interfaces.callback_router._send") as send:
        assert run_command(7001, 7001, "savat") is True
        assert run_command(7001, 7001, "nonsense") is False
    assert "/start" in send.call_args[0][1]
