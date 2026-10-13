"""
Geo & Location aggregate roots: Country, Region, District, City,
Neighborhood, Address.

Each administrative-hierarchy aggregate (Country/Region/District/City/
Neighborhood) enforces its own structural invariants (non-empty name,
not-self-parent) directly; cross-aggregate existence checks (e.g. "does
this Region's country_id actually reference a real Country") require a
repository lookup and are therefore an Application Service concern
(MIC §6's four-tier validation split: "Cross-Module Validation... via
a synchronous call to the owning module's Application Service", here
applied intra-module between sibling aggregates for the identical
reason -- a domain object cannot query a repository).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from apps.geo.domain.entities import AddressCoordinate, AddressMetadata
from apps.geo.domain.enums import (
    AddressType,
    CityStatus,
    CountryStatus,
    DistrictStatus,
    NeighborhoodStatus,
    RegionStatus,
)
from apps.geo.domain.events import (
    AddressCreated,
    AddressDeleted,
    AddressUpdated,
    CityCreated,
    CountryCreated,
    DistrictCreated,
    GeoEntityDeleted,
    GeoEntityUpdated,
    NeighborhoodCreated,
    RegionCreated,
)
from apps.geo.domain.exceptions import InvalidHierarchy
from apps.geo.domain.value_objects import (
    CityCode,
    CountryCode,
    DistrictCode,
    FormattedAddress,
    GeoPoint,
    LocationSlug,
    NeighborhoodCode,
    PostalCode,
    RegionCode,
    Timezone,
)


@dataclass(slots=True)
class Country:
    id: uuid.UUID
    code: CountryCode
    slug: LocationSlug
    name: str
    status: CountryStatus = CountryStatus.ACTIVE
    timezone: Timezone | None = None

    def __post_init__(self) -> None:
        from common.exceptions import ValidationFailed

        if not self.name or not self.name.strip():
            raise ValidationFailed("Country name must not be empty.")

    def deactivate(self) -> None:
        self.status = CountryStatus.INACTIVE

    def activate(self) -> None:
        self.status = CountryStatus.ACTIVE

    def update(self, name: str | None = None, timezone: Timezone | None = None) -> GeoEntityUpdated:
        before = {"name": self.name, "timezone": str(self.timezone) if self.timezone else None}
        if name is not None:
            self.name = name
        if timezone is not None:
            self.timezone = timezone
        after = {"name": self.name, "timezone": str(self.timezone) if self.timezone else None}
        return GeoEntityUpdated(geo_level="country", entity_id=self.id, before=before, after=after)


@dataclass(slots=True)
class Region:
    id: uuid.UUID
    country_id: uuid.UUID
    code: RegionCode
    slug: LocationSlug
    name: str
    status: RegionStatus = RegionStatus.ACTIVE

    def __post_init__(self) -> None:
        from common.exceptions import ValidationFailed

        if not self.name or not self.name.strip():
            raise ValidationFailed("Region name must not be empty.")

    def update(self, name: str | None = None) -> GeoEntityUpdated:
        before = {"name": self.name}
        if name is not None:
            self.name = name
        return GeoEntityUpdated(geo_level="region", entity_id=self.id, before=before, after={"name": self.name})

    def deactivate(self) -> None:
        self.status = RegionStatus.INACTIVE

    def activate(self) -> None:
        self.status = RegionStatus.ACTIVE


@dataclass(slots=True)
class District:
    id: uuid.UUID
    region_id: uuid.UUID
    code: DistrictCode
    slug: LocationSlug
    name: str
    status: DistrictStatus = DistrictStatus.ACTIVE

    def __post_init__(self) -> None:
        from common.exceptions import ValidationFailed

        if not self.name or not self.name.strip():
            raise ValidationFailed("District name must not be empty.")

    def update(self, name: str | None = None) -> GeoEntityUpdated:
        before = {"name": self.name}
        if name is not None:
            self.name = name
        return GeoEntityUpdated(geo_level="district", entity_id=self.id, before=before, after={"name": self.name})

    def deactivate(self) -> None:
        self.status = DistrictStatus.INACTIVE

    def activate(self) -> None:
        self.status = DistrictStatus.ACTIVE


@dataclass(slots=True)
class City:
    id: uuid.UUID
    region_id: uuid.UUID
    code: CityCode
    slug: LocationSlug
    name: str
    district_id: uuid.UUID | None = None
    status: CityStatus = CityStatus.ACTIVE
    center_point: GeoPoint | None = None
    timezone: Timezone | None = None

    def __post_init__(self) -> None:
        from common.exceptions import ValidationFailed

        if not self.name or not self.name.strip():
            raise ValidationFailed("City name must not be empty.")

    def update(self, name: str | None = None, center_point: GeoPoint | None = None) -> GeoEntityUpdated:
        before = {"name": self.name}
        if name is not None:
            self.name = name
        if center_point is not None:
            self.center_point = center_point
        return GeoEntityUpdated(geo_level="city", entity_id=self.id, before=before, after={"name": self.name})

    def assign_coordinates(self, point: GeoPoint) -> None:
        self.center_point = point

    def deactivate(self) -> None:
        self.status = CityStatus.INACTIVE

    def activate(self) -> None:
        self.status = CityStatus.ACTIVE


@dataclass(slots=True)
class Neighborhood:
    id: uuid.UUID
    city_id: uuid.UUID
    code: NeighborhoodCode
    slug: LocationSlug
    name: str
    status: NeighborhoodStatus = NeighborhoodStatus.ACTIVE
    center_point: GeoPoint | None = None

    def __post_init__(self) -> None:
        from common.exceptions import ValidationFailed

        if not self.name or not self.name.strip():
            raise ValidationFailed("Neighborhood name must not be empty.")

    def update(self, name: str | None = None) -> GeoEntityUpdated:
        before = {"name": self.name}
        if name is not None:
            self.name = name
        return GeoEntityUpdated(geo_level="neighborhood", entity_id=self.id, before=before, after={"name": self.name})

    def deactivate(self) -> None:
        self.status = NeighborhoodStatus.INACTIVE

    def activate(self) -> None:
        self.status = NeighborhoodStatus.ACTIVE


@dataclass(slots=True)
class Address:
    """
    Aggregate root -- owns AddressCoordinate and AddressMetadata.
    References the administrative hierarchy (country/region/city/
    neighborhood) by ID only, per the platform-wide "reference by ID,
    never own another aggregate's data" rule already applied
    everywhere else (Domain Architecture Specification §2.2's Product
    referencing Category/Brand by ID is the direct precedent).
    """

    id: uuid.UUID
    owner_type: str
    owner_id: uuid.UUID
    address_type: AddressType
    country_id: uuid.UUID
    city_id: uuid.UUID
    line1: str
    region_id: uuid.UUID | None = None
    district_id: uuid.UUID | None = None
    neighborhood_id: uuid.UUID | None = None
    line2: str | None = None
    postal_code: PostalCode | None = None
    recipient_name: str | None = None
    recipient_phone: str | None = None
    recipient_telegram_username: str | None = None
    coordinate: AddressCoordinate | None = None
    metadata: AddressMetadata = field(default_factory=AddressMetadata)
    formatted: FormattedAddress | None = None
    is_default: bool = False
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        from common.exceptions import ValidationFailed

        if not self.line1 or not self.line1.strip():
            raise ValidationFailed("Address line1 must not be empty.", details={"fields": [{"field": "line1", "code": "REQUIRED"}]})

    def update(
        self, line1: str | None = None, line2: str | None = None, postal_code: PostalCode | None = None, metadata: AddressMetadata | None = None,
        city_id: uuid.UUID | None = None, address_type: AddressType | None = None,
        recipient_name: str | None = None, recipient_phone: str | None = None, recipient_telegram_username: str | None = None,
    ) -> AddressUpdated:
        """
        Real, product-required capability: a customer editing a saved
        address previously had no way to change its city, type, or
        recipient info at all (only line1/line2/postal_code) -- the
        only way to correct any of those was deleting and re-creating
        the address. PATCH-like throughout: every parameter left
        `None` leaves that field untouched, matching this project's
        own established convention (see
        ProductVariantAdminForm._save_price's identical "blank =
        unchanged" contract). `city_id`/`address_type` are the two
        real fields with no natural "blank means unchanged" sentinel
        of their own (a UUID/enum can't be empty the way a string can)
        -- `None` is unambiguous here since neither field is ever
        legitimately nullable on an existing address.
        """
        before = {
            "line1": self.line1, "line2": self.line2, "city_id": str(self.city_id), "address_type": self.address_type.value,
            "recipient_name": self.recipient_name, "recipient_phone": self.recipient_phone, "recipient_telegram_username": self.recipient_telegram_username,
        }
        if line1 is not None:
            self.line1 = line1
        if line2 is not None:
            self.line2 = line2
        if postal_code is not None:
            self.postal_code = postal_code
        if metadata is not None:
            self.metadata = metadata
        if city_id is not None:
            self.city_id = city_id
        if address_type is not None:
            self.address_type = address_type
        if recipient_name is not None:
            self.recipient_name = recipient_name
        if recipient_phone is not None:
            self.recipient_phone = recipient_phone
        if recipient_telegram_username is not None:
            self.recipient_telegram_username = recipient_telegram_username
        after = {
            "line1": self.line1, "line2": self.line2, "city_id": str(self.city_id), "address_type": self.address_type.value,
            "recipient_name": self.recipient_name, "recipient_phone": self.recipient_phone, "recipient_telegram_username": self.recipient_telegram_username,
        }
        return AddressUpdated(address_id=self.id, before=before, after=after)

    def assign_coordinate(self, coordinate: AddressCoordinate) -> None:
        self.coordinate = coordinate

    def set_formatted(self, formatted: FormattedAddress) -> None:
        self.formatted = formatted

    def mark_default(self) -> None:
        self.is_default = True

    def unmark_default(self) -> None:
        self.is_default = False


