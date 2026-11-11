"""Feelings in the free advisor (talk.py) and replying in the language the shopper wrote in (engine.detect_locale)."""
from __future__ import annotations

import pytest

from apps.assistant.infrastructure.advisor import engine, talk


@pytest.mark.parametrize("text, key", [
    ("juda qimmat ekan", "price"), ("дорого очень", "price"), ("too expensive", "price"),
    ("charchadim natija yo'q", "down"), ("нет мотивации", "down"),
    ("yomon xizmat", "complaint"), ("rahmat zo'r ekan", "praise"),
    ("uyqum yomon", None),  # a health question, not a complaint
])
def test_feelings(text, key):
    assert talk.intent(text) == key


@pytest.mark.parametrize("text, fallback, expected", [
    ("Привет, что лучше для похудения?", "uz", "ru"),
    ("kreatin qanday ichiladi", "ru", "uz"),
    ("what is the best protein for women", "uz", "en"),
    ("қандай протеин яхши", "ru", "uz"),
    ("ok", "ru", "ru"),
    ("protein", "en", "en"),
])
def test_detect_locale(text, fallback, expected):
    assert engine.detect_locale(text, fallback) == expected
