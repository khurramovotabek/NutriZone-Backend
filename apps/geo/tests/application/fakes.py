"""
In-memory fakes implementing application/ports.py's Protocols, matching
`apps.products.tests.application.fakes`'s exact pattern.
"""
from __future__ import annotations


class FakeCountryRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, country_id):
        return self.by_id.get(country_id)

    def get_by_code(self, code):
        return next((c for c in self.by_id.values() if c.code.value == code), None)

    def save(self, country):
        self.by_id[country.id] = country
        return country

    def code_exists(self, code, exclude_id=None) -> bool:
        return any(c.code.value == code and c.id != exclude_id for c in self.by_id.values())

    def slug_exists(self, slug, exclude_id=None) -> bool:
        return any(c.slug.value == slug and c.id != exclude_id for c in self.by_id.values())

    def delete(self, country_id):
        self.by_id.pop(country_id, None)

    def list_active(self, page, page_size):
        results = list(self.by_id.values())
        return results[(page - 1) * page_size : page * page_size], len(results)


class FakeRegionRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, region_id):
        return self.by_id.get(region_id)

    def save(self, region):
        self.by_id[region.id] = region
        return region

    def code_exists(self, code, exclude_id=None) -> bool:
        return any(r.code.value == code and r.id != exclude_id for r in self.by_id.values())

    def delete(self, region_id):
        self.by_id.pop(region_id, None)

    def list_by_country(self, country_id, page, page_size):
        results = [r for r in self.by_id.values() if r.country_id == country_id]
        return results[(page - 1) * page_size : page * page_size], len(results)


class FakeDistrictRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, district_id):
        return self.by_id.get(district_id)

    def save(self, district):
        self.by_id[district.id] = district
        return district

    def code_exists(self, code, exclude_id=None) -> bool:
        return any(d.code.value == code and d.id != exclude_id for d in self.by_id.values())

    def delete(self, district_id):
        self.by_id.pop(district_id, None)

    def list_by_region(self, region_id, page, page_size):
        results = [d for d in self.by_id.values() if d.region_id == region_id]
        return results[(page - 1) * page_size : page * page_size], len(results)


class FakeCityRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, city_id):
        return self.by_id.get(city_id)

    def save(self, city):
        self.by_id[city.id] = city
        return city

    def code_exists(self, code, exclude_id=None) -> bool:
        return any(c.code.value == code and c.id != exclude_id for c in self.by_id.values())

    def delete(self, city_id):
        self.by_id.pop(city_id, None)

    def list_by_region(self, region_id, page, page_size):
        results = list(self.by_id.values())
        if region_id:
            results = [c for c in results if c.region_id == region_id]
        return results[(page - 1) * page_size : page * page_size], len(results)

    def find_nearest(self, latitude, longitude, limit):
        from apps.geo.domain.services import GeoDistanceCalculator
        from apps.geo.domain.value_objects import Coordinate

        target = Coordinate.of(latitude, longitude)
        candidates = [(c, GeoDistanceCalculator.distance_meters(target, c.center_point.coordinate)) for c in self.by_id.values() if c.center_point]
        candidates.sort(key=lambda pair: pair[1])
        return [c for c, _ in candidates[:limit]]


class FakeNeighborhoodRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, neighborhood_id):
        return self.by_id.get(neighborhood_id)

    def save(self, neighborhood):
        self.by_id[neighborhood.id] = neighborhood
        return neighborhood

    def code_exists(self, code, exclude_id=None) -> bool:
        return any(n.code.value == code and n.id != exclude_id for n in self.by_id.values())

    def delete(self, neighborhood_id):
        self.by_id.pop(neighborhood_id, None)

    def list_by_city(self, city_id, page, page_size):
        results = [n for n in self.by_id.values() if n.city_id == city_id]
        return results[(page - 1) * page_size : page * page_size], len(results)


class FakeAddressRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, address_id):
        return self.by_id.get(address_id)

    def save(self, address):
        self.by_id[address.id] = address
        return address

    def delete(self, address_id):
        self.by_id.pop(address_id, None)

    def list_signatures_for_owner(self, owner_type, owner_id):
        from apps.geo.domain.services import AddressNormalizer

        return frozenset(
            AddressNormalizer.normalized_signature(a.line1, a.line2, str(a.city_id), str(a.postal_code) if a.postal_code else None)
            for a in self.by_id.values()
            if a.owner_type == owner_type and a.owner_id == owner_id
        )

    def list_for_owner(self, owner_type, owner_id):
        return [a for a in self.by_id.values() if a.owner_type == owner_type and a.owner_id == owner_id]


def collect_events(sink: list):
    def _stage(events: list[tuple[str, dict]]) -> None:
        sink.extend(events)

    return _stage
