"""Customer bot: "find this product" (text / link / photo), photos in the support chat, stores + nearest, /privacy, chat language."""
from __future__ import annotations

import io
import json
import uuid
from unittest.mock import patch

import pytest
from django.test import Client

from apps.identity.infrastructure import models as identity_orm
from apps.support.infrastructure.models import ProductRequest
from apps.telegram_bot.infrastructure.tg_files import TelegramFile
from apps.telegram_bot.interfaces import find_product

pytestmark = pytest.mark.django_db
AUTH = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": "test-webhook-secret"}


@pytest.fixture(autouse=True)
def _bot(settings, tmp_path):
    from core.caching.redis_client import get_redis_client

    settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
    settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"
    settings.MEDIA_ROOT = tmp_path
    get_redis_client().flushdb()
    yield


def _user(tg_id: int, language: str = "uz"):
    return identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", status="active",
                                            telegram_user_id=tg_id, full_name="Aziz", language=language)


def _post(update: dict):
    return Client().post("/api/v1/telegram/webhook", data=json.dumps({"update_id": 1, **update}), content_type="application/json", **AUTH)


def _msg(tg_id: int, **fields) -> dict:
    return {"message": {"message_id": 5, "chat": {"id": tg_id, "type": "private"}, "from": {"id": tg_id}, **fields}}


def _callback(tg_id: int, data: str) -> dict:
    return {"callback_query": {"id": "cb", "from": {"id": tg_id}, "message": {"chat": {"id": tg_id}}, "data": data}}


def _png() -> TelegramFile:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (16, 16), "blue").save(buf, "PNG")
    return TelegramFile(content=buf.getvalue(), filename="photo.png", mime_type="image/png")


def test_split_text_takes_the_link_and_first_line():
    assert find_product.split_text("Mutant Mass 6.8 kg\nshokoladli https://iherb.com/pr/x") == ("Mutant Mass 6.8 kg", "shokoladli", "https://iherb.com/pr/x")
    name, _, url = find_product.split_text("iherb.com/pr/mutant-mass")
    assert url == "https://iherb.com/pr/mutant-mass" and "iherb.com" in name


def test_menu_find_then_text_creates_a_request():
    tg = 7001
    user = _user(tg)
    with patch("apps.telegram_bot.interfaces.callback_router._send") as send:
        _post(_callback(tg, "menu:find"))
        assert find_product.is_awaiting(tg)
        _post(_msg(tg, text="Kevin Levrone Gold Whey 2 kg https://example.com/gold"))
    row = ProductRequest.objects.get(customer=user)
    assert row.product_name == "Kevin Levrone Gold Whey 2 kg" and row.url == "https://example.com/gold"
    assert row.number in send.call_args_list[-1].args[1] and not find_product.is_awaiting(tg)


def test_text_without_find_mode_is_still_a_search():
    tg = 7002
    _user(tg)
    with patch("apps.telegram_bot.interfaces.callback_router.search_text") as search:
        _post(_msg(tg, text="protein"))
    assert search.called and ProductRequest.objects.count() == 0


def test_stray_photo_is_offered_then_sent_with_the_image():
    tg = 7003
    user = _user(tg, "ru")
    with patch("apps.telegram_bot.interfaces.callback_router._send") as send, patch("apps.telegram_bot.infrastructure.tg_files.download", return_value=_png()):
        _post(_msg(tg, photo=[{"file_id": "small", "file_size": 10, "width": 90, "height": 90}, {"file_id": "big", "file_size": 900, "width": 800, "height": 800}],
                   caption="Optimum Nutrition Serious Mass"))
        assert "Найти этот товар" in send.call_args.args[1]  # the offer, in the shopper's language
        assert ProductRequest.objects.count() == 0
        _post(_callback(tg, "fp:send"))
    row = ProductRequest.objects.get(customer=user)
    assert row.product_name == "Optimum Nutrition Serious Mass" and row.image.name.startswith("product-requests/")


def test_photo_in_open_support_chat_becomes_an_image_message():
    from apps.chat.infrastructure.models import MessageModel

    tg = 7004
    _user(tg)
    with patch("apps.telegram_bot.interfaces.callback_router._send"):
        _post(_callback(tg, "menu:chat"))
    with patch("apps.telegram_bot.interfaces.api.v1.views._reply_text") as reply, patch("apps.telegram_bot.infrastructure.tg_files.download", return_value=_png()):
        _post(_msg(tg, photo=[{"file_id": "big", "file_size": 900, "width": 16, "height": 16}], caption="Shu bormi?"))
    message = MessageModel.objects.filter(message_type="attachment").order_by("-created_at").first()
    assert message is not None and message.content == "Shu bormi?"
    assert ProductRequest.objects.count() == 0 and reply.called


def test_chat_acknowledgement_uses_the_shoppers_language():
    tg = 7005
    _user(tg, "en")
    with patch("apps.telegram_bot.interfaces.callback_router._send"):
        _post(_callback(tg, "menu:chat"))
    with patch("apps.telegram_bot.interfaces.api.v1.views._reply_text") as reply:
        _post(_msg(tg, text="Hello, do you have creatine?"))
    assert "sent" in reply.call_args.args[1].lower()


def test_location_outside_checkout_lists_the_nearest_stores():
    from apps.stores.infrastructure.models import Store

    tg = 7006
    _user(tg)
    Store.objects.create(id=uuid.uuid4(), name="Far Branch", slug=f"far-{uuid.uuid4().hex[:5]}", kind="store", status="active", latitude=39.65, longitude=66.96)
    Store.objects.create(id=uuid.uuid4(), name="Near Branch", slug=f"near-{uuid.uuid4().hex[:5]}", kind="store", status="active", latitude=41.31, longitude=69.28)
    Store.objects.create(id=uuid.uuid4(), name="Warehouse", slug=f"wh-{uuid.uuid4().hex[:5]}", kind="warehouse", status="active", latitude=41.31, longitude=69.28)
    with patch("apps.telegram_bot.interfaces.callback_router._send") as send:
        _post(_msg(tg, location={"latitude": 41.30, "longitude": 69.27}))
    text = send.call_args.args[1]
    assert text.index("Near Branch") < text.index("Far Branch") and "Warehouse" not in text


def test_privacy_command_answers_even_before_sign_up(settings):
    settings.FRONTEND_URL = "https://nutrizone.uz"
    with patch("apps.telegram_bot.interfaces.callback_router._send") as send:
        _post(_msg(7007, text="/privacy"))
    keyboard = send.call_args.args[2]
    assert any(b.get("url") == "https://nutrizone.uz/privacy" for row in keyboard for b in row)
    assert any(b.get("url") == "https://nutrizone.uz/terms" for row in keyboard for b in row)


def test_main_menu_has_find_and_stores():
    from apps.telegram_bot.interfaces.callback_router import _main_menu_keyboard

    data = [b.get("callback_data") for row in _main_menu_keyboard("uz") for b in row]
    assert "menu:find" in data and "menu:stores" in data
