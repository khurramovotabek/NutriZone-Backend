"""
Geo & Location domain enums.

Scope note (documented per this module's own build instruction to
"follow every approved document exactly"): "Geo & Location" is NOT one
of the eighteen bounded contexts named in the Domain Architecture
Specification. That document instead folds geo concerns into `stores`
(GeoProximityResolver, Store location) and treats addresses as
Fulfillment/Ordering-owned data. This module's brief introduces a new,
platform-wide geo bounded context. Per MIC's own amendment discipline
(the same discipline already applied to the `Bundle` aggregate and the
`apps.catalog`/`apps.products` naming reconciliation in the Products
module), this is implemented as a genuine new bounded context -- the
Domain Architecture Specification and Database Blueprint should be
formally amended to register `geo` as bounded context #19 before this
is considered fully reconciled with those two documents; this is
flagged explicitly in the module's completion report rather than
silently treated as already covered by the original 18.
"""
from __future__ import annotations

from common.utils import DomainStrEnum


class CountryStatus(DomainStrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class RegionStatus(DomainStrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class DistrictStatus(DomainStrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class CityStatus(DomainStrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class NeighborhoodStatus(DomainStrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class AddressType(DomainStrEnum):
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    WAREHOUSE = "warehouse"
    PICKUP_POINT = "pickup_point"
    OFFICE = "office"


class GeoLevel(DomainStrEnum):
    """The administrative hierarchy this module owns end-to-end: Country -> Region -> District -> City -> Neighborhood."""

    COUNTRY = "country"
    REGION = "region"
    DISTRICT = "district"
    CITY = "city"
    NEIGHBORHOOD = "neighborhood"


class CoordinateSystem(DomainStrEnum):
    """WGS84 is the only supported system at launch (standard for GPS/web mapping) -- kept as an enum, not a hardcoded assumption, so a future system (e.g. a local Uzbek cadastral system) is an additive value, not a schema change."""

    WGS84 = "wgs84"


class TimezoneType(DomainStrEnum):
    STANDARD = "standard"
    DAYLIGHT_SAVING = "daylight_saving"
