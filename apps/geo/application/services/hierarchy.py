"""
Administrative-hierarchy Application Services: Create/Update/Delete for
Country, Region, District, City, Neighborhood (15 services).

Each Create service validates its parent reference exists (a
repository lookup, hence an Application Service concern per
domain/aggregates.py's module docstring) before constructing the
aggregate.
"""
from __future__ import annotations

import uuid

from django.db import transaction

from apps.geo.application.ports import (
    CityRepository, CountryRepository, DistrictRepository, NeighborhoodRepository, RegionRepository,
)
from apps.geo.application.services._shared import GeoServiceContext
from apps.geo.domain.aggregates import City, Country, District, Neighborhood, Region
from apps.geo.domain.enums import CityStatus, CountryStatus, DistrictStatus, NeighborhoodStatus, RegionStatus
from apps.geo.domain.exceptions import (
    DuplicateCityCode, DuplicateCountryCode, DuplicateDistrictCode, DuplicateNeighborhoodCode, DuplicateRegionCode,
    DuplicateSlug, GeoEntityNotFound,
)
from apps.geo.domain.services import HierarchyValidator
from apps.geo.domain.value_objects import CityCode, CountryCode, DistrictCode, LocationSlug, NeighborhoodCode, RegionCode
from common.exceptions import ResourceNotFound


# --- Country ---------------------------------------------------------

class CreateCountry:
    def __init__(self, repo: CountryRepository, ctx: GeoServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, code: str, name: str, slug_text: str | None = None) -> Country:
        if self._repo.code_exists(code):
            raise DuplicateCountryCode(f"Country code '{code}' already exists.")
        slug = LocationSlug.from_text(slug_text or name)
        if self._repo.slug_exists(slug.value):
            raise DuplicateSlug(f"Slug '{slug.value}' already exists.")

        country = Country(id=uuid.uuid4(), code=CountryCode(code), slug=slug, name=name)
        saved = self._repo.save(country)

        from apps.geo.domain.events import CountryCreated

        self._ctx.stage_events([("CountryCreated", CountryCreated(country_id=saved.id, code=code, name=name).to_payload())])
        self._ctx.audit().created(entity_type="Country", entity_id=str(saved.id), after={"code": code, "name": name})
        self._ctx.invalidate_geo_cache("country")
        self._ctx.metric("geo_countries_total")
        return saved


class UpdateCountry:
    def __init__(self, repo: CountryRepository, ctx: GeoServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, country_id: uuid.UUID, name: str | None = None) -> Country:
        country = self._repo.get_by_id(country_id)
        if country is None:
            raise ResourceNotFound("Country not found.")
        event = country.update(name=name)
        saved = self._repo.save(country)

        self._ctx.stage_events([("GeoEntityUpdated", event.to_payload())])
        self._ctx.audit().updated(entity_type="Country", entity_id=str(country_id), before=event.before, after=event.after)
        self._ctx.invalidate_geo_cache("country")
        return saved


class DeleteCountry:
    def __init__(self, repo: CountryRepository, ctx: GeoServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, country_id: uuid.UUID) -> None:
        country = self._repo.get_by_id(country_id)
        if country is None:
            raise ResourceNotFound("Country not found.")
        self._repo.delete(country_id)

        from apps.geo.domain.events import GeoEntityDeleted

        self._ctx.stage_events([("GeoEntityDeleted", GeoEntityDeleted(geo_level="country", entity_id=country_id).to_payload())])
        self._ctx.audit().deleted(entity_type="Country", entity_id=str(country_id), before={"code": country.code.value})
        self._ctx.invalidate_geo_cache("country")


# --- Region ------------------------------------------------------------

class CreateRegion:
    def __init__(self, region_repo: RegionRepository, country_repo: CountryRepository, ctx: GeoServiceContext) -> None:
        self._region_repo = region_repo
        self._country_repo = country_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, country_id: uuid.UUID, code: str, name: str, slug_text: str | None = None) -> Region:
        if self._country_repo.get_by_id(country_id) is None:
            raise GeoEntityNotFound(f"Country '{country_id}' does not exist.")
        if self._region_repo.code_exists(code):
            raise DuplicateRegionCode(f"Region code '{code}' already exists.")

        region = Region(id=uuid.uuid4(), country_id=country_id, code=RegionCode(code), slug=LocationSlug.from_text(slug_text or name), name=name)
        saved = self._region_repo.save(region)

        from apps.geo.domain.events import RegionCreated

        self._ctx.stage_events([("RegionCreated", RegionCreated(region_id=saved.id, country_id=country_id, code=code, name=name).to_payload())])
        self._ctx.audit().created(entity_type="Region", entity_id=str(saved.id), after={"code": code, "name": name})
        self._ctx.invalidate_geo_cache("region")
        self._ctx.metric("geo_regions_total")
        return saved


