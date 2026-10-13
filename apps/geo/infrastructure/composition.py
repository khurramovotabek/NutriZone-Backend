"""
Composition root for the `geo` module's interfaces layer.

Wires concrete `infrastructure/` implementations into `application/
services/` constructors -- matching
`apps.identity.infrastructure.composition`/
`apps.products.infrastructure.composition`'s exact pattern. No service
locator: every `build_*()` factory explicitly constructs and returns
one fully-wired object. Views must never instantiate a repository
directly (this phase's explicit rule) -- every read and write path
below is the only sanctioned way the (not-yet-built) Interfaces layer
reaches persistence.
"""
from __future__ import annotations

import uuid

from apps.geo.application.selectors import GeoSelector
from apps.geo.application.services._shared import GeoServiceContext
from apps.geo.application.services.address import (
    AssignCoordinates, CreateAddress, DeleteAddress, NormalizeAddress, UpdateAddress, ValidateAddress,
)
from apps.geo.application.services.geocoding import ReverseGeocode, SearchLocations
from apps.geo.application.services.hierarchy import (
    CreateCity, CreateCountry, CreateDistrict, CreateNeighborhood, CreateRegion,
    DeleteCity, DeleteCountry, DeleteDistrict, DeleteNeighborhood, DeleteRegion,
    UpdateCity, UpdateCountry, UpdateDistrict, UpdateNeighborhood, UpdateRegion,
)
from apps.geo.application.services.queries import ListCities, ListCountries, ListDistricts, ListNeighborhoods, ListRegions
from apps.geo.infrastructure import models as orm
from apps.geo.infrastructure.repositories import (
    DjangoAddressRepository, DjangoCityRepository, DjangoCountryRepository,
    DjangoDistrictRepository, DjangoNeighborhoodRepository, DjangoRegionRepository,
)
from apps.geo.infrastructure.selectors import DjangoGeoSearchBackend
from core.outbox import stage_event


def stage_geo_events(events: list[tuple[str, dict]]) -> None:
    """The `stage_events` callable every Geo Application Service is constructed with -- the concrete Outbox-aware implementation, kept out of `application/` per Clean Architecture."""
    for event_type, payload in events:
        stage_event(orm.GeoOutboxEvent, event_type, payload)


def build_context(actor_id: uuid.UUID | None = None) -> GeoServiceContext:
    return GeoServiceContext(stage_events=stage_geo_events, actor_id=actor_id)


# --- Hierarchy: Country -----------------------------------------------

def build_create_country(actor_id=None) -> CreateCountry:
    return CreateCountry(DjangoCountryRepository(), build_context(actor_id))


def build_update_country(actor_id=None) -> UpdateCountry:
    return UpdateCountry(DjangoCountryRepository(), build_context(actor_id))


def build_delete_country(actor_id=None) -> DeleteCountry:
    return DeleteCountry(DjangoCountryRepository(), build_context(actor_id))


# --- Hierarchy: Region --------------------------------------------------

def build_create_region(actor_id=None) -> CreateRegion:
    return CreateRegion(DjangoRegionRepository(), DjangoCountryRepository(), build_context(actor_id))


def build_update_region(actor_id=None) -> UpdateRegion:
    return UpdateRegion(DjangoRegionRepository(), build_context(actor_id))


def build_delete_region(actor_id=None) -> DeleteRegion:
    return DeleteRegion(DjangoRegionRepository(), build_context(actor_id))


# --- Hierarchy: District -------------------------------------------------

def build_create_district(actor_id=None) -> CreateDistrict:
    return CreateDistrict(DjangoDistrictRepository(), DjangoRegionRepository(), build_context(actor_id))


def build_update_district(actor_id=None) -> UpdateDistrict:
    return UpdateDistrict(DjangoDistrictRepository(), build_context(actor_id))


def build_delete_district(actor_id=None) -> DeleteDistrict:
    return DeleteDistrict(DjangoDistrictRepository(), build_context(actor_id))


# --- Hierarchy: City -----------------------------------------------------

def build_create_city(actor_id=None) -> CreateCity:
    return CreateCity(DjangoCityRepository(), DjangoRegionRepository(), DjangoDistrictRepository(), build_context(actor_id))


def build_update_city(actor_id=None) -> UpdateCity:
    return UpdateCity(DjangoCityRepository(), build_context(actor_id))


def build_delete_city(actor_id=None) -> DeleteCity:
    return DeleteCity(DjangoCityRepository(), build_context(actor_id))


# --- Hierarchy: Neighborhood ----------------------------------------------

def build_create_neighborhood(actor_id=None) -> CreateNeighborhood:
    return CreateNeighborhood(DjangoNeighborhoodRepository(), DjangoCityRepository(), build_context(actor_id))


def build_update_neighborhood(actor_id=None) -> UpdateNeighborhood:
    return UpdateNeighborhood(DjangoNeighborhoodRepository(), build_context(actor_id))


def build_delete_neighborhood(actor_id=None) -> DeleteNeighborhood:
    return DeleteNeighborhood(DjangoNeighborhoodRepository(), build_context(actor_id))


# --- Address --------------------------------------------------------------

def build_create_address(actor_id=None) -> CreateAddress:
    return CreateAddress(DjangoAddressRepository(), DjangoCityRepository(), DjangoCountryRepository(), build_context(actor_id), DjangoDistrictRepository())


def build_update_address(actor_id=None) -> UpdateAddress:
    return UpdateAddress(DjangoAddressRepository(), DjangoCityRepository(), build_context(actor_id), DjangoDistrictRepository())


def build_delete_address(actor_id=None) -> DeleteAddress:
    return DeleteAddress(DjangoAddressRepository(), build_context(actor_id))


def build_normalize_address() -> NormalizeAddress:
    return NormalizeAddress(DjangoCityRepository())


def build_validate_address() -> ValidateAddress:
    return ValidateAddress(DjangoCityRepository(), DjangoCountryRepository())


def build_assign_coordinates(actor_id=None) -> AssignCoordinates:
    return AssignCoordinates(DjangoAddressRepository(), build_context(actor_id))


# --- Geocoding / Search -----------------------------------------------------

def build_reverse_geocode(actor_id=None) -> ReverseGeocode:
    return ReverseGeocode(DjangoCityRepository(), build_context(actor_id))


def build_search_locations(actor_id=None) -> SearchLocations:
    return SearchLocations(DjangoGeoSearchBackend(), build_context(actor_id))


def build_geo_selector() -> GeoSelector:
    return GeoSelector(DjangoGeoSearchBackend())


# --- Queries --------------------------------------------------------------

def build_list_countries() -> ListCountries:
    return ListCountries(DjangoCountryRepository())


def build_list_regions() -> ListRegions:
    return ListRegions(DjangoRegionRepository())


def build_list_districts() -> ListDistricts:
    return ListDistricts(DjangoDistrictRepository())


def build_list_cities() -> ListCities:
    return ListCities(DjangoCityRepository())


def build_list_neighborhoods() -> ListNeighborhoods:
    return ListNeighborhoods(DjangoNeighborhoodRepository())


# --- Reference-data repositories (read-only lookups the future
# interfaces layer needs directly) -- wired here so views never
# instantiate a repository implementing a swappable Port directly,
# matching the fix already applied to apps.products.interfaces.api.v1.views.

def build_address_repository() -> DjangoAddressRepository:
    return DjangoAddressRepository()
