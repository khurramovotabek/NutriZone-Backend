from __future__ import annotations

import pytest

from apps.geo.domain.value_objects import (
    AddressLine,
    CityCode,
    Coordinate,
    CountryCode,
    DistrictCode,
    FormattedAddress,
    GeoBounds,
    GeoPoint,
    Latitude,
    LocationSlug,
    Longitude,
    NeighborhoodCode,
    PostalCode,
    RegionCode,
    Timezone,
)
from common.exceptions import ValidationFailed

pytestmark = pytest.mark.unit


class TestLatitudeLongitude:
    @pytest.mark.parametrize("value", [-90, 0, 90, 45.5])
    def test_latitude_accepts_valid_range(self, value):
        Latitude(value)

    @pytest.mark.parametrize("value", [-90.1, 90.1, 180])
    def test_latitude_rejects_out_of_range(self, value):
        with pytest.raises(ValidationFailed):
            Latitude(value)

    @pytest.mark.parametrize("value", [-180, 0, 180])
    def test_longitude_accepts_valid_range(self, value):
        Longitude(value)

    def test_longitude_rejects_out_of_range(self):
        with pytest.raises(ValidationFailed):
            Longitude(180.1)


class TestCoordinate:
    def test_of_constructs_from_floats(self):
        coord = Coordinate.of(41.3, 69.2)
        assert coord.latitude.value == 41.3
        assert coord.longitude.value == 69.2


class TestGeoBounds:
    def test_valid_bounds(self):
        GeoBounds(north_east=Coordinate.of(42, 70), south_west=Coordinate.of(41, 69))

    def test_rejects_inverted_latitude(self):
        with pytest.raises(ValidationFailed):
            GeoBounds(north_east=Coordinate.of(41, 70), south_west=Coordinate.of(42, 69))

    def test_contains_point_inside(self):
        bounds = GeoBounds(north_east=Coordinate.of(42, 70), south_west=Coordinate.of(41, 69))
        assert bounds.contains(Coordinate.of(41.5, 69.5)) is True

    def test_contains_point_outside(self):
        bounds = GeoBounds(north_east=Coordinate.of(42, 70), south_west=Coordinate.of(41, 69))
        assert bounds.contains(Coordinate.of(50, 50)) is False


class TestGeoPoint:
    def test_valid_point(self):
        GeoPoint(coordinate=Coordinate.of(41, 69), accuracy_meters=5.0)

    def test_rejects_negative_accuracy(self):
        with pytest.raises(ValidationFailed):
            GeoPoint(coordinate=Coordinate.of(41, 69), accuracy_meters=-1)


class TestAddressLine:
    def test_valid_line(self):
        AddressLine("123 Main St")

    def test_rejects_empty(self):
        with pytest.raises(ValidationFailed):
            AddressLine("")

    def test_rejects_too_long(self):
        with pytest.raises(ValidationFailed):
            AddressLine("x" * 256)


class TestPostalCode:
    def test_valid_postal_code(self):
        assert PostalCode("100000").value == "100000"

    def test_rejects_too_short(self):
        with pytest.raises(ValidationFailed):
            PostalCode("1")


class TestTimezone:
    def test_valid_shape(self):
        assert Timezone("Asia/Tashkent").value == "Asia/Tashkent"

    def test_rejects_invalid_shape(self):
        with pytest.raises(ValidationFailed):
            Timezone("not-a-timezone")


class TestGeoCodes:
    def test_country_code_valid(self):
        assert CountryCode("UZ").value == "UZ"

    def test_country_code_rejects_lowercase(self):
        with pytest.raises(ValidationFailed):
            CountryCode("uz")

    def test_region_code_valid(self):
        RegionCode("TASH")

    def test_district_code_valid(self):
        DistrictCode("D1")

    def test_city_code_valid(self):
        CityCode("TAS")

    def test_neighborhood_code_valid(self):
        NeighborhoodCode("N1")


class TestLocationSlug:
    def test_from_text_normalizes(self):
        assert LocationSlug.from_text("Tashkent City!!").value == "tashkent-city"

    def test_rejects_invalid_format(self):
        with pytest.raises(ValidationFailed):
            LocationSlug("Not A Slug")


class TestFormattedAddress:
    def test_valid(self):
        FormattedAddress(single_line="123 Main St, Tashkent", lines=("123 Main St", "Tashkent"))

    def test_rejects_empty_single_line(self):
        with pytest.raises(ValidationFailed):
            FormattedAddress(single_line="", lines=())