class UpdateRegion:
    def __init__(self, repo: RegionRepository, ctx: GeoServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, region_id: uuid.UUID, name: str | None = None) -> Region:
        region = self._repo.get_by_id(region_id)
        if region is None:
            raise ResourceNotFound("Region not found.")
        event = region.update(name=name)
        saved = self._repo.save(region)

        self._ctx.stage_events([("GeoEntityUpdated", event.to_payload())])
        self._ctx.audit().updated(entity_type="Region", entity_id=str(region_id), before=event.before, after=event.after)
        self._ctx.invalidate_geo_cache("region")
        return saved


class DeleteRegion:
    def __init__(self, repo: RegionRepository, ctx: GeoServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, region_id: uuid.UUID) -> None:
        region = self._repo.get_by_id(region_id)
        if region is None:
            raise ResourceNotFound("Region not found.")
        self._repo.delete(region_id)

        from apps.geo.domain.events import GeoEntityDeleted

        self._ctx.stage_events([("GeoEntityDeleted", GeoEntityDeleted(geo_level="region", entity_id=region_id).to_payload())])
        self._ctx.audit().deleted(entity_type="Region", entity_id=str(region_id), before={"code": region.code.value})
        self._ctx.invalidate_geo_cache("region")


# --- District ---------------------------------------------------------

class CreateDistrict:
    def __init__(self, district_repo: DistrictRepository, region_repo: RegionRepository, ctx: GeoServiceContext) -> None:
        self._district_repo = district_repo
        self._region_repo = region_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, region_id: uuid.UUID, code: str, name: str, slug_text: str | None = None) -> District:
        if self._region_repo.get_by_id(region_id) is None:
            raise GeoEntityNotFound(f"Region '{region_id}' does not exist.")
        if self._district_repo.code_exists(code):
            raise DuplicateDistrictCode(f"District code '{code}' already exists.")

        district = District(id=uuid.uuid4(), region_id=region_id, code=DistrictCode(code), slug=LocationSlug.from_text(slug_text or name), name=name)
        saved = self._district_repo.save(district)

        from apps.geo.domain.events import DistrictCreated

        self._ctx.stage_events([("DistrictCreated", DistrictCreated(district_id=saved.id, region_id=region_id, code=code, name=name).to_payload())])
        self._ctx.audit().created(entity_type="District", entity_id=str(saved.id), after={"code": code, "name": name})
        self._ctx.invalidate_geo_cache("district")
        return saved


class UpdateDistrict:
    def __init__(self, repo: DistrictRepository, ctx: GeoServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, district_id: uuid.UUID, name: str | None = None) -> District:
        district = self._repo.get_by_id(district_id)
        if district is None:
            raise ResourceNotFound("District not found.")
        event = district.update(name=name)
        saved = self._repo.save(district)

        self._ctx.stage_events([("GeoEntityUpdated", event.to_payload())])
        self._ctx.audit().updated(entity_type="District", entity_id=str(district_id), before=event.before, after=event.after)
        self._ctx.invalidate_geo_cache("district")
        return saved


class DeleteDistrict:
    def __init__(self, repo: DistrictRepository, ctx: GeoServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, district_id: uuid.UUID) -> None:
        district = self._repo.get_by_id(district_id)
        if district is None:
            raise ResourceNotFound("District not found.")
        self._repo.delete(district_id)

        from apps.geo.domain.events import GeoEntityDeleted

        self._ctx.stage_events([("GeoEntityDeleted", GeoEntityDeleted(geo_level="district", entity_id=district_id).to_payload())])
        self._ctx.audit().deleted(entity_type="District", entity_id=str(district_id), before={"code": district.code.value})
        self._ctx.invalidate_geo_cache("district")


# --- City --------------------------------------------------------------

class CreateCity:
    def __init__(self, city_repo: CityRepository, region_repo: RegionRepository, district_repo: DistrictRepository, ctx: GeoServiceContext) -> None:
        self._city_repo = city_repo
        self._region_repo = region_repo
        self._district_repo = district_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, region_id: uuid.UUID, code: str, name: str, district_id: uuid.UUID | None = None, slug_text: str | None = None) -> City:
        region = self._region_repo.get_by_id(region_id)
        if region is None:
            raise GeoEntityNotFound(f"Region '{region_id}' does not exist.")

        if district_id is not None:
            district = self._district_repo.get_by_id(district_id)
            if district is None:
                raise GeoEntityNotFound(f"District '{district_id}' does not exist.")
            HierarchyValidator.assert_district_belongs_to_region(district.region_id, region_id)

        if self._city_repo.code_exists(code):
            raise DuplicateCityCode(f"City code '{code}' already exists.")

        city = City(id=uuid.uuid4(), region_id=region_id, district_id=district_id, code=CityCode(code), slug=LocationSlug.from_text(slug_text or name), name=name)
        saved = self._city_repo.save(city)

        from apps.geo.domain.events import CityCreated

        self._ctx.stage_events([("CityCreated", CityCreated(city_id=saved.id, district_id=district_id, region_id=region_id, code=code, name=name).to_payload())])
        self._ctx.audit().created(entity_type="City", entity_id=str(saved.id), after={"code": code, "name": name})
        self._ctx.invalidate_geo_cache("city")
        self._ctx.metric("geo_cities_total")
        return saved


