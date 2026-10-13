from __future__ import annotations

import uuid

import pytest

from apps.geo.domain.aggregates import Address, City, Country, District, Neighborhood, Region
from apps.geo.domain.enums import AddressType
from apps.geo.domain.value_objects import CityCode, Coordinate, CountryCode, DistrictCode, LocationSlug, NeighborhoodCode, RegionCode
from common.exceptions import ValidationFailed

pytestmark = pytest.mark.unit


class TestCountry:
    def test_valid_country(self):
        Country(id=uuid.uuid4(), code=CountryCode("UZ"), slug=LocationSlug("uzbekistan"), name="Uzbekistan")

    def test_empty_name_raises(self):
        with pytest.raises(ValidationFailed):
            Country(id=uuid.uuid4(), code=CountryCode("UZ"), slug=LocationSlug("uzbekistan"), name="")

    def test_activate_deactivate(self):
        country = Country(id=uuid.uuid4(), code=CountryCode("UZ"), slug=LocationSlug("uz"), name="Uzbekistan")
        country.deactivate()
        assert country.status.value == "inactive"
        country.activate()
        assert country.status.value == "active"

    def test_update_returns_event_with_before_after(self):
        country = Country(id=uuid.uuid4(), code=CountryCode("UZ"), slug=LocationSlug("uz"), name="Old Name")
        event = country.update(name="New Name")
        assert country.name == "New Name"
        assert event.before["name"] == "Old Name"
        assert event.after["name"] == "New Name"
        assert event.geo_level == "country"


class TestRegion:
    def test_valid_region(self):
        Region(id=uuid.uuid4(), country_id=uuid.uuid4(), code=RegionCode("TASH"), slug=LocationSlug("tashkent"), name="Tashkent")

    def test_empty_name_raises(self):
        with pytest.raises(ValidationFailed):
            Region(id=uuid.uuid4(), country_id=uuid.uuid4(), code=RegionCode("TASH"), slug=LocationSlug("tashkent"), name="")


class TestDistrict:
    def test_valid_district(self):
        District(id=uuid.uuid4(), region_id=uuid.uuid4(), code=DistrictCode("D1"), slug=LocationSlug("d1"), name="District 1")


class TestCity:
    def test_valid_city(self):
        City(id=uuid.uuid4(), region_id=uuid.uuid4(), code=CityCode("TAS"), slug=LocationSlug("tashkent"), name="Tashkent")

    def test_assign_coordinates(self):
        from apps.geo.domain.value_objects import GeoPoint

        city = City(id=uuid.uuid4(), region_id=uuid.uuid4(), code=CityCode("TAS"), slug=LocationSlug("tashkent"), name="Tashkent")
        point = GeoPoint(coordinate=Coordinate.of(41.3, 69.2))
        city.assign_coordinates(point)
        assert city.center_point == point


class TestNeighborhood:
    def test_valid_neighborhood(self):
        Neighborhood(id=uuid.uuid4(), city_id=uuid.uuid4(), code=NeighborhoodCode("N1"), slug=LocationSlug("n1"), name="Neighborhood 1")


class TestAddress:
    def test_valid_address(self):
        Address(id=uuid.uuid4(), owner_type="user", owner_id=uuid.uuid4(), address_type=AddressType.RESIDENTIAL, country_id=uuid.uuid4(), city_id=uuid.uuid4(), line1="123 Main St")

    def test_empty_line1_raises(self):
        with pytest.raises(ValidationFailed):
            Address(id=uuid.uuid4(), owner_type="user", owner_id=uuid.uuid4(), address_type=AddressType.RESIDENTIAL, country_id=uuid.uuid4(), city_id=uuid.uuid4(), line1="")

    def test_mark_unmark_default(self):
        address = Address(id=uuid.uuid4(), owner_type="user", owner_id=uuid.uuid4(), address_type=AddressType.RESIDENTIAL, country_id=uuid.uuid4(), city_id=uuid.uuid4(), line1="123 Main St")
        address.mark_default()
        assert address.is_default is True
        address.unmark_default()
        assert address.is_default is False

    def test_update_returns_event(self):
        address = Address(id=uuid.uuid4(), owner_type="user", owner_id=uuid.uuid4(), address_type=AddressType.RESIDENTIAL, country_id=uuid.uuid4(), city_id=uuid.uuid4(), line1="Old Line")
        event = address.update(line1="New Line")
        assert address.line1 == "New Line"
        assert event.before["line1"] == "Old Line"
