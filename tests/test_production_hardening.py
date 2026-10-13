"""Production hardening: the API map is private unless explicitly enabled."""
from __future__ import annotations

import importlib

import pytest
from django.test import Client, override_settings
from django.urls import clear_url_caches


def _reload_urls():
    import config.urls

    clear_url_caches()
    importlib.reload(config.urls)


@pytest.mark.django_db
def test_api_docs_are_not_served_when_disabled():
    try:
        with override_settings(API_DOCS_ENABLED=False):
            _reload_urls()
            client = Client()
            assert client.get("/api/schema/").status_code == 404
            assert client.get("/api/docs/swagger/").status_code == 404
            assert client.get("/health/live").status_code == 200  # the rest of the site still routes
    finally:
        _reload_urls()
