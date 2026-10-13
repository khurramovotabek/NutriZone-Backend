from __future__ import annotations

import pytest

from apps.products.infrastructure.health import (
    check_products_cache,
    check_products_event_registration,
    check_products_media_storage,
    check_products_outbox,
    check_products_repository,
    check_products_search,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_check_products_repository_healthy():
    ok, detail = check_products_repository()
    assert ok is True
    assert detail == "ok"


def test_check_products_cache_round_trips():
    ok, detail = check_products_cache()
    assert ok is True


def test_check_products_outbox_reports_pending_count():
    ok, detail = check_products_outbox()
    assert ok is True
    assert "pending" in detail


def test_check_products_search_executes_without_error():
    ok, detail = check_products_search()
    assert ok is True


def test_check_products_media_storage_round_trips(tmp_path, monkeypatch):
    from core.storage import LocalDiskBackend

    monkeypatch.setattr("core.storage.get_storage_backend", lambda: LocalDiskBackend(root=tmp_path))
    ok, detail = check_products_media_storage()
    assert ok is True


def test_check_products_event_registration_after_import():
    import shared.event_contracts.products  # noqa: F401 -- ensures registration has run

    ok, detail = check_products_event_registration()
    assert ok is True
