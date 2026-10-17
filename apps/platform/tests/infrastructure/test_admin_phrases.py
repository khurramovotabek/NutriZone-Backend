"""Dashboard phrase translation (apps/platform/infrastructure/admin_i18n.py)."""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.platform.infrastructure import admin_i18n as ai

TABLE = {
    "Kanal avtopostlari": "Channel auto-posts",
    "{0} kun oldin": "{0} days ago",
    "Chek sozlamalari": "Receipt settings",
    "Muddati o'tgan partiyalar javonda: {0} ta ({1} dona)": "Expired batches on the shelf: {0} ({1} units)",
}


def t(text, lang="en"):
    return ai.translate_text(text, lang, TABLE)


class TestTranslateText:
    def test_whole_phrase(self):
        assert t("Kanal avtopostlari") == "Channel auto-posts"

    def test_apostrophe_kinds_and_spacing_are_ignored(self):
        assert t("  Muddati o‘tgan partiyalar javonda: 2 ta (5 dona)\n") == "  Expired batches on the shelf: 2 (5 units)\n"

    def test_numbers_are_kept(self):
        assert t("4 kun oldin") == "4 days ago"

    def test_separators_and_django_prefixes(self):
        assert t("Chek sozlamalari | Change Chek sozlamalari | NutriZone") == "Receipt settings | Change Receipt settings | NutriZone"
        assert t("Изменить Chek sozlamalari") == "Изменить Receipt settings"

    def test_decoration_is_kept(self):
        assert t("☠️ Kanal avtopostlari →") == "☠️ Channel auto-posts →"

    def test_unknown_text_and_data_are_left_alone(self):
        assert t("Optimum Nutrition Gold Standard") is None
        assert t("Kanal avtopostlari haqida") is None  # only whole phrases, never words inside one
        assert t("12 345") is None

    def test_html_skips_scripts_textareas_and_notranslate(self, monkeypatch):
        monkeypatch.setattr(ai, "catalog", lambda lang: (TABLE, "v"))
        html = (
            '<h1 title="Chek sozlamalari">Kanal avtopostlari</h1><script>var a="Kanal avtopostlari";</script>'
            '<textarea placeholder="Chek sozlamalari">Kanal avtopostlari</textarea><span translate="no">Kanal avtopostlari</span>'
            '<input type="submit" value="Chek sozlamalari"><input name="q" value="Chek sozlamalari">'
        )
        out = ai.translate_html(html, "en")
        assert '<h1 title="Receipt settings">Channel auto-posts</h1>' in out
        assert 'var a="Kanal avtopostlari"' in out
        assert '<textarea placeholder="Receipt settings">Kanal avtopostlari</textarea>' in out
        assert '<span translate="no">Kanal avtopostlari</span>' in out
        assert '<input type="submit" value="Receipt settings">' in out
        assert '<input name="q" value="Chek sozlamalari">' in out  # user input values are never touched


@pytest.mark.django_db
class TestMiddleware:
    @pytest.fixture(autouse=True)
    def _enabled(self, settings):
        settings.ADMIN_PHRASES_ENABLED = True

    @pytest.fixture
    def staff(self):
        return get_user_model().objects.create_superuser("i18n_admin", "i18n@example.com", "x" * 20)

    def test_dashboard_is_translated_in_english(self, staff):
        c = Client()
        c.force_login(staff)
        c.cookies["django_language"] = "en"
        body = c.get("/django-admin/", HTTP_ACCEPT_LANGUAGE="en").content.decode()
        assert "Bugungi vazifalar" not in body
        assert "Today's tasks" in body

    def test_phrase_catalog_script(self):
        resp = Client().get("/django-admin/i18n/phrases.en.js")
        assert resp.status_code == 200
        assert resp["Content-Type"].startswith("application/javascript")
        assert b"window.NZ_PHRASES=" in resp.content


def test_confirmation_attributes_are_translated(monkeypatch):
    monkeypatch.setattr(ai, "catalog", lambda lang: ({**TABLE, "Suhbat arxivga o'tkazilsinmi?": "Move the chat to the archive?"}, "v"))
    out = ai.translate_html('<button data-nzi-confirm="Suhbat arxivga o&#x27;tkazilsinmi?">x</button><button data-confirm="Kanal avtopostlari">y</button>', "en")
    assert 'data-nzi-confirm="Move the chat to the archive?"' in out
    assert 'data-confirm="Channel auto-posts"' in out
