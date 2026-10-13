"""
Address Application Services: CreateAddress, UpdateAddress,
DeleteAddress, NormalizeAddress, ValidateAddress, AssignCoordinates.
"""
from __future__ import annotations

import uuid

from django.db import transaction

from apps.geo.application.ports import AddressRepository, CityRepository, CountryRepository
from apps.geo.application.services._shared import GeoServiceContext
from apps.geo.domain.aggregates import Address
from apps.geo.domain.entities import AddressCoordinate, AddressMetadata
from apps.geo.domain.enums import AddressType
from apps.geo.domain.exceptions import DuplicateAddressDetected, GeoEntityNotFound
from apps.geo.domain.services import AddressNormalizer, DuplicateAddressDetector, GeoDistanceCalculator
from apps.geo.domain.value_objects import Coordinate, GeoPoint, PostalCode
from common.exceptions import ResourceNotFound


METADATA_FIELDS = ("building_name", "entrance", "floor", "unit", "entrance_code", "delivery_instructions")


def metadata_from(data: dict | None) -> AddressMetadata:
    """The delivery details (podyezd, floor, flat, door code, landmark) -- blank strings stored as None."""
    data = data or {}
    return AddressMetadata(**{f: ((data.get(f) or "").strip() or None) for f in METADATA_FIELDS})


def delivery_details_line(metadata: AddressMetadata | None, limit: int = 255) -> str:
    """One line a courier reads: "2-podyezd · 5-qavat · 34-xonadon · domofon 34K · Mo'ljal: ..." (Uzbek, the team's language)."""
    if metadata is None:
        return ""
    parts = []
    if metadata.building_name:
        parts.append(metadata.building_name)
    if metadata.entrance:
        parts.append(f"{metadata.entrance}-podyezd")
    if metadata.floor:
        parts.append(f"{metadata.floor}-qavat")
    if metadata.unit:
        parts.append(f"{metadata.unit}-xonadon")
    if metadata.entrance_code:
        parts.append(f"domofon {metadata.entrance_code}")
    if metadata.delivery_instructions:
        parts.append(f"Mo'ljal: {metadata.delivery_instructions}")
    line = " · ".join(parts)
    return line if len(line) <= limit else line[: limit - 1] + "…"


def _check_district(district_repo, district_id, region_id) -> None:
    """A district must exist and lie in the address's region (a Chilonzor tumani never under Samarqand)."""
    if district_id is None or district_repo is None:
        return
    district = district_repo.get_by_id(district_id)
    if district is None:
        raise GeoEntityNotFound(f"District '{district_id}' does not exist.")
    if region_id is not None and district.region_id != region_id:
        from common.exceptions import ValidationFailed

        raise ValidationFailed("The district is not in the address's region.", details={"fields": [{"field": "district_id", "code": "REGION_MISMATCH"}]})


class CreateAddress:
    def __init__(self, address_repo: AddressRepository, city_repo: CityRepository, country_repo: CountryRepository, ctx: GeoServiceContext, district_repo=None) -> None:
        self._district_repo = district_repo
        self._address_repo = address_repo
        self._city_repo = city_repo
        self._country_repo = country_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(
        self, owner_type: str, owner_id: uuid.UUID, address_type: str, country_id: uuid.UUID, city_id: uuid.UUID,
        line1: str, line2: str | None = None, postal_code: str | None = None, region_id=None, district_id=None, neighborhood_id=None,
        recipient_name: str | None = None, recipient_phone: str | None = None, recipient_telegram_username: str | None = None,
        metadata: dict | None = None,
    ) -> Address:
        if self._country_repo.get_by_id(country_id) is None:
            raise GeoEntityNotFound(f"Country '{country_id}' does not exist.")
        city = self._city_repo.get_by_id(city_id)
        if city is None:
            raise GeoEntityNotFound(f"City '{city_id}' does not exist.")

        _check_district(self._district_repo, district_id, region_id or city.region_id)
        signature = AddressNormalizer.normalized_signature(line1, line2, str(city_id), postal_code)
        existing_signatures = self._address_repo.list_signatures_for_owner(owner_type, owner_id)
        if DuplicateAddressDetector.is_duplicate(signature, existing_signatures):
            raise DuplicateAddressDetected("An identical address already exists for this owner.")

        address = Address(
            id=uuid.uuid4(), owner_type=owner_type, owner_id=owner_id, address_type=AddressType(address_type),
            country_id=country_id, city_id=city_id, region_id=region_id or city.region_id, district_id=district_id, neighborhood_id=neighborhood_id,
            line1=line1, line2=line2, postal_code=PostalCode(postal_code) if postal_code else None,
            recipient_name=recipient_name, recipient_phone=recipient_phone, recipient_telegram_username=recipient_telegram_username,
            metadata=metadata_from(metadata),
        )
        address.set_formatted(AddressNormalizer.format(line1, line2, city.name, None, "", postal_code))
        saved = self._address_repo.save(address)

        from apps.geo.domain.events import AddressCreated

        self._ctx.stage_events([("AddressCreated", AddressCreated(address_id=saved.id, owner_type=owner_type, owner_id=owner_id).to_payload())])
        self._ctx.audit().created(entity_type="Address", entity_id=str(saved.id), after={"line1": line1, "owner_id": str(owner_id)})
        self._ctx.invalidate_geo_cache("address")
        self._ctx.metric("geo_addresses_created_total")
        return saved


