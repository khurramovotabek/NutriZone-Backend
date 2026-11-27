"""Knowledge part 12 (migration 0019) and the routing around it: where-to-buy, the live coin programme, best sellers
without a kind, off-topic / quick facts, budget picks that never list a tub above the budget, and superseded duplicates."""
from __future__ import annotations

import importlib

import pytest
from django.apps import apps as django_apps

from apps.assistant.infrastructure.advisor import nlu, talk
from apps.assistant.infrastructure.advisor.engine import answer
from apps.assistant.infrastructure.migrations import _expert_pro
from apps.assistant.infrastructure.models import KnowledgeEntry

pytestmark = pytest.mark.django_db

MORE = importlib.import_module("apps.assistant.infrastructure.migrations.0018_expert_more_knowledge")
PRO = importlib.import_module("apps.assistant.infrastructure.migrations.0019_expert_pro_knowledge")


@pytest.fixture
def pro_kb():
    MORE.seed(django_apps, None)
    PRO.seed(django_apps, None)


def test_entries_are_complete():
    for _topic, _priority, title, questions, keywords, uz, ru, en in _expert_pro.E:
        assert title in _expert_pro.TITLES and questions and keywords and uz and ru and en
    titles = {e[2] for e in _expert_pro.E}
    assert set(_expert_pro.SUPERSEDES.values()) <= titles | {"Bir nechta qo'shimchani birga ichish", "Mahsulotni qaytarish va almashtirish"}


@pytest.mark.parametrize("text, loc, title", [
    ("kreatin nima", "uz", "Kreatin nima va nima beradi"),
    ("What is creatine", "en", "Kreatin nima va nima beradi"),
    ("gainer nima", "uz", "Gainer nima va kimga kerak"),
    ("qalbaki proteinni qanday ajratish mumkin", "uz", "Original mahsulotni qanday tanish"),
    ("buyurtmamni o'zgartirsam bo'ladimi", "uz", "Buyurtmani o'zgartirish"),
    ("promokod qayerga yoziladi", "uz", "Kupon kodi (promokod) qayerga yoziladi"),
    ("optom sotasizlarmi", "uz", "Optom, hamkorlik, ish va franshiza"),
    ("ishga olasizlarmi", "uz", "Optom, hamkorlik, ish va franshiza"),
    ("mahsulot tugab qolgan qachon keladi", "uz", "Mahsulot tugagan bo'lsa yoki yangi mahsulot"),
    ("energetik ichsam bo'ladimi", "uz", "Energetik ichimliklar va sport"),
    ("chekish va sport", "uz", "Chekish, nos, vape va sport"),
    ("jigar uchun nima ichish kerak", "uz", "Jigar salomatligi va sport ozuqasi"),
    ("proteindan ich qotishi", "uz", "Proteindan ich qotishi"),
    ("stress uchun nima ichish kerak", "uz", "Stress va asab uchun"),
    ("ko'z uchun vitamin", "uz", "Ko'z salomatligi uchun"),
    ("bo'y o'stirish uchun vitamin", "uz", "Bo'y o'stirish mumkinmi"),
    ("erkaklar salomatligi uchun", "uz", "Erkaklar salomatligi uchun vitaminlar"),
    ("qorin muskullari qanday chiqadi", "uz", "Qorin press kubiklari"),
    ("haftada necha marta zalga borish kerak", "uz", "Mushakni o'stirish: mashg'ulot asoslari"),
    ("kardio yoki kuch mashqi ozish uchun", "uz", "Ozish uchun kardio yoki kuch mashqi"),
    ("non yemasam ozamanmi", "uz", "Non, guruch va uglevod ozishda"),
    ("nonushtaga nima yeyish", "uz", "Nonushtaga nima yeyish kerak"),
    ("sizlarda original mahsulotmi", "uz", "Mahsulotlar originalmi?"),
    ("qon bosimi past nima ichay", "uz", "Past qon bosimi va sport ozuqasi"),
    ("mashg'ulotdan keyin bosh aylanadi", "uz", "Mashg'ulotda bosh og'rig'i va bosh aylanishi"),
    ("belim og'riydi zalda", "uz", "Bel og'rig'i va zal"),
    ("ishtaham yo'q", "uz", "Ishtahani boshqarish"),
    ("pul yechildi lekin buyurtma yo'q", "uz", "To'lov o'tmadi yoki pul yechildi"),
    ("chek bera olasizlarmi", "uz", "Chek olish"),
    ("crossfit uchun sport ozuqa", "uz", "CrossFit va funksional mashg'ulot uchun"),
    ("armrestling uchun", "uz", "Kuch sporti: armrestling, pauerlifting, og'ir atletika"),
    ("tez ozish mumkinmi", "uz", "To'g'ri ozish: kaloriya va tezlik"),
])
def test_replay_gaps_get_the_knowledge_answer(pro_kb, text, loc, title):
    reply, _ids, _chips, meta = answer({}, text, loc)
    assert meta["last"] == "knowledge" and reply == KnowledgeEntry.objects.get(title=title).answer(loc)


