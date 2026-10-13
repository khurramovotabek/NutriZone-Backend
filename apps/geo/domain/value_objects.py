"""
Geo & Location domain value objects.

Immutable, self-validating -- structural rules live here (domain), not
duplicated in the serializer layer, matching the pattern established
by `apps/products/domain/value_objects.py`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from common.exceptions import ValidationFailed

_COUNTRY_CODE_RE = re.compile(r"^[A-Z]{2}$")  # ISO 3166-1 alpha-2
# 2–10 upper-case letters / digits, inner hyphens allowed: the reference data uses ISO-style codes such as "UZ-SA"
# (Samarqand viloyati), "SA-SAMAR" (Samarqand) and "TSH-CHI" (Chilonzor tumani). Without the hyphen every such
# region / city / district failed to load, so addresses could only be saved in Tashkent ("TGCITY1").
_HIERARCHY_CODE = r"^(?=.{2,10}$)[A-Z0-9]+(?:-[A-Z0-9]+)*$"
_REGION_CODE_RE = re.compile(_HIERARCHY_CODE)
_DISTRICT_CODE_RE = re.compile(_HIERARCHY_CODE)
_CITY_CODE_RE = re.compile(_HIERARCHY_CODE)
_NEIGHBORHOOD_CODE_RE = re.compile(r"^[A-Z0-9]{2,10}$")
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_POSTAL_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9\s-]{2,9}$", re.IGNORECASE)
_IANA_TZ_RE = re.compile(r"^[A-Za-z_]+/[A-Za-z_]+(?:/[A-Za-z_]+)?$")


@dataclass(frozen=True, slots=True)
class Latitude:
    value: float

    def __post_init__(self) -> None:
        if not (-90.0 <= self.value <= 90.0):
            raise ValidationFailed("Latitude must be between -90 and 90.", details={"fields": [{"field": "latitude", "code": "OUT_OF_RANGE"}]})


@dataclass(frozen=True, slots=True)
class Longitude:
    value: float

    def __post_init__(self) -> None:
        if not (-180.0 <= self.value <= 180.0):
            raise ValidationFailed("Longitude must be between -180 and 180.", details={"fields": [{"field": "longitude", "code": "OUT_OF_RANGE"}]})


@dataclass(frozen=True, slots=True)
class Coordinate:
    """A single lat/lng pair -- the atomic building block for GeoPoint, GeoBounds, and BoundaryPolygon."""

    latitude: Latitude
    longitude: Longitude

    @staticmethod
    def of(lat: float, lng: float) -> "Coordinate":
        return Coordinate(Latitude(lat), Longitude(lng))


@dataclass(frozen=True, slots=True)
class GeoPoint:
    """A Coordinate plus provenance metadata -- what an Address/City/Neighborhood actually stores, distinct from the bare Coordinate used inside a BoundaryPolygon's point list."""

    coordinate: Coordinate
    accuracy_meters: float | None = None

    def __post_init__(self) -> None:
        if self.accuracy_meters is not None and self.accuracy_meters < 0:
            raise ValidationFailed("accuracy_meters must not be negative.", details={"fields": [{"field": "accuracy_meters", "code": "NEGATIVE"}]})


@dataclass(frozen=True, slots=True)
class GeoBounds:
    """An axis-aligned bounding box (north-east / south-west corners) -- used for map-viewport queries and coarse containment checks before a full polygon test."""

    north_east: Coordinate
    south_west: Coordinate

    def __post_init__(self) -> None:
        if self.north_east.latitude.value < self.south_west.latitude.value:
            raise ValidationFailed("GeoBounds north_east latitude must be >= south_west latitude.")
        if self.north_east.longitude.value < self.south_west.longitude.value:
            raise ValidationFailed("GeoBounds north_east longitude must be >= south_west longitude.")

    def contains(self, point: Coordinate) -> bool:
        return (
            self.south_west.latitude.value <= point.latitude.value <= self.north_east.latitude.value
            and self.south_west.longitude.value <= point.longitude.value <= self.north_east.longitude.value
        )


@dataclass(frozen=True, slots=True)
class AddressLine:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValidationFailed("Address line must not be empty.", details={"fields": [{"field": "address_line", "code": "REQUIRED"}]})
        if len(self.value) > 255:
            raise ValidationFailed("Address line must not exceed 255 characters.", details={"fields": [{"field": "address_line", "code": "TOO_LONG"}]})


@dataclass(frozen=True, slots=True)
class PostalCode:
    value: str

    def __post_init__(self) -> None:
        if not _POSTAL_CODE_RE.match(self.value):
            raise ValidationFailed("Invalid postal code format.", details={"fields": [{"field": "postal_code", "code": "INVALID_FORMAT"}]})

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Timezone:
    """IANA timezone identifier (e.g. 'Asia/Tashkent') -- validated for shape here; existence against the real tz database is a domain-service concern (see services.py::TimezoneValidator), since the domain layer avoids depending on the interpreter's bundled tz data as a structural rule."""

    value: str

    def __post_init__(self) -> None:
        if not _IANA_TZ_RE.match(self.value):
            raise ValidationFailed(
                "Timezone must be a valid IANA identifier, e.g. 'Asia/Tashkent'.",
                details={"fields": [{"field": "timezone", "code": "INVALID_FORMAT"}]},
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class CountryCode:
    value: str

    def __post_init__(self) -> None:
        if not _COUNTRY_CODE_RE.match(self.value):
            raise ValidationFailed("Country code must be a 2-letter ISO 3166-1 alpha-2 code.", details={"fields": [{"field": "country_code", "code": "INVALID_FORMAT"}]})

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class RegionCode:
    value: str

    def __post_init__(self) -> None:
        if not _REGION_CODE_RE.match(self.value):
            raise ValidationFailed("Invalid region code format.", details={"fields": [{"field": "region_code", "code": "INVALID_FORMAT"}]})

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class DistrictCode:
    value: str

    def __post_init__(self) -> None:
        if not _DISTRICT_CODE_RE.match(self.value):
            raise ValidationFailed("Invalid district code format.", details={"fields": [{"field": "district_code", "code": "INVALID_FORMAT"}]})

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class CityCode:
    value: str

    def __post_init__(self) -> None:
        if not _CITY_CODE_RE.match(self.value):
            raise ValidationFailed("Invalid city code format.", details={"fields": [{"field": "city_code", "code": "INVALID_FORMAT"}]})

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class NeighborhoodCode:
    value: str

    def __post_init__(self) -> None:
        if not _NEIGHBORHOOD_CODE_RE.match(self.value):
            raise ValidationFailed("Invalid neighborhood code format.", details={"fields": [{"field": "neighborhood_code", "code": "INVALID_FORMAT"}]})

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class LocationSlug:
    value: str

    def __post_init__(self) -> None:
        if not _SLUG_RE.match(self.value):
            raise ValidationFailed("Slug must be lowercase, alphanumeric, hyphen-separated.", details={"fields": [{"field": "slug", "code": "INVALID_FORMAT"}]})

    @staticmethod
    def from_text(text: str) -> "LocationSlug":
        normalized = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
        if not normalized:
            raise ValidationFailed("Cannot derive a slug from empty or non-alphanumeric text.")
        return LocationSlug(normalized[:220].rstrip("-"))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class FormattedAddress:
    """The assembled, human-readable multi-line address string -- computed by domain/services.py::AddressNormalizer, stored alongside the structured address fields so a client never has to reassemble it."""

    single_line: str
    lines: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.single_line:
            raise ValidationFailed("FormattedAddress.single_line must not be empty.")
