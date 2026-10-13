from __future__ import annotations

import pytest

from apps.geo.domain.exceptions import InvalidHierarchy, InvalidTimezone
from apps.geo.domain.services import (
    AddressNormalizer,
    DuplicateAddressDetector,
    GeoDistanceCalculator,
    HierarchyValidator,
    TimezoneValidator,
)
from apps.geo.domain.value_objects import Coordinate, Timezone
from common.exceptions import ValidationFailed

pytestmark = pytest.mark.unit


class TestTimezoneValidator:
    def test_valid_iana_timezone(self):
        TimezoneValidator.validate(Timezone("Asia/Tashkent"))

    def test_invalid_iana_timezone_raises(self):
        with pytest.raises(InvalidTimezone):
            TimezoneValidator.validate(Timezone("Fake/Place"))

    def test_utc_is_valid(self):
        TimezoneValidator.validate(Timezone("Etc/UTC"))


class TestGeoDistanceCalculator:
    def test_distance_to_self_is_zero(self):
        point = Coordinate.of(41.3, 69.2)
        assert GeoDistanceCalculator.distance_meters(point, point) == pytest.approx(0, abs=1e-6)

    def test_distance_between_known_points(self):
        # Tashkent to Samarkand is roughly 260km.
        tashkent = Coordinate.of(41.2995, 69.2401)
        samarkand = Coordinate.of(39.6270, 66.9750)
        distance_km = GeoDistanceCalculator.distance_meters(tashkent, samarkand) / 1000
        assert 250 < distance_km < 290

    def test_distance_is_symmetric(self):
        a, b = Coordinate.of(0, 0), Coordinate.of(1, 1)
        assert GeoDistanceCalculator.distance_meters(a, b) == pytest.approx(GeoDistanceCalculator.distance_meters(b, a))


class TestAddressNormalizer:
    def test_format_assembles_lines(self):
        formatted = AddressNormalizer.format("123 Main St", "Apt 4", "Tashkent", "Tashkent Region", "Uzbekistan", "100000")
        assert "123 Main St" in formatted.single_line
        assert "Uzbekistan" in formatted.single_line

    def test_format_omits_none_line2(self):
        formatted = AddressNormalizer.format("123 Main St", None, "Tashkent", None, "Uzbekistan", None)
        assert "123 Main St" in formatted.lines

    def test_normalized_signature_is_case_insensitive(self):
        sig1 = AddressNormalizer.normalized_signature("123 Main St", None, "city-1", None)
        sig2 = AddressNormalizer.normalized_signature("123 MAIN ST", None, "city-1", None)
        assert sig1 == sig2

    def test_normalized_signature_collapses_whitespace(self):
        sig1 = AddressNormalizer.normalized_signature("123   Main   St", None, "city-1", None)
        sig2 = AddressNormalizer.normalized_signature("123 Main St", None, "city-1", None)
        assert sig1 == sig2

    def test_normalized_signature_differs_by_city(self):
        sig1 = AddressNormalizer.normalized_signature("123 Main St", None, "city-1", None)
        sig2 = AddressNormalizer.normalized_signature("123 Main St", None, "city-2", None)
        assert sig1 != sig2


class TestDuplicateAddressDetector:
    def test_detects_duplicate(self):
        assert DuplicateAddressDetector.is_duplicate("sig-1", frozenset({"sig-1", "sig-2"})) is True

    def test_no_duplicate(self):
        assert DuplicateAddressDetector.is_duplicate("sig-3", frozenset({"sig-1", "sig-2"})) is False


class TestHierarchyValidator:
    def test_district_belongs_to_region_passes(self):
        region_id = "region-1"
        HierarchyValidator.assert_district_belongs_to_region(region_id, region_id)

    def test_district_belongs_to_region_fails(self):
        with pytest.raises(InvalidHierarchy):
            HierarchyValidator.assert_district_belongs_to_region("region-1", "region-2")

    def test_city_belongs_to_region_fails(self):
        with pytest.raises(InvalidHierarchy):
            HierarchyValidator.assert_city_belongs_to_region("region-1", "region-2")