def test_superseded_duplicates_are_switched_off_and_their_questions_move(pro_kb):
    for old, new in _expert_pro.SUPERSEDES.items():
        assert not KnowledgeEntry.objects.filter(title=old, is_active=True).exists()
        assert KnowledgeEntry.objects.get(title=new).is_active


@pytest.mark.parametrize("text, loc", [
    ("kreatinni qayerdan olsam bo'ladi", "uz"), ("protein qayerdan sotib olsam bo'ladi", "uz"), ("где купить креатин", "ru"), ("where can i buy whey protein", "en"),
])
def test_where_to_buy_points_to_the_shop(pro_kb, text, loc):
    reply, _ids, _chips, meta = answer({}, text, loc)
    assert meta["last"] == "where_buy" and "NutriZone" in reply


def test_a_nutrient_source_question_is_not_a_purchase(pro_kb):
    *_r, meta = answer({}, "vegetarianman oqsilni qayerdan olaman", "uz")
    assert meta["last"] == "knowledge"


def test_coin_use_gets_the_live_programme_not_the_review_article(pro_kb):
    *_r, meta = answer({}, "coin qanday ishlatiladi", "uz")
    assert meta["last"] == "faq_loyalty"
    *_r, meta = answer({}, "sharh yozsam coin beriladimi", "uz")
    assert meta["last"] == "knowledge"


@pytest.mark.parametrize("text", ["ob-havo qanday", "menga she'r yoz", "futbol kim yutdi", "курс доллара"])
def test_off_topic_is_declined_politely(text):
    assert talk.intent(text) == "offtopic"


@pytest.mark.parametrize("text, expected", [("2+2 nechchi", "**4**"), ("12 * 3", "**36**"), ("10/4", "**2.5**")])
def test_simple_arithmetic_is_answered(text, expected):
    assert expected in talk.special(text, "uz")


def test_date_question_is_answered_and_division_by_zero_is_not():
    assert "Bugun" in talk.special("bugun qanday kun", "uz")
    assert talk.special("5/0", "uz") is None
    assert talk.special("kreatin qanday ichiladi", "uz") is None


def test_returns_win_over_order_status_in_russian():
    assert nlu.parse("Как вернуть заказ").intent == "faq_returns"


def test_shop_hours_are_not_the_clock():
    assert talk.special("Andijon filiali soat nechagacha ishlaydi?", "uz") is None
    assert "soat" in talk.special("soat necha", "uz")


def test_which_one_and_where_is_a_pick_not_directions(pro_kb):
    *_r, meta = answer({}, "sut mahsulotlari yoqmaydi, qornim shishadi. qaysi proteinni qayerdan olsam bo'ladi?", "uz")
    assert meta["last"] != "where_buy"


def test_an_age_alone_does_not_turn_a_safety_question_into_a_profile_form(pro_kb):
    *_r, meta = answer({}, "40 yoshda kreatin ichsa bo'ladimi", "uz")
    assert meta["last"] != "ask" and meta["profile"].get("age") == 40


def test_a_seller_request_reaches_an_operator():
    assert nlu.parse("sotuvchi bilan gaplashsam bo'ladimi").intent == "operator"
