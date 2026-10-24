"""NutriZone Brain v2: live-data answers of the free advisor (price, branch stock, compare, promo, contacts, safety)."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.assistant.infrastructure.advisor import brain
from apps.assistant.infrastructure.advisor.engine import answer

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _fresh_index():
    brain._CACHE.clear()
    brain._CACHE["at"] = 0.0
    yield
    brain._CACHE.clear()
    brain._CACHE["at"] = 0.0


def _store(name="LifeSport Andijon", city="Andijon", district=""):
    from apps.stores.infrastructure.models import Store

    return Store.objects.create(id=uuid.uuid4(), name=name, slug=f"s-{uuid.uuid4().hex[:6]}", kind="store", status="active", city=city, district=district,
                                latitude=40.77, longitude=72.36, phone_numbers=["+998901112233"])


def test_health_conditions_get_a_safety_first_answer():
    reply, ids, chips, meta = answer({}, "yurak og'rig'im bor, pre workout ichsam bo'ladimi?", "uz")
    assert meta["last"] == "health" and "tavsiya etilmaydi" in reply
    reply, *_r, meta = answer({}, "можно ли ребенку креатин", "ru")
    assert meta["last"] == "health" and "18" in reply


def test_compare_two_kinds():
    reply, *_r, meta = answer({}, "kreatin va protein farqi nima?", "uz")
    assert meta["last"] == "compare" and "Kreatin" in reply and "Protein" in reply


def test_contacts_and_hours_and_branch_pin():
    _store()
    reply, *_r, meta = answer({}, "telefon raqamingiz?", "uz")
    assert meta["last"] == "contacts"
    reply, *_r, meta = answer({}, "Andijon filiali soat nechagacha ishlaydi?", "uz")
    assert meta["last"] == "hours" and "LifeSport Andijon" in reply and meta["_venues"][0]["lat"] == 40.77
    reply, *_r, meta = answer({}, "Andijon filiali qayerda?", "uz")
    assert meta["_venues"][0]["title"] == "LifeSport Andijon"


def test_aliases_and_glued_words():
    assert "optimum nutrition gold standard goldstandart" in brain._variants("on gold standard")
    assert any("goldstand" in v.replace(" ", "") for v in brain._variants("gold standard"))


def test_filler_words_are_dropped_from_the_query():
    assert brain._clean_query("Olimp whey narxi qancha?") == "olimp whey"
    assert brain._clean_query("Сколько стоит креатин?") == "креатин"


def test_turn_returns_venues_for_the_bot():
    from apps.assistant.infrastructure.advisor.engine import _turn_sync
    from apps.assistant.infrastructure.models import AssistantConversation

    _store()
    conv = AssistantConversation.objects.create(client_key="tg:1", channel="telegram", locale="uz", engine="local")
    out = _turn_sync(conv.id, "Andijon filiali qayerda?")
    assert out["venues"] and out["venues"][0]["title"] == "LifeSport Andijon"
    conv.refresh_from_db()
    assert "_venues" not in conv.meta


def test_why_questions_explain_the_kind():
    reply, *_r, meta = answer({}, "зачем креатин?", "ru")
    assert meta["last"] == "why" and "Кому нужно" in reply and "3–5 г" in reply


def test_cheapest_sorts_by_price_and_follow_up_reuses_the_kind(monkeypatch):
    calls = []

    def fake_search(query="", loc="uz", limit=4, category=None, brand=None, sort=None, on_sale=False, in_stock=True):
        calls.append((query, sort))
        return [{"id": str(uuid.uuid4()), "name": "Whey A", "price": Decimal("500000"), "old": None, "discount": None, "variant": None, "in_stock": True}]

    monkeypatch.setattr(brain, "_search", fake_search)
    reply, ids, _c, meta = answer({}, "eng arzon protein qaysi?", "uz")
    assert meta["last"] == "cheap" and calls[-1] == ("whey protein", "price") and len(ids) == 1
    reply, *_r, meta = answer(meta, "Eng arzoni qaysi?", "uz")
    assert meta["last"] == "cheap" and calls[-1] == ("whey protein", "price")


def test_asking_for_details_uses_the_goal_in_the_example():
    reply, *_r, meta = answer({}, "massa olish uchun nima tavsiya qilasiz?", "uz")
    assert meta["last"] == "ask" and "mushak massasi, haftada 3 marta" in reply and ", ozish," not in reply
