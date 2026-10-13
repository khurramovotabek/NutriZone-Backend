"""
Geocoding & Search Application Services: ReverseGeocode, SearchLocations.
"""
from __future__ import annotations

from apps.geo.application.ports import CityRepository, GeoSearchGateway
from apps.geo.application.services._shared import GeoServiceContext
from apps.geo.domain.services import GeoDistanceCalculator
from apps.geo.domain.value_objects import Coordinate


class ReverseGeocode:
    """
    Given a coordinate, resolves the nearest City -- backs the "find my
    location" checkout-flow use case other bounded contexts
    (Fulfillment, once built) will call by ID reference, per the
    platform-wide reference-by-ID rule.
    """

    def __init__(self, city_repo: CityRepository, ctx: GeoServiceContext) -> None:
        self._city_repo = city_repo
        self._ctx = ctx

    def execute(self, latitude: float, longitude: float) -> dict:
        with self._ctx.timer("geo_reverse_geocode_duration"):
            nearest_cities = self._city_repo.find_nearest(latitude, longitude, limit=1)

        self._ctx.metric("geo_reverse_geocode_total")

        return {
            "nearest_city": nearest_cities[0] if nearest_cities else None,
        }


class SearchLocations:
    def __init__(self, search_gateway: GeoSearchGateway, ctx: GeoServiceContext) -> None:
        self._search_gateway = search_gateway
        self._ctx = ctx

    def execute(self, query: str, geo_level: str | None = None, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
        with self._ctx.timer("geo_search_duration"):
            results, total = self._search_gateway.search(query=query, geo_level=geo_level, page=page, page_size=page_size)
        self._ctx.metric("geo_searches_total")
        return results, total
