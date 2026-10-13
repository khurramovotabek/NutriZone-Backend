"""
Geo & Location domain entities (non-root members of an aggregate).
"""
from __future__ import annotations

from dataclasses import dataclass

from apps.geo.domain.value_objects import GeoPoint


@dataclass(slots=True)
class AddressCoordinate:
    """Non-root entity, owned by Address -- the geocoded point plus how it was obtained."""

    point: GeoPoint
    source: str = "manual"  # gps | map_pin | search | link | telegram_native_share | manual | geocoded
    geocoded_at: object = None  # datetime | None, kept loosely typed to avoid a domain->datetime-tz dependency beyond stdlib


@dataclass(slots=True)
class AddressMetadata:
    """Non-root entity, owned by Address -- building/unit/delivery-instruction detail beyond the structured address lines."""

    building_name: str | None = None
    entrance: str | None = None  # podyezd
    floor: str | None = None
    unit: str | None = None
    delivery_instructions: str | None = None
    entrance_code: str | None = None


@dataclass(slots=True)
class LocationTranslation:
    """Non-root entity -- per-locale name, matching the translation-table pattern already established platform-wide (Database Blueprint §4.2's Category/Brand/Product translations)."""

    locale_code: str
    name: str
