"""AI bilimlar bazasi (search, tools, the free advisor using it), the new profile/category tools and read-aloud (Azure)."""
from __future__ import annotations

import json
import uuid
from unittest import mock

import pytest
from django.contrib.auth.models import User as StaffUser
from django.test import Client, override_settings

from apps.assistant.infrastructure import knowledge, tools, tts
from apps.assistant.infrastructure.models import KnowledgeEntry

pytestmark = pytest.mark.django_db


def _entry(**kw):
    data = {"topic": "promo", "title": "Oktabr aksiyasi", "questions": "aksiya bormi\nскидки есть\nany sale", "keywords": "aksiya, chegirma, скидка, sale",
            "answer_uz": "Oktabr oxirigacha barcha kreatinlarga 10% chegirma.", "answer_ru": "До конца октября скидка 10% на весь креатин.", "answer_en": "10% off all creatine until the end of October.",
            "priority": 90}
    data.update(kw)
    return KnowledgeEntry.objects.create(**data)


class TestSearch:
    def test_matches_in_three_languages_and_respects_expiry(self):
        e = _entry()
        assert knowledge.search("aksiya bormi?")[0].entry == e
        assert knowledge.search("скидки есть?")[0].entry == e
        assert knowledge.search("is there any sale")[0].entry == e
        from datetime import date

        e.valid_until = date(2020, 1, 1)
        e.save()
        assert all(h.entry != e for h in knowledge.search("aksiya bormi?"))

    def test_tool_answers_in_the_customer_language_and_counts_use(self):
        e = _entry()
        out, err = tools.run("search_knowledge", {"query": "скидки есть"}, "ru")
        assert not err and out["results"][0]["answer"].startswith("До конца октября")
        e.refresh_from_db()
        assert e.uses == 1

    def test_free_advisor_answers_from_the_knowledge_base(self):
        from apps.assistant.infrastructure.advisor.engine import answer

        _entry()
        reply, ids, chips, meta = answer({}, "aksiya bormi?", "uz")
        assert "10% chegirma" in reply and meta["last"] == "knowledge"  # asked exactly as taught: the shop's own answer wins
        _entry(topic="faq", title="Ish kunlari", questions="bayramda ishlaysizmi", keywords="bayram, праздник", answer_uz="Bayram kunlari ham ishlaymiz.", priority=60)
        reply, *_rest, meta = answer({}, "bayramda ishlaysizmi", "uz")
        assert reply == "Bayram kunlari ham ishlaymiz." and meta["last"] == "knowledge"


class TestTools:
    def test_profile_for_guest_and_signed_in_customer(self):
        from apps.identity.infrastructure.models import User

        out, _ = tools.run("get_customer_profile", {}, "uz")
        assert out == {"signed_in": False}
        u = User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", status="active", full_name="Aziza Karimova", height_cm=165, weight_kg=58)
        token = tools.CURRENT_CUSTOMER.set(u.id)
        try:
            out, _ = tools.run("get_customer_profile", {}, "uz")
        finally:
            tools.CURRENT_CUSTOMER.reset(token)
        assert out["signed_in"] and out["first_name"] == "Aziza" and out["height"] == 165 and "recent_purchases" in out

    def test_category_and_brand_info(self):
        from apps.products.infrastructure import models as p

        c = p.Category.objects.create(id=uuid.uuid4())
        p.CategoryTranslation.objects.create(id=uuid.uuid4(), category=c, locale_code="uz", name="Kreatin", slug=f"k-{uuid.uuid4().hex[:5]}", description="Kuch va chidamlilik uchun.")
        out, err = tools.run("get_category_info", {"name": "kreatin"}, "uz")
        assert not err and out["found"] and out["description"] == "Kuch va chidamlilik uchun."
        out, _ = tools.run("get_brand_info", {"name": "nonexistent brand"}, "uz")
        assert out == {"found": False}

    def test_every_tool_has_a_handler(self):
        assert {t["name"] for t in tools.TOOLS} == set(tools.HANDLERS)


class TestTts:
    def test_clean_reads_like_speech(self):
        assert tts.clean("**Kreatin** 💪\n• kuniga 5 g\n• suv bilan https://x.uz") == "Kreatin. kuniga 5 g. suv bilan."

    @override_settings(AZURE_SPEECH_KEY="k" * 32, AZURE_SPEECH_REGION="westeurope")
    def test_endpoint_calls_azure_with_the_uzbek_voice_and_caches(self, tmp_path, settings):
        settings.MEDIA_ROOT = str(tmp_path)
        fake = mock.Mock(status_code=200, content=b"ID3mp3")
        with mock.patch("requests.post", return_value=fake) as post:
            c = Client()
            h = {"HTTP_X_ASSISTANT_CLIENT": "c" * 20}
            r = c.post("/api/v1/assistant/tts", json.dumps({"text": "Assalomu alaykum!", "locale": "uz"}), content_type="application/json", **h)
            assert r.status_code == 200 and r["Content-Type"] == "audio/mpeg" and r.content == b"ID3mp3"
            ssml = post.call_args.kwargs["data"].decode()
            assert "uz-UZ-MadinaNeural" in ssml and "westeurope.tts.speech.microsoft.com" in post.call_args.args[0]
            c.post("/api/v1/assistant/tts", json.dumps({"text": "Assalomu alaykum!", "locale": "uz"}), content_type="application/json", **h)
            assert post.call_count == 1  # second time from the cache
        assert Client().get("/api/v1/assistant/status").json()["data"]["tts"] is True

    def test_disabled_without_a_key(self):
        r = Client().post("/api/v1/assistant/tts", json.dumps({"text": "x", "locale": "uz"}), content_type="application/json", HTTP_X_ASSISTANT_CLIENT="c" * 20)
        assert r.status_code == 503


def test_dashboard_pages():
    user = StaffUser.objects.create_superuser(username=f"kb_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
    c = Client()
    c.force_login(user)
    e = _entry()
    assert c.get("/django-admin/assistant/knowledgeentry/").status_code == 200
    assert c.get(f"/django-admin/assistant/knowledgeentry/{e.id}/change/").status_code == 200
    r = c.post("/django-admin/assistant/knowledgeentry/add/", {"topic": "faq", "title": "Ish vaqti", "questions": "soat nechagacha ishlaysiz", "keywords": "ish vaqti",
                                                               "answer_uz": "Har kuni 9:00 dan 21:00 gacha.", "answer_ru": "", "answer_en": "", "priority": "50", "is_active": "on"})
    assert r.status_code == 302 and KnowledgeEntry.objects.filter(title="Ish vaqti", created_by=user.username).exists()
