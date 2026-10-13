"""
Geo & Location domain (business) validators -- thin, intention-revealing
wrappers over the value objects' own constructor validation, matching
the pattern established by `apps/products/domain/validators.py`.
"""
from __future__ import annotations

from apps.geo.domain.value_objects import (
    Coordinate,
    CountryCode,
    Latitude,
    Longitude,
    PostalCode,
    RegionCode,
    Timezone,
)


def LatitudeValidator(value: float) -> Latitude:  # noqa: N802 - matches this module's brief's naming
    return Latitude(value)


def LongitudeValidator(value: float) -> Longitude:  # noqa: N802
    return Longitude(value)


def CoordinateValidator(lat: float, lng: float) -> Coordinate:  # noqa: N802
    return Coordinate.of(lat, lng)


def PostalCodeValidator(value: str) -> PostalCode:  # noqa: N802
    return PostalCode(value)


def CountryCodeValidator(value: str) -> CountryCode:  # noqa: N802
    return CountryCode(value)


def RegionCodeValidator(value: str) -> RegionCode:  # noqa: N802
    return RegionCode(value)


def TimezoneFormatValidator(value: str) -> Timezone:  # noqa: N802
    """Shape-only validation (see domain/services.py::TimezoneValidator for the full tz-database check)."""
    return Timezone(value)


def validate_hierarchy_not_self_referential(entity_id, parent_id) -> None:
    from apps.geo.domain.exceptions import InvalidHierarchy

    if entity_id is not None and entity_id == parent_id:
        raise InvalidHierarchy("A geo entity cannot be its own parent.")
