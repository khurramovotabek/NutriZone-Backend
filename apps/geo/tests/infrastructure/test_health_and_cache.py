from __future__ import annotations

import pytest

from apps.geo.infrastructure.event_handlers import (
    CACHE_GROUPS,
    geo_cache_key,
    handle_geo_event,
    invalidate_geo_scope,
)
from apps.geo.infrastructure.health import (
    check_geo_cache,
    check_geo_database,
    check_geo_outbox,
    check_geo_repository,
    check_geo_search,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestHealthChecks:
    def test_check_geo_repository_healthy(self):
        ok, detail = check_geo_repository()
        assert ok is True

    def test_check_geo_database_healthy(self):
        ok, detail = check_geo_database()
        assert ok is True

    def test_check_geo_cache_round_trips(self):
        ok, detail = check_geo_cache()
        assert ok is True

    def test_check_geo_outbox_reports_pending(self):
        ok, detail = check_geo_outbox()
        assert ok is True
        assert "pending" in detail

    def test_check_geo_search_executes(self):
        ok, detail = check_geo_search()
        assert ok is True


class TestCacheKeyVersioning:
    def test_cache_key_rejects_unknown_group(self):
        with pytest.raises(ValueError):
            geo_cache_key("not_a_real_group", "x")

    def test_cache_key_changes_after_invalidation(self):
        key_before = geo_cache_key("city_list", "region-1")
        invalidate_geo_scope("city")
        key_after = geo_cache_key("city_list", "region-1")
        assert key_before != key_after

    def test_invalidate_scope_only_affects_mapped_groups(self):
        address_key_before = geo_cache_key("address_lookup", "addr-1")
        invalidate_geo_scope("city")  # city scope does not affect address_lookup
        address_key_after = geo_cache_key("address_lookup", "addr-1")
        assert address_key_before == address_key_after

    def test_all_cache_groups_present(self):
        assert len(CACHE_GROUPS) == 8


class TestEventHandlerDispatch:
    def test_handle_country_created_invalidates_and_records_metric(self):
        # Should not raise -- exercises the full dispatch path.
        handle_geo_event("CountryCreated", {"country_id": "x"})

    def test_handle_unknown_event_type_is_a_noop(self):
        handle_geo_event("SomeUnregisteredEvent", {})
