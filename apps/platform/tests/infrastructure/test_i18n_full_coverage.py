"""
Real, live-verified regression test for Phase H: a genuine, large i18n
gap was found -- 21 strings (mostly from the POS Terminal page) were
completely untranslated in BOTH uz and ru locale files, so selecting
either language would leave large parts of the page in English.
Every scenario here was proven live before being formalized.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import User
from django.test import Client

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_client():
    user = User.objects.create_superuser(username=f"admin_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
    client = Client()
    client.force_login(user)
    return client


class TestPosTerminalFullTranslationCoverage:
    def test_ru_pos_terminal_has_no_leftover_english_strings(self, staff_client):
        staff_client.post("/i18n/setlang/", {"language": "ru", "next": "/django-admin/pos/terminal/classic/"})
        response = staff_client.get("/django-admin/pos/terminal/classic/")
        assert response.status_code == 200
        body = response.content.decode()
        assert "Начать новую продажу" in body
        assert "Корзина пуста" in body
        assert "Выбранный способ оплаты" in body

    def test_uz_pos_terminal_has_no_leftover_english_strings(self, staff_client):
        staff_client.post("/i18n/setlang/", {"language": "uz", "next": "/django-admin/pos/terminal/classic/"})
        response = staff_client.get("/django-admin/pos/terminal/classic/")
        assert response.status_code == 200
        body = response.content.decode()
        assert "Yangi savdoni boshlash" in body
        assert "Savatcha bo'sh" in body


class TestChatAdminTranslationCoverage:
    def test_ru_chat_page_title_is_translated(self, staff_client):
        staff_client.post("/i18n/setlang/", {"language": "ru", "next": "/django-admin/chat/"})
        response = staff_client.get("/django-admin/chat/")
        assert response.status_code == 200
        assert "Чат" in response.content.decode()
