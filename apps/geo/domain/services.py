"""
Geo & Location domain services.

Pure business rules with no I/O, per MIC §4 -- handed data by the
calling Application Service, never fetching it themselves. Matches the
pattern established by every prior module's domain/services.py.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from apps.geo.domain.value_objects import Coordinate, FormattedAddress, Timezone
from common.exceptions import ValidationFailed

_EARTH_RADIUS_METERS = 6_371_000


class TimezoneValidator:
    """
    Validates an IANA timezone identifier against the interpreter's
    bundled tz database (Python 3.9+ stdlib `zoneinfo`) -- kept
    separate from the `Timezone` value object's own constructor
    (which only validates the *shape* 'Continent/City') since a full
    tz-database lookup is a heavier check some callers may not always
    want paid on every VO construction (e.g. deserializing many
    addresses from a trusted source).
    """

    @staticmethod
    def validate(timezone: Timezone) -> None:
        import zoneinfo

        try:
            zoneinfo.ZoneInfo(timezone.value)
        except (zoneinfo.ZoneInfoNotFoundError, ValueError) as exc:
            from apps.geo.domain.exceptions import InvalidTimezone

            raise InvalidTimezone(f"'{timezone.value}' is not a recognized IANA timezone.") from exc


class GeoDistanceCalculator:
    """Great-circle (haversine) distance between two coordinates -- used by ReverseGeocode/SearchLocations for nearest-match ranking."""

    @staticmethod
    def distance_meters(a: Coordinate, b: Coordinate) -> float:
        lat1, lat2 = math.radians(a.latitude.value), math.radians(b.latitude.value)
        dlat = math.radians(b.latitude.value - a.latitude.value)
        dlng = math.radians(b.longitude.value - a.longitude.value)
        h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
        return 2 * _EARTH_RADIUS_METERS * math.asin(math.sqrt(h))


class AddressNormalizer:
    """
    Domain Architecture Specification-style pure service: assembles a
    `FormattedAddress` from structured fields, and computes a
    normalized signature (a stable hash) used by
    `DuplicateAddressDetector` below -- normalization means
    lowercasing, whitespace-collapsing, and joining in a fixed field
    order, so two addresses that differ only in casing/spacing/field
    ordering are recognized as the same address.
    """

    @staticmethod
    def format(line1: str, line2: str | None, city_name: str, region_name: str | None, country_name: str, postal_code: str | None) -> FormattedAddress:
        lines = [line1]
        if line2:
            lines.append(line2)
        locality = ", ".join(p for p in (city_name, region_name) if p)
        if locality:
            lines.append(locality)
        if postal_code:
            lines.append(postal_code)
        lines.append(country_name)
        return FormattedAddress(single_line=", ".join(lines), lines=tuple(lines))

    @staticmethod
    def normalized_signature(line1: str, line2: str | None, city_id: str, postal_code: str | None) -> str:
        parts = [
            re_collapse(line1), re_collapse(line2 or ""), city_id, re_collapse(postal_code or ""),
        ]
        raw = "|".join(parts).lower()
        return hashlib.sha256(raw.encode()).hexdigest()


def re_collapse(text: str) -> str:
    import re

    return re.sub(r"\s+", " ", text.strip())


class DuplicateAddressDetector:
    """Compares a candidate address's normalized signature against a caller-supplied set of existing signatures (repository-sourced) -- pure comparison, no I/O itself."""

    @staticmethod
    def is_duplicate(candidate_signature: str, existing_signatures: frozenset[str]) -> bool:
        return candidate_signature in existing_signatures


class HierarchyValidator:
    """
    Structural (not existence) checks for the administrative hierarchy
    -- existence of a referenced parent id is a repository concern
    (Application Service), but "is this assignment even structurally
    sane" (e.g. a City cannot list a District that belongs to a
    different Region) can be checked once both records are loaded,
    without needing a *third* repository call.
    """

    @staticmethod
    def assert_district_belongs_to_region(district_region_id, expected_region_id) -> None:
        from apps.geo.domain.exceptions import InvalidHierarchy

        if district_region_id != expected_region_id:
            raise InvalidHierarchy("This district does not belong to the specified region.")

    @staticmethod
    def assert_city_belongs_to_region(city_region_id, expected_region_id) -> None:
        from apps.geo.domain.exceptions import InvalidHierarchy

        if city_region_id != expected_region_id:
            raise InvalidHierarchy("This city does not belong to the specified region.")
