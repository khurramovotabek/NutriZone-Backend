"""The assistant in Telegram groups: only questions addressed to the bot get an answer."""
from __future__ import annotations

import pytest

from apps.telegram_bot.interfaces import callback_router

pytestmark = [pytest.mark.django_db]


def _msg(text, reply_to_bot=False):
    m = {"chat": {"id": -100123, "type": "supergroup"}, "from": {"id": 77, "first_name": "Ali", "language_code": "uz"}, "text": text}
    if reply_to_bot:
        m["reply_to_message"] = {"from": {"is_bot": True, "username": "nutrizone_bot"}}
    return m


@pytest.fixture
def sent(monkeypatch, settings):
    settings.TELEGRAM_BOT_USERNAME = "nutrizone_bot"
    settings.ASSISTANT_ENABLED = True
    settings.ANTHROPIC_API_KEY = ""
    out = []
    monkeypatch.setattr(callback_router, "_send", lambda chat_id, text, keyboard=None: out.append((chat_id, text, keyboard)))
    return out


def test_ignores_group_chatter(sent):
    assert callback_router.group_question(_msg("bugun mashg'ulot zo'r bo'ldi")) is False
    assert sent == []


def test_answers_a_mention(sent):
    assert callback_router.group_question(_msg("@nutrizone_bot do'konlaringiz qayerda?")) is True
    chat_id, text, keyboard = sent[0]
    assert chat_id == -100123 and text.startswith("Ali, ") and keyboard[-1][0]["url"] == "https://t.me/nutrizone_bot"


def test_answers_a_reply_to_the_bot(sent):
    assert callback_router.group_question(_msg("massa uchun nima tavsiya qilasiz?", reply_to_bot=True)) is True