class UpdateAddress:
    def __init__(self, repo: AddressRepository, city_repo: CityRepository, ctx: GeoServiceContext, district_repo=None) -> None:
        self._district_repo = district_repo
        self._repo = repo
        self._city_repo = city_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(
        self, address_id: uuid.UUID, line1: str | None = None, line2: str | None = None, postal_code: str | None = None,
        city_id: uuid.UUID | None = None, address_type: str | None = None,
        recipient_name: str | None = None, recipient_phone: str | None = None, recipient_telegram_username: str | None = None,
        metadata: dict | None = None, district_id: uuid.UUID | None = None,
    ) -> Address:
        address = self._repo.get_by_id(address_id)
        if address is None:
            raise ResourceNotFound("Address not found.")

        if city_id is not None:
            new_city = self._city_repo.get_by_id(city_id)
            if new_city is None:
                raise GeoEntityNotFound(f"City '{city_id}' does not exist.")
            if city_id != address.city_id:
                address.region_id, address.district_id = new_city.region_id, None  # the old district belongs to the old city
        if district_id is not None:
            _check_district(self._district_repo, district_id, address.region_id)
            address.district_id = district_id

        event = address.update(
            line1=line1, line2=line2, postal_code=PostalCode(postal_code) if postal_code else None,
            city_id=city_id, address_type=AddressType(address_type) if address_type is not None else None,
            recipient_name=recipient_name, recipient_phone=recipient_phone, recipient_telegram_username=recipient_telegram_username,
            metadata=metadata_from(metadata) if metadata is not None else None,
        )
        if line1 is not None or line2 is not None or postal_code is not None or city_id is not None:
            # Real, closed gap: `formatted`/`formatted_single_line` is a
            # denormalized display string set once at creation
            # (CreateAddress's own pattern) -- never previously
            # regenerated on update, so editing the city or street left
            # the OLD city/line1 visible in `formatted_single_line`
            # while the real, authoritative `city_id`/`line1` fields
            # underneath had already changed. Re-derives it the exact
            # same way CreateAddress does, only when a field it depends
            # on actually changed.
            city = self._city_repo.get_by_id(address.city_id)
            if city is not None:
                address.set_formatted(AddressNormalizer.format(address.line1, address.line2, city.name, None, "", str(address.postal_code) if address.postal_code else None))
        saved = self._repo.save(address)

        self._ctx.stage_events([("AddressUpdated", event.to_payload())])
        self._ctx.audit().updated(entity_type="Address", entity_id=str(address_id), before=event.before, after=event.after)
        self._ctx.invalidate_geo_cache("address")
        return saved


class DeleteAddress:
    def __init__(self, repo: AddressRepository, ctx: GeoServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, address_id: uuid.UUID) -> None:
        address = self._repo.get_by_id(address_id)
        if address is None:
            raise ResourceNotFound("Address not found.")
        self._repo.delete(address_id)

        from apps.geo.domain.events import AddressDeleted

        self._ctx.stage_events([("AddressDeleted", AddressDeleted(address_id=address_id).to_payload())])
        self._ctx.audit().deleted(entity_type="Address", entity_id=str(address_id), before={"owner_id": str(address.owner_id)})
        self._ctx.invalidate_geo_cache("address")


class NormalizeAddress:
    """Read-only utility service: given raw address parts, returns the FormattedAddress + normalized signature without persisting anything -- used by client-side 'preview before save' flows."""

    def __init__(self, city_repo: CityRepository) -> None:
        self._city_repo = city_repo

    def execute(self, line1: str, line2: str | None, city_id: uuid.UUID, postal_code: str | None):
        city = self._city_repo.get_by_id(city_id)
        if city is None:
            raise GeoEntityNotFound(f"City '{city_id}' does not exist.")
        formatted = AddressNormalizer.format(line1, line2, city.name, None, "", postal_code)
        signature = AddressNormalizer.normalized_signature(line1, line2, str(city_id), postal_code)
        return formatted, signature


class ValidateAddress:
    """Read-only utility service: structural validation only (does this address have the required fields, is the postal code well-formed) -- does not check for duplicates (that's NormalizeAddress + CreateAddress's job) or geocode (ReverseGeocode's job)."""

    def __init__(self, city_repo: CityRepository, country_repo: CountryRepository) -> None:
        self._city_repo = city_repo
        self._country_repo = country_repo

    def execute(self, country_id: uuid.UUID, city_id: uuid.UUID, line1: str, postal_code: str | None = None) -> bool:
        if self._country_repo.get_by_id(country_id) is None:
            raise GeoEntityNotFound(f"Country '{country_id}' does not exist.")
        if self._city_repo.get_by_id(city_id) is None:
            raise GeoEntityNotFound(f"City '{city_id}' does not exist.")
        from apps.geo.domain.value_objects import AddressLine

        AddressLine(line1)
        if postal_code:
            PostalCode(postal_code)
        return True


class AssignCoordinates:
    def __init__(self, repo: AddressRepository, ctx: GeoServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, address_id: uuid.UUID, latitude: float, longitude: float, source: str = "manual", accuracy_meters: float | None = None) -> Address:
        address = self._repo.get_by_id(address_id)
        if address is None:
            raise ResourceNotFound("Address not found.")

        point = GeoPoint(coordinate=Coordinate.of(latitude, longitude), accuracy_meters=round(accuracy_meters, 1) if accuracy_meters is not None else None)
        address.assign_coordinate(AddressCoordinate(point=point, source=source))
        saved = self._repo.save(address)

        self._ctx.audit().updated(entity_type="Address", entity_id=str(address_id), before={}, after={"latitude": latitude, "longitude": longitude})
        self._ctx.invalidate_geo_cache("address")
        return saved
