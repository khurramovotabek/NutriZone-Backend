"""
Repository integration tests -- require a real PostgreSQL database.
Matches `apps.products.tests.infrastructure.test_repositories`'s
pattern.
"""
from __future__ import annotations

import uuid

import pytest

from apps.geo.domain.aggregates import Address, City, Country, Region
from apps.geo.domain.enums import AddressType
from apps.geo.domain.value_objects import CityCode, Coordinate, CountryCode, LocationSlug, RegionCode
from apps.geo.infrastructure.repositories import (
    DjangoAddressRepository, DjangoCityRepository, DjangoCountryRepository, DjangoRegionRepository,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestDjangoCountryRepository:
    def test_save_then_get_by_id_round_trips(self):
        repo = DjangoCountryRepository()
        country = Country(id=uuid.uuid4(), code=CountryCode("UZ"), slug=LocationSlug("uzbekistan"), name="Uzbekistan")
        repo.save(country)

        fetched = repo.get_by_id(country.id)
        assert fetched is not None
        assert fetched.code.value == "UZ"
        assert fetched.name == "Uzbekistan"

    def test_get_by_code(self):
        repo = DjangoCountryRepository()
        country = Country(id=uuid.uuid4(), code=CountryCode("KZ"), slug=LocationSlug("kazakhstan"), name="Kazakhstan")
        repo.save(country)
        assert repo.get_by_code("KZ").id == country.id

    def test_code_exists_respects_exclusion(self):
        repo = DjangoCountryRepository()
        country = Country(id=uuid.uuid4(), code=CountryCode("TJ"), slug=LocationSlug("tajikistan"), name="Tajikistan")
        repo.save(country)
        assert repo.code_exists("TJ") is True
        assert repo.code_exists("TJ", exclude_id=country.id) is False

    def test_delete_soft_deletes(self):
        from apps.geo.infrastructure import models as orm

        repo = DjangoCountryRepository()
        country = Country(id=uuid.uuid4(), code=CountryCode("KG"), slug=LocationSlug("kyrgyzstan"), name="Kyrgyzstan")
        repo.save(country)
        repo.delete(country.id)
        assert orm.Country.objects.filter(id=country.id).first() is None
        assert orm.Country.all_objects.filter(id=country.id).first() is not None


class TestDjangoRegionRepository:
    def test_save_and_get(self):
        country_repo = DjangoCountryRepository()
        country = Country(id=uuid.uuid4(), code=CountryCode("UZ"), slug=LocationSlug("uz2"), name="Uzbekistan")
        country_repo.save(country)

        region_repo = DjangoRegionRepository()
        region = Region(id=uuid.uuid4(), country_id=country.id, code=RegionCode("TASH2"), slug=LocationSlug("tashkent2"), name="Tashkent")
        region_repo.save(region)

        fetched = region_repo.get_by_id(region.id)
        assert fetched.country_id == country.id


class TestDjangoCityRepository:
    def test_find_nearest_returns_closest_city(self):
        region_repo = DjangoRegionRepository()
        country_repo = DjangoCountryRepository()
        country = Country(id=uuid.uuid4(), code=CountryCode("UZ"), slug=LocationSlug("uz3"), name="Uzbekistan")
        country_repo.save(country)
        region = Region(id=uuid.uuid4(), country_id=country.id, code=RegionCode("TASH3"), slug=LocationSlug("tashkent3"), name="Tashkent")
        region_repo.save(region)

        city_repo = DjangoCityRepository()
        from apps.geo.domain.value_objects import GeoPoint

        near = City(id=uuid.uuid4(), region_id=region.id, code=CityCode("NEAR"), slug=LocationSlug("near-city"), name="Near City", center_point=GeoPoint(coordinate=Coordinate.of(41.30, 69.20)))
        far = City(id=uuid.uuid4(), region_id=region.id, code=CityCode("FAR"), slug=LocationSlug("far-city"), name="Far City", center_point=GeoPoint(coordinate=Coordinate.of(43.0, 71.0)))
        city_repo.save(near)
        city_repo.save(far)

        results = city_repo.find_nearest(41.31, 69.21, limit=1)
        assert results[0].id == near.id


class TestDjangoAddressRepository:
    def test_save_and_get_with_metadata(self):
        country_repo = DjangoCountryRepository()
        country = Country(id=uuid.uuid4(), code=CountryCode("UZ"), slug=LocationSlug("uz4"), name="Uzbekistan")
        country_repo.save(country)
        region_repo = DjangoRegionRepository()
        region = Region(id=uuid.uuid4(), country_id=country.id, code=RegionCode("TASH4"), slug=LocationSlug("tashkent4"), name="Tashkent")
        region_repo.save(region)
        city_repo = DjangoCityRepository()
        city = City(id=uuid.uuid4(), region_id=region.id, code=CityCode("TAS4"), slug=LocationSlug("tashkent-city4"), name="Tashkent City")
        city_repo.save(city)

        address_repo = DjangoAddressRepository()
        from apps.geo.domain.entities import AddressMetadata

        address = Address(
            id=uuid.uuid4(), owner_type="user", owner_id=uuid.uuid4(), address_type=AddressType.RESIDENTIAL,
            country_id=country.id, city_id=city.id, line1="123 Main St", metadata=AddressMetadata(building_name="Tower A"),
        )
        address_repo.save(address)

        fetched = address_repo.get_by_id(address.id)
        assert fetched.line1 == "123 Main St"
        assert fetched.metadata.building_name == "Tower A"

    def test_save_and_get_recipient_details(self):
        """Real, product-required capability: who the delivery is for -- saved and reloaded correctly through the real ORM."""
        country_repo = DjangoCountryRepository()
        country = Country(id=uuid.uuid4(), code=CountryCode("UZ"), slug=LocationSlug("uz-recip"), name="Uzbekistan")
        country_repo.save(country)
        region_repo = DjangoRegionRepository()
        region = Region(id=uuid.uuid4(), country_id=country.id, code=RegionCode("TASHR"), slug=LocationSlug("tashkent-recip"), name="Tashkent")
        region_repo.save(region)
        city_repo = DjangoCityRepository()
        city = City(id=uuid.uuid4(), region_id=region.id, code=CityCode("TASR"), slug=LocationSlug("tashkent-city-recip"), name="Tashkent City")
        city_repo.save(city)

        address_repo = DjangoAddressRepository()
        address = Address(
            id=uuid.uuid4(), owner_type="user", owner_id=uuid.uuid4(), address_type=AddressType.RESIDENTIAL,
            country_id=country.id, city_id=city.id, line1="123 Main St",
            recipient_name="Aziz Karimov", recipient_phone="+998901234567", recipient_telegram_username="azizkarimov",
        )
        address_repo.save(address)

        fetched = address_repo.get_by_id(address.id)
        assert fetched.recipient_name == "Aziz Karimov"
        assert fetched.recipient_phone == "+998901234567"
        assert fetched.recipient_telegram_username == "azizkarimov"

    def test_list_signatures_for_owner(self):
        country_repo = DjangoCountryRepository()
        country = Country(id=uuid.uuid4(), code=CountryCode("UZ"), slug=LocationSlug("uz5"), name="Uzbekistan")
        country_repo.save(country)
        city_repo = DjangoCityRepository()
        region_repo = DjangoRegionRepository()
        region = Region(id=uuid.uuid4(), country_id=country.id, code=RegionCode("TASH5"), slug=LocationSlug("tashkent5"), name="Tashkent")
        region_repo.save(region)
        city = City(id=uuid.uuid4(), region_id=region.id, code=CityCode("TAS5"), slug=LocationSlug("tashkent-city5"), name="Tashkent City")
        city_repo.save(city)

        address_repo = DjangoAddressRepository()
        owner_id = uuid.uuid4()
        address = Address(id=uuid.uuid4(), owner_type="user", owner_id=owner_id, address_type=AddressType.RESIDENTIAL, country_id=country.id, city_id=city.id, line1="123 Main St")
        address_repo.save(address)

        signatures = address_repo.list_signatures_for_owner("user", owner_id)
        assert len(signatures) == 1
