"""Knowledge part 11 (migration 0018): the replay gaps answer from the knowledge base, the tone layer no longer
apologises for questions about a product's state, and "hi" is a greeting only as a word."""
from __future__ import annotations

import importlib

import pytest
from django.apps import apps as django_apps

from apps.assistant.infrastructure.advisor import nlu, tone
from apps.assistant.infrastructure.advisor.engine import answer
from apps.assistant.infrastructure.migrations import _expert_more
from apps.assistant.infrastructure.models import KnowledgeEntry

pytestmark = pytest.mark.django_db

MIGRATION = importlib.import_module("apps.assistant.infrastructure.migrations.0018_expert_more_knowledge")


@pytest.fixture
def more_kb():
    MIGRATION.seed(django_apps, None)


def test_entries_are_complete():
    for topic, priority, title, questions, keywords, uz, ru, en in _expert_more.E:
        assert title in _expert_more.TITLES and questions and keywords and uz and ru and en


@pytest.mark.parametrize("text, loc, title", [
    ("sharh yozsam coin beriladimi", "uz", "Sharh yozib coin olish"),
    ("Как получить коины за отзыв", "ru", "Sharh yozib coin olish"),
    ("oshqozonim og'riydi protein ichsam bo'ladimi", "uz", "Oshqozon og'rig'i, gastrit va protein"),
    ("pishgan tuxumda qancha oqsil bor", "uz", "Oddiy ovqatlarda qancha oqsil bor"),
    ("kaloriya qanday hisoblanadi", "uz", "Kaloriyani qanday hisoblash"),
    ("ozish uchun kechqurun nima yeyish kerak", "uz", "Ozishda kechki ovqat"),
    ("boksyorga qaysi sport ozuqasi kerak", "uz", "Kurash, boks va yakkakurash uchun sport ozuqasi"),
    ("futbolchiga nima kerak", "uz", "Futbol va jamoaviy sport uchun sport ozuqasi"),
    ("vegetarianman oqsilni qayerdan olaman", "uz", "Vegetarianlar uchun oqsil manbalari"),
    ("где взять белок вегетарианцу", "ru", "Vegetarianlar uchun oqsil manbalari"),
    ("Как вернуть товар если не подошел вкус", "ru", "Mahsulotni qaytarish va almashtirish"),
])
def test_replay_gaps_get_the_knowledge_answer(more_kb, text, loc, title):
    reply, _ids, _chips, meta = answer({}, text, loc)
    assert meta["last"] == "knowledge" and reply == KnowledgeEntry.objects.get(title=title).answer(loc)


def test_review_coin_entry_states_the_per_order_rule():
    uz = next(e for e in _expert_more.E if e[2] == "Sharh yozib coin olish")[5]
    assert "Har bir buyurtma" in uz and "Har qanday baho" in uz and "1 000" in uz


@pytest.mark.parametrize("text, expected", [
    ("proteinning muddati o'tgan bo'lsa ichsa bo'ladimi", None),
    ("просроченный протеин можно пить", None),
    ("muddati o'tgan protein keldi", "upset"),
    ("qadoq singan keldi", "upset"),
    ("вы продали просроченный протеин", "upset"),
    ("buyurtmam hali kelmadi", "upset"),
])
def test_product_state_words_are_upset_only_when_it_came_that_way(text, expected):
    assert tone.mood(text) == expected


def test_hi_is_a_greeting_only_as_a_word():
    assert nlu.parse("hi").intent == "greet"
    assert nlu.parse("kaloriya qanday hisoblanadi").intent != "greet"
