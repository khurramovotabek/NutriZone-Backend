"""
Query Application Services: ListCountries, ListRegions, ListDistricts,
ListCities, ListNeighborhoods.
"""
from __future__ import annotations

import uuid

from apps.geo.application.ports import (
    CityRepository, CountryRepository, DistrictRepository, NeighborhoodRepository, RegionRepository,
)


class ListCountries:
    def __init__(self, repo: CountryRepository) -> None:
        self._repo = repo

    def execute(self, page: int = 1, page_size: int = 50):
        return self._repo.list_active(page=page, page_size=page_size)


class ListRegions:
    def __init__(self, repo: RegionRepository) -> None:
        self._repo = repo

    def execute(self, country_id: uuid.UUID, page: int = 1, page_size: int = 50):
        return self._repo.list_by_country(country_id=country_id, page=page, page_size=page_size)


class ListDistricts:
    def __init__(self, repo: DistrictRepository) -> None:
        self._repo = repo

    def execute(self, region_id: uuid.UUID, page: int = 1, page_size: int = 50):
        return self._repo.list_by_region(region_id=region_id, page=page, page_size=page_size)


class ListCities:
    def __init__(self, repo: CityRepository) -> None:
        self._repo = repo

    def execute(self, region_id: uuid.UUID | None = None, page: int = 1, page_size: int = 50):
        return self._repo.list_by_region(region_id=region_id, page=page, page_size=page_size)


class ListNeighborhoods:
    def __init__(self, repo: NeighborhoodRepository) -> None:
        self._repo = repo

    def execute(self, city_id: uuid.UUID, page: int = 1, page_size: int = 50):
        return self._repo.list_by_city(city_id=city_id, page=page, page_size=page_size)
