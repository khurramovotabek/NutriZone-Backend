from __future__ import annotations

import uuid

import pytest

from apps.geo.application.services._shared import GeoServiceContext
from apps.geo.application.services.hierarchy import (
    CreateCity, CreateCountry, CreateDistrict, CreateNeighborhood, CreateRegion,
    DeleteCountry, UpdateCountry,
)
from apps.geo.domain.aggregates import City, Country, District, Region
from apps.geo.domain.exceptions import DuplicateCountryCode, DuplicateRegionCode, GeoEntityNotFound, InvalidHierarchy
from apps.geo.domain.value_objects import CityCode, CountryCode, DistrictCode, LocationSlug, RegionCode
from apps.geo.tests.application.fakes import (
    FakeCityRepository, FakeCountryRepository, FakeDistrictRepository, FakeNeighborhoodRepository, FakeRegionRepository,
    collect_events,
)
from common.exceptions import ResourceNotFound


def _ctx():
    events: list = []
    return GeoServiceContext(stage_events=collect_events(events), actor_id=uuid.uuid4()), events


@pytest.mark.django_db
class TestCreateCountry:
    """Marked django_db: uses @transaction.atomic -- same documented rationale as every prior module's write-path tests."""

    def test_creates_country(self):
        repo = FakeCountryRepository()
        ctx, events = _ctx()
        country = CreateCountry(repo, ctx).execute(code="UZ", name="Uzbekistan")
        assert country.code.value == "UZ"
        assert any(e[0] == "CountryCreated" for e in events)

    def test_duplicate_code_raises(self):
        repo = FakeCountryRepository()
        ctx, _ = _ctx()
        CreateCountry(repo, ctx).execute(code="UZ", name="Uzbekistan")
        with pytest.raises(DuplicateCountryCode):
            CreateCountry(repo, ctx).execute(code="UZ", name="Uzbekistan Again")


@pytest.mark.django_db
class TestUpdateDeleteCountry:
    def test_update_country(self):
        repo = FakeCountryRepository()
        country = Country(id=uuid.uuid4(), code=CountryCode("UZ"), slug=LocationSlug("uz"), name="Old Name")
        repo.save(country)
        ctx, events = _ctx()

        updated = UpdateCountry(repo, ctx).execute(country_id=country.id, name="New Name")

        assert updated.name == "New Name"
        assert any(e[0] == "GeoEntityUpdated" for e in events)

    def test_update_missing_country_raises(self):
        repo = FakeCountryRepository()
        ctx, _ = _ctx()
        with pytest.raises(ResourceNotFound):
            UpdateCountry(repo, ctx).execute(country_id=uuid.uuid4(), name="X")

    def test_delete_country(self):
        repo = FakeCountryRepository()
        country = Country(id=uuid.uuid4(), code=CountryCode("UZ"), slug=LocationSlug("uz"), name="Uzbekistan")
        repo.save(country)
        ctx, events = _ctx()

        DeleteCountry(repo, ctx).execute(country.id)

        assert country.id not in repo.by_id
        assert any(e[0] == "GeoEntityDeleted" for e in events)


@pytest.mark.django_db
class TestCreateRegion:
    def test_creates_region(self):
        country_repo = FakeCountryRepository()
        country = Country(id=uuid.uuid4(), code=CountryCode("UZ"), slug=LocationSlug("uz"), name="Uzbekistan")
        country_repo.save(country)
        region_repo = FakeRegionRepository()
        ctx, events = _ctx()

        region = CreateRegion(region_repo, country_repo, ctx).execute(country_id=country.id, code="TASH", name="Tashkent")

        assert region.country_id == country.id
        assert any(e[0] == "RegionCreated" for e in events)

    def test_unknown_country_raises(self):
        ctx, _ = _ctx()
        with pytest.raises(GeoEntityNotFound):
            CreateRegion(FakeRegionRepository(), FakeCountryRepository(), ctx).execute(country_id=uuid.uuid4(), code="TASH", name="Tashkent")

    def test_duplicate_region_code_raises(self):
        country_repo = FakeCountryRepository()
        country = Country(id=uuid.uuid4(), code=CountryCode("UZ"), slug=LocationSlug("uz"), name="Uzbekistan")
        country_repo.save(country)
        region_repo = FakeRegionRepository()
        ctx, _ = _ctx()
        CreateRegion(region_repo, country_repo, ctx).execute(country_id=country.id, code="TASH", name="Tashkent")
        with pytest.raises(DuplicateRegionCode):
            CreateRegion(region_repo, country_repo, ctx).execute(country_id=country.id, code="TASH", name="Tashkent Again")


@pytest.mark.django_db
class TestCreateCityHierarchyValidation:
    def test_district_from_wrong_region_raises(self):
        region_repo = FakeRegionRepository()
        region_a = Region(id=uuid.uuid4(), country_id=uuid.uuid4(), code=RegionCode("REGA"), slug=LocationSlug("region-a"), name="Region A")
        region_b = Region(id=uuid.uuid4(), country_id=uuid.uuid4(), code=RegionCode("REGB"), slug=LocationSlug("region-b"), name="Region B")
        region_repo.save(region_a)
        region_repo.save(region_b)

        district_repo = FakeDistrictRepository()
        district_in_b = District(id=uuid.uuid4(), region_id=region_b.id, code=DistrictCode("D1"), slug=LocationSlug("d1"), name="District 1")
        district_repo.save(district_in_b)

        city_repo = FakeCityRepository()
        ctx, _ = _ctx()

        with pytest.raises(InvalidHierarchy):
            CreateCity(city_repo, region_repo, district_repo, ctx).execute(region_id=region_a.id, code="CITY1", name="City 1", district_id=district_in_b.id)

    def test_creates_city_without_district(self):
        region_repo = FakeRegionRepository()
        region = Region(id=uuid.uuid4(), country_id=uuid.uuid4(), code=RegionCode("TASH"), slug=LocationSlug("tashkent"), name="Tashkent")
        region_repo.save(region)
        city_repo = FakeCityRepository()
        ctx, events = _ctx()

        city = CreateCity(city_repo, region_repo, FakeDistrictRepository(), ctx).execute(region_id=region.id, code="TAS", name="Tashkent City")

        assert city.region_id == region.id
        assert any(e[0] == "CityCreated" for e in events)


@pytest.mark.django_db
class TestCreateNeighborhood:
    def test_unknown_city_raises(self):
        ctx, _ = _ctx()
        with pytest.raises(GeoEntityNotFound):
            CreateNeighborhood(FakeNeighborhoodRepository(), FakeCityRepository(), ctx).execute(city_id=uuid.uuid4(), code="N1", name="Neighborhood 1")
