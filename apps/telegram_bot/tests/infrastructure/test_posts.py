from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.telegram_bot.infrastructure import posts
from apps.telegram_bot.infrastructure.models import TelegramPost

pytestmark = pytest.mark.django_db

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
       b"\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")


def _customer(telegram_id, phone):
    from apps.identity.infrastructure.models import User

    return User.objects.create(phone_number=phone, telegram_user_id=telegram_id, status="active")


class FakeApi:
    def __init__(self, fail_for=()):
        self.calls = []
        self.fail_for = set(fail_for)

    def __call__(self, method, *, data=None, files=None):
        self.calls.append((method, dict(data or {}), bool(files)))
        if str((data or {}).get("chat_id")) in self.fail_for:
            raise posts.PostError("Forbidden: bot was blocked by the user")
        if method == "sendPhoto":
            return {"message_id": 10, "photo": [{"file_id": "small"}, {"file_id": "big"}]}
        return {"message_id": 11}


@pytest.fixture
def settings_bot(settings):
    settings.TELEGRAM_BOT_TOKEN = "123:test"
    settings.FRONTEND_URL = "https://nutrizone.uz"
    return settings


def test_keyboard_two_per_row_and_only_http_links(settings_bot):
    post = TelegramPost(title="t", buttons=[{"text": "A", "url": "https://a.uz"}, {"text": "B", "url": "javascript:x"}, {"text": "C", "url": "https://c.uz"}, {"text": "D", "url": "tg://resolve?domain=x"}])
    assert posts.keyboard(post) == [[{"text": "A", "url": "https://a.uz"}, {"text": "C", "url": "https://c.uz"}], [{"text": "D", "url": "tg://resolve?domain=x"}]]


def test_text_only_post_to_channel_and_customers(settings_bot):
    _customer(111, "+998900000001")
    _customer(222, "+998900000002")
    post = TelegramPost.objects.create(title="Aksiya", body="<b>-20%</b> hamma proteinlarga", to_channel=True, channel="@nutrizone_uz", to_customers=True, pin=True, status="queued")
    api = FakeApi(fail_for={"222"})
    with patch.object(posts, "_api", api), patch.object(posts, "PACE_SECONDS", 0):
        result = posts.send(post.pk)
    post.refresh_from_db()
    assert result == {"sent": 2, "failed": 1}
    assert post.status == "sent" and post.recipients == 3 and post.channel_message_id == 11
    methods = [c[0] for c in api.calls]
    assert methods.count("sendMessage") == 3 and "pinChatMessage" in methods
    assert api.calls[0][1]["chat_id"] == "@nutrizone_uz" and api.calls[0][1]["parse_mode"] == "HTML"
    assert post.last_error == ""  # a customer who blocked the bot is counted, not reported


def test_photo_uploaded_once_then_reused_and_long_text_split(settings_bot):
    _customer(111, "+998900000001")
    _customer(222, "+998900000002")
    long_body = "x" * 1500
    post = TelegramPost.objects.create(title="Uzun", body=long_body, to_customers=True, status="queued",
                                       image=SimpleUploadedFile("p.png", PNG, content_type="image/png"), buttons=[{"text": "Sayt", "url": "https://nutrizone.uz"}])
    api = FakeApi()
    with patch.object(posts, "_api", api), patch.object(posts, "PACE_SECONDS", 0):
        posts.send(post.pk)
    photos = [c for c in api.calls if c[0] == "sendPhoto"]
    texts = [c for c in api.calls if c[0] == "sendMessage"]
    assert photos[0][2] is True and photos[1][2] is False and photos[1][1]["photo"] == "big"  # uploaded once, then file_id
    assert all("caption" not in c[1] for c in photos) and all("reply_markup" not in c[1] for c in photos)
    assert all(c[1]["text"] == long_body and "reply_markup" in c[1] for c in texts)  # buttons on the last message


def test_only_queued_posts_are_sent(settings_bot):
    post = TelegramPost.objects.create(title="d", body="x", to_customers=True, status="draft")
    with patch.object(posts, "_api", FakeApi()):
        assert posts.send(post.pk) == {"skipped": True}


def test_composer_pages_render(admin_client):
    assert admin_client.get("/django-admin/telegram_bot/telegrampost/add/").status_code == 200
    assert admin_client.get("/django-admin/telegram_bot/telegrampost/").status_code == 200
