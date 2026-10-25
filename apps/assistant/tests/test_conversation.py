"""The advisor holds a conversation: small talk, introductions, complaints, goodbyes, a name, and a helpful reply
when it doesn't understand -- without ever hijacking a real product question."""
from __future__ import annotations

import pytest

from apps.assistant.infrastructure.advisor import talk
from apps.assistant.infrastructure.advisor.engine import answer

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("text, loc, last", [
    ("qalaysiz", "uz", "talk_how_are_you"), ("как дела?", "ru", "talk_how_are_you"), ("sen kimsan", "uz", "talk_who"),
    ("what can you do", "en", "talk_abilities"), ("buyurtmam kelmadi, jahlim chiqdi", "uz", "talk_complaint"),
    ("xayr", "uz", "talk_bye"), ("ok", "uz", "talk_ack"), ("Maslahatlar markazi", "uz", "talk_guides"),
])
def test_small_talk_gets_a_human_answer(text, loc, last):
    reply, ids, _chips, meta = answer({"name": "Otabek"}, text, loc)
    assert meta["last"] == last and not ids and reply


def test_a_signed_in_customer_is_greeted_by_name():
    reply, *_r = answer({"name": "Otabek"}, "salom", "uz")
    assert reply.startswith("Assalomu alaykum, Otabek!")


def test_product_questions_are_never_small_talk():
    assert talk.intent("yomon emas, kreatin nima uchun kerak?") is None
    assert talk.intent("ha, protein qanday ichiladi") is None
    assert talk.intent("okay so how much protein do I need per day for muscle gain") is None  # too long to be chit-chat


def test_an_off_topic_sentence_gets_a_clarifying_answer_not_a_random_fact():
    reply, ids, chips, meta = answer({}, "bugun ob-havo qanday bo'ladi ertaga", "uz")
    assert meta["last"] == "unclear" and not ids and chips and "tushunmadim" in reply


def test_complaints_offer_a_person():
    reply, *_r = answer({}, "terrible service, not working", "en")
    assert "sorry" in reply.lower()
