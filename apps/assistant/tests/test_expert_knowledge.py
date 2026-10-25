"""The assistant as a sports-nutrition and vitamin expert: named vitamins and minerals, the seeded expert knowledge
(migration 0006) answering real questions in uz / ru / en, and the safety answer only when a condition is really named."""
from __future__ import annotations

import importlib

import pytest

from apps.assistant.infrastructure import knowledge
from apps.assistant.infrastructure.advisor import kb, nlu
from apps.assistant.infrastructure.advisor.engine import answer
from apps.assistant.infrastructure.models import KnowledgeEntry

pytestmark = pytest.mark.django_db

EXPERT = importlib.import_module("apps.assistant.infrastructure.migrations.0006_expert_knowledge")


@pytest.fixture
def expert_kb():
    """The seeded expert entries, whether or not the test database ran the data migration."""
    for topic, priority, title, questions, keywords, uz, ru, en in EXPERT.ENTRIES:
        KnowledgeEntry.objects.get_or_create(title=title, defaults={"topic": topic, "priority": priority, "questions": questions, "keywords": keywords,
                                                                    "answer_uz": uz, "answer_ru": ru, "answer_en": en})


def _concepts(text: str) -> list[str]:
    t = nlu.normalize(text)
    return nlu.concepts_in(f"{t} {t.translate(nlu.LATIN_FROM_CYR)}")


@pytest.mark.parametrize("text, kind", [
    ("D vitamini qancha ichish kerak?", "vitamin_d"), ("витамин Д3 сколько пить", "vitamin_d"), ("vitamin c for colds", "vitamin_c"),
    ("B12 kimga kerak", "vitamin_b12"), ("rux qanday ichiladi", "zinc"), ("магний для сна", "magnesium"), ("kamqonlik uchun temir", "iron"),
    ("ZMA nima", "zma"), ("glutamin foydasi", "glutamine"), ("ashvagandha", "ashwagandha"),
])
def test_named_vitamins_minerals_and_supplements_are_recognised(text, kind):
    assert _concepts(text)[0] == kind


def test_lookalike_words_are_not_supplements():
    assert _concepts("ruxsat bormi") == []  # "rux" (zinc) is also the start of "ruxsat" (permission)
    assert "vitamin_c" not in _concepts("can you overdose on vitamins")  # plural "vitamins" isn't vitamin C
    assert _concepts("multivitamin va D vitamini") == ["vitamin_d", "vitamin"]  # a multi asked for by name stays


def test_every_kind_has_texts_in_three_languages():
    kinds = set(nlu.CONCEPT_WORDS) | set(nlu.SPECIFIC)
    for key in ("kind_name", "why", "who", "usage"):
        for loc in ("uz", "ru", "en"):
            assert kinds <= set(kb.T[key][loc]), (key, loc, kinds - set(kb.T[key][loc]))


def test_lettered_vitamins_rank_their_own_entry_not_vitamins_in_general(expert_kb):
    assert knowledge.search("D vitamini qancha ichish kerak?")[0].entry.title == "D vitamini: kimga va qancha"
    assert knowledge.search("витамин Д3 сколько пить в день")[0].entry.title == "D vitamini: kimga va qancha"
    assert knowledge.search("B12 kimga kerak?")[0].entry.title == "B12 va B guruhi vitaminlari"
    assert knowledge.search("vitamin c")[0].entry.title == "C vitamini"


def test_how_to_questions_never_get_the_diabetes_warning(expert_kb):
    # "qanday" (how) used to match the diabetes stem "qand"; "без сахара" matched "сахар"
    for text, loc in (("Kreatin qanday ichiladi?", "uz"), ("rux qanday ichiladi", "uz"), ("протеин без сахара есть?", "ru")):
        reply, _ids, _chips, meta = answer({}, text, loc)
        assert meta["last"] != "health" and "diabet" not in reply.lower() and "диабет" not in reply.lower(), text
    reply, *_r, meta = answer({}, "qandli diabetim bor, protein ichsam bo'ladimi?", "uz")
    assert meta["last"] == "health" and "endokrinolog" in reply


@pytest.mark.parametrize("text, loc, title", [
    ("how much vitamin d should I take", "en", "D vitamini: kimga va qancha"),
    ("mushagim tortishyapti nima ichay", "uz", "Magniy: uyqu va mushak tortishishi"),
    ("магний для сна", "ru", "Magniy: uyqu va mushak tortishishi"),
    ("immunitet uchun nima ichish kerak", "uz", "Immunitet uchun nima ichish kerak"),
    ("kreatin sochni to'kadimi", "uz", "Kreatin haqida miflar"),
    ("bcaa kerakmi agar protein ichsam", "uz", "BCAA yoki EAA"),
    ("ramazonda protein qachon ichiladi", "uz", "Ramazonda mashg'ulot va qo'shimchalar"),
    ("16 yoshda protein ichsa bo'ladimi", "uz", "O'smirlar uchun sport ozuqasi"),
    ("will i fail a drug test", "en", "Professional sportchilar va doping nazorati"),
    ("proteindan dam bo'lyapman", "uz", "Probiotik va ichak salomatligi"),
])
def test_expert_questions_get_the_expert_answer(expert_kb, text, loc, title):
    reply, _ids, _chips, meta = answer({}, text, loc)
    entry = KnowledgeEntry.objects.get(title=title)
    assert meta["last"] == "knowledge" and reply == entry.answer(loc)


def test_a_body_goal_still_builds_a_personal_stack(expert_kb):
    reply, *_r, meta = answer({}, "massa olish uchun nima tavsiya qilasiz", "uz")
    assert meta["last"] == "ask"  # asks for height / weight / age, then builds the stack


def test_expert_entries_are_complete():
    titles = [e[2] for e in EXPERT.ENTRIES]
    assert len(titles) == len(set(titles)) >= 45
    for topic, _p, title, questions, keywords, uz, ru, en in EXPERT.ENTRIES:
        assert topic in dict(KnowledgeEntry.TOPICS) and questions.count("\n") >= 2 and len(keywords) <= 300 and uz and ru and en, title
