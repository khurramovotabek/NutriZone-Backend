from __future__ import annotations

import pytest
from django.http import QueryDict

from apps.geo.interfaces.api.v1.filters import (
    parse_bounding_box_params,
    parse_pagination,
    parse_reverse_geocode_params,
    parse_search_params,
    parse_uuid_param,
)
from common.exceptions import ValidationFailed

pytestmark = pytest.mark.unit


def _qd(params: dict) -> QueryDict:
    qd = QueryDict(mutable=True)
    for key, value in params.items():
        qd[key] = value
    return qd


class TestPagination:
    def test_defaults(self):
        params = parse_pagination(_qd({}))
        assert params.page == 1
        assert params.page_size == 50

    def test_caps_page_size(self):
        params = parse_pagination(_qd({"page_size": "9999"}))
        assert params.page_size == 200

    def test_invalid_page_raises(self):
        with pytest.raises(ValidationFailed):
            parse_pagination(_qd({"page": "not-a-number"}))


class TestUuidParam:
    def test_valid_uuid(self):
        import uuid

        value = str(uuid.uuid4())
        assert str(parse_uuid_param(value, "field")) == value

    def test_none_returns_none(self):
        assert parse_uuid_param(None, "field") is None

    def test_invalid_uuid_raises(self):
        with pytest.raises(ValidationFailed):
            parse_uuid_param("not-a-uuid", "field")


class TestSearchParams:
    def test_defaults(self):
        params = parse_search_params(_qd({}))
        assert params.query == ""
        assert params.geo_level is None

    def test_valid_geo_level(self):
        params = parse_search_params(_qd({"filter[geo_level]": "city"}))
        assert params.geo_level == "city"

    def test_invalid_geo_level_raises(self):
        with pytest.raises(ValidationFailed):
            parse_search_params(_qd({"filter[geo_level]": "planet"}))


class TestBoundingBoxParams:
    def test_valid_box(self):
        box = parse_bounding_box_params(_qd({"ne_lat": "42", "ne_lng": "70", "sw_lat": "41", "sw_lng": "69"}))
        assert box["ne_lat"] == 42.0

    def test_missing_field_raises(self):
        with pytest.raises(ValidationFailed):
            parse_bounding_box_params(_qd({"ne_lat": "42"}))

    def test_non_numeric_raises(self):
        with pytest.raises(ValidationFailed):
            parse_bounding_box_params(_qd({"ne_lat": "x", "ne_lng": "70", "sw_lat": "41", "sw_lng": "69"}))


class TestReverseGeocodeParams:
    def test_valid_params(self):
        lat, lng = parse_reverse_geocode_params(_qd({"latitude": "41.3", "longitude": "69.2"}))
        assert lat == 41.3
        assert lng == 69.2

    def test_missing_params_raises(self):
        with pytest.raises(ValidationFailed):
            parse_reverse_geocode_params(_qd({"latitude": "41.3"}))
