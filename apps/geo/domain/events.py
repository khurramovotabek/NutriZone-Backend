"""
Geo & Location domain events.

Registered against `core.events.registry` via
`shared/event_contracts/geo.py`, matching the pattern established by
every prior module.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class CountryCreated:
    country_id: uuid.UUID
    code: str
    name: str

    def to_payload(self) -> dict:
        return {**asdict(self), "country_id": str(self.country_id)}


@dataclass(frozen=True, slots=True)
class RegionCreated:
    region_id: uuid.UUID
    country_id: uuid.UUID
    code: str
    name: str

    def to_payload(self) -> dict:
        return {**asdict(self), "region_id": str(self.region_id), "country_id": str(self.country_id)}


@dataclass(frozen=True, slots=True)
class DistrictCreated:
    district_id: uuid.UUID
    region_id: uuid.UUID
    code: str
    name: str

    def to_payload(self) -> dict:
        return {**asdict(self), "district_id": str(self.district_id), "region_id": str(self.region_id)}


@dataclass(frozen=True, slots=True)
class CityCreated:
    city_id: uuid.UUID
    district_id: uuid.UUID | None
    region_id: uuid.UUID
    code: str
    name: str

    def to_payload(self) -> dict:
        return {
            **asdict(self), "city_id": str(self.city_id),
            "district_id": str(self.district_id) if self.district_id else None,
            "region_id": str(self.region_id),
        }


@dataclass(frozen=True, slots=True)
class NeighborhoodCreated:
    neighborhood_id: uuid.UUID
    city_id: uuid.UUID
    code: str
    name: str

    def to_payload(self) -> dict:
        return {**asdict(self), "neighborhood_id": str(self.neighborhood_id), "city_id": str(self.city_id)}


@dataclass(frozen=True, slots=True)
class AddressCreated:
    address_id: uuid.UUID
    owner_type: str
    owner_id: uuid.UUID

    def to_payload(self) -> dict:
        return {**asdict(self), "address_id": str(self.address_id), "owner_id": str(self.owner_id)}


@dataclass(frozen=True, slots=True)
class AddressUpdated:
    address_id: uuid.UUID
    before: dict
    after: dict

    def to_payload(self) -> dict:
        return {**asdict(self), "address_id": str(self.address_id)}


@dataclass(frozen=True, slots=True)
class AddressDeleted:
    address_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"address_id": str(self.address_id)}


@dataclass(frozen=True, slots=True)
class GeoEntityUpdated:
    """Generic update event for Country/Region/District/City/Neighborhood -- one shape, `geo_level` discriminates, per MIC §7's preference for a closed, registered event set over an ever-growing per-entity list of near-identical events."""

    geo_level: str
    entity_id: uuid.UUID
    before: dict
    after: dict

    def to_payload(self) -> dict:
        return {**asdict(self), "entity_id": str(self.entity_id)}


@dataclass(frozen=True, slots=True)
class GeoEntityDeleted:
    geo_level: str
    entity_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"geo_level": self.geo_level, "entity_id": str(self.entity_id)}