class UpdateCity:
    def __init__(self, repo: CityRepository, ctx: GeoServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, city_id: uuid.UUID, name: str | None = None) -> City:
        city = self._repo.get_by_id(city_id)
        if city is None:
            raise ResourceNotFound("City not found.")
        event = city.update(name=name)
        saved = self._repo.save(city)

        self._ctx.stage_events([("GeoEntityUpdated", event.to_payload())])
        self._ctx.audit().updated(entity_type="City", entity_id=str(city_id), before=event.before, after=event.after)
        self._ctx.invalidate_geo_cache("city")
        return saved


class DeleteCity:
    def __init__(self, repo: CityRepository, ctx: GeoServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, city_id: uuid.UUID) -> None:
        city = self._repo.get_by_id(city_id)
        if city is None:
            raise ResourceNotFound("City not found.")
        self._repo.delete(city_id)

        from apps.geo.domain.events import GeoEntityDeleted

        self._ctx.stage_events([("GeoEntityDeleted", GeoEntityDeleted(geo_level="city", entity_id=city_id).to_payload())])
        self._ctx.audit().deleted(entity_type="City", entity_id=str(city_id), before={"code": city.code.value})
        self._ctx.invalidate_geo_cache("city")


# --- Neighborhood -----------------------------------------------------

class CreateNeighborhood:
    def __init__(self, neighborhood_repo: NeighborhoodRepository, city_repo: CityRepository, ctx: GeoServiceContext) -> None:
        self._neighborhood_repo = neighborhood_repo
        self._city_repo = city_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, city_id: uuid.UUID, code: str, name: str, slug_text: str | None = None) -> Neighborhood:
        if self._city_repo.get_by_id(city_id) is None:
            raise GeoEntityNotFound(f"City '{city_id}' does not exist.")
        if self._neighborhood_repo.code_exists(code):
            raise DuplicateNeighborhoodCode(f"Neighborhood code '{code}' already exists.")

        neighborhood = Neighborhood(id=uuid.uuid4(), city_id=city_id, code=NeighborhoodCode(code), slug=LocationSlug.from_text(slug_text or name), name=name)
        saved = self._neighborhood_repo.save(neighborhood)

        from apps.geo.domain.events import NeighborhoodCreated

        self._ctx.stage_events([("NeighborhoodCreated", NeighborhoodCreated(neighborhood_id=saved.id, city_id=city_id, code=code, name=name).to_payload())])
        self._ctx.audit().created(entity_type="Neighborhood", entity_id=str(saved.id), after={"code": code, "name": name})
        self._ctx.invalidate_geo_cache("neighborhood")
        return saved


class UpdateNeighborhood:
    def __init__(self, repo: NeighborhoodRepository, ctx: GeoServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, neighborhood_id: uuid.UUID, name: str | None = None) -> Neighborhood:
        neighborhood = self._repo.get_by_id(neighborhood_id)
        if neighborhood is None:
            raise ResourceNotFound("Neighborhood not found.")
        event = neighborhood.update(name=name)
        saved = self._repo.save(neighborhood)

        self._ctx.stage_events([("GeoEntityUpdated", event.to_payload())])
        self._ctx.audit().updated(entity_type="Neighborhood", entity_id=str(neighborhood_id), before=event.before, after=event.after)
        self._ctx.invalidate_geo_cache("neighborhood")
        return saved


class DeleteNeighborhood:
    def __init__(self, repo: NeighborhoodRepository, ctx: GeoServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, neighborhood_id: uuid.UUID) -> None:
        neighborhood = self._repo.get_by_id(neighborhood_id)
        if neighborhood is None:
            raise ResourceNotFound("Neighborhood not found.")
        self._repo.delete(neighborhood_id)

        from apps.geo.domain.events import GeoEntityDeleted

        self._ctx.stage_events([("GeoEntityDeleted", GeoEntityDeleted(geo_level="neighborhood", entity_id=neighborhood_id).to_payload())])
        self._ctx.audit().deleted(entity_type="Neighborhood", entity_id=str(neighborhood_id), before={"code": neighborhood.code.value})
        self._ctx.invalidate_geo_cache("neighborhood")
