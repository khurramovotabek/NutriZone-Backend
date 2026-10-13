"""
Geo & Location repositories.

Concrete implementations of application/ports.py's Protocols -- maps
ORM rows to domain dataclasses, catches ORM-level exceptions and
re-raises as domain exceptions, matching the pattern established by
`apps/products/infrastructure/repositories.py`.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from django.db import IntegrityError

from apps.geo.domain.aggregates import Address, City, Country, District, Neighborhood, Region
from apps.geo.domain.entities import AddressCoordinate, AddressMetadata as AddressMetadataEntity
from apps.geo.domain.enums import AddressType, CityStatus, CountryStatus, DistrictStatus, NeighborhoodStatus, RegionStatus
from apps.geo.domain.value_objects import (
    CityCode, Coordinate, CountryCode, DistrictCode, FormattedAddress, GeoPoint,
    LocationSlug, NeighborhoodCode, PostalCode, RegionCode, Timezone,
)
from apps.geo.infrastructure import models as orm
from common.exceptions import ConflictError

_DEFAULT_LOCALE = "en"


def _t(row, related_name: str = "translations"):
    return getattr(row, related_name).filter(locale_code=_DEFAULT_LOCALE).first()


class DjangoCountryRepository:
    def get_by_id(self, country_id: uuid.UUID) -> Country | None:
        row = orm.Country.objects.filter(id=country_id).first()
        return self._to_domain(row) if row else None

    def get_by_code(self, code: str) -> Country | None:
        row = orm.Country.objects.filter(code=code).first()
        return self._to_domain(row) if row else None

    def save(self, country: Country) -> Country:
        try:
            row, _ = orm.Country.objects.update_or_create(
                id=country.id, defaults={"code": country.code.value, "status": country.status.value, "timezone": str(country.timezone) if country.timezone else None}
            )
        except IntegrityError as exc:
            raise ConflictError("A country with conflicting unique fields already exists.") from exc
        orm.CountryTranslation.objects.update_or_create(country=row, locale_code=_DEFAULT_LOCALE, defaults={"name": country.name, "slug": country.slug.value})
        return country

    def code_exists(self, code: str, exclude_id: uuid.UUID | None = None) -> bool:
        qs = orm.Country.objects.filter(code=code)
        if exclude_id:
            qs = qs.exclude(id=exclude_id)
        return qs.exists()

    def slug_exists(self, slug: str, exclude_id: uuid.UUID | None = None) -> bool:
        qs = orm.CountryTranslation.objects.filter(slug=slug, locale_code=_DEFAULT_LOCALE)
        if exclude_id:
            qs = qs.exclude(country_id=exclude_id)
        return qs.exists()

    def delete(self, country_id: uuid.UUID) -> None:
        row = orm.Country.objects.filter(id=country_id).first()
        if row:
            row.delete()

    def list_active(self, page: int, page_size: int) -> tuple[list[Country], int]:
        qs = orm.Country.objects.filter(status=CountryStatus.ACTIVE.value)
        total = qs.count()
        rows = qs.order_by("code")[(page - 1) * page_size : page * page_size]
        return [self._to_domain(r) for r in rows], total

    def _to_domain(self, row: orm.Country) -> Country:
        t = _t(row)
        return Country(
            id=row.id, code=CountryCode(row.code), slug=LocationSlug(t.slug if t else str(row.id)), name=t.name if t else row.code,
            status=CountryStatus(row.status), timezone=Timezone(row.timezone) if row.timezone else None,
        )


class DjangoRegionRepository:
    def get_by_id(self, region_id: uuid.UUID) -> Region | None:
        row = orm.Region.objects.filter(id=region_id).first()
        return self._to_domain(row) if row else None

    def save(self, region: Region) -> Region:
        try:
            row, _ = orm.Region.objects.update_or_create(id=region.id, defaults={"country_id": region.country_id, "code": region.code.value, "status": region.status.value})
        except IntegrityError as exc:
            raise ConflictError("A region with conflicting unique fields already exists.") from exc
        orm.RegionTranslation.objects.update_or_create(region=row, locale_code=_DEFAULT_LOCALE, defaults={"name": region.name, "slug": region.slug.value})
        return region

    def code_exists(self, code: str, exclude_id: uuid.UUID | None = None) -> bool:
        qs = orm.Region.objects.filter(code=code)
        if exclude_id:
            qs = qs.exclude(id=exclude_id)
        return qs.exists()

    def delete(self, region_id: uuid.UUID) -> None:
        row = orm.Region.objects.filter(id=region_id).first()
        if row:
            row.delete()

    def list_by_country(self, country_id: uuid.UUID, page: int, page_size: int) -> tuple[list[Region], int]:
        qs = orm.Region.objects.filter(country_id=country_id, status=RegionStatus.ACTIVE.value)
        total = qs.count()
        rows = qs.order_by("code")[(page - 1) * page_size : page * page_size]
        return [self._to_domain(r) for r in rows], total

    def _to_domain(self, row: orm.Region) -> Region:
        t = _t(row)
        return Region(id=row.id, country_id=row.country_id, code=RegionCode(row.code), slug=LocationSlug(t.slug if t else str(row.id)), name=t.name if t else row.code, status=RegionStatus(row.status))


class DjangoDistrictRepository:
    def get_by_id(self, district_id: uuid.UUID) -> District | None:
        row = orm.District.objects.filter(id=district_id).first()
        return self._to_domain(row) if row else None

    def save(self, district: District) -> District:
        try:
            row, _ = orm.District.objects.update_or_create(id=district.id, defaults={"region_id": district.region_id, "code": district.code.value, "status": district.status.value})
        except IntegrityError as exc:
            raise ConflictError("A district with conflicting unique fields already exists.") from exc
        orm.DistrictTranslation.objects.update_or_create(district=row, locale_code=_DEFAULT_LOCALE, defaults={"name": district.name, "slug": district.slug.value})
        return district

    def code_exists(self, code: str, exclude_id: uuid.UUID | None = None) -> bool:
        qs = orm.District.objects.filter(code=code)
        if exclude_id:
            qs = qs.exclude(id=exclude_id)
        return qs.exists()

    def delete(self, district_id: uuid.UUID) -> None:
        row = orm.District.objects.filter(id=district_id).first()
        if row:
            row.delete()

    def list_by_region(self, region_id: uuid.UUID, page: int, page_size: int) -> tuple[list[District], int]:
        qs = orm.District.objects.filter(region_id=region_id, status=DistrictStatus.ACTIVE.value)
        total = qs.count()
        rows = qs.order_by("code")[(page - 1) * page_size : page * page_size]
        return [self._to_domain(r) for r in rows], total

    def _to_domain(self, row: orm.District) -> District:
        t = _t(row)
        return District(id=row.id, region_id=row.region_id, code=DistrictCode(row.code), slug=LocationSlug(t.slug if t else str(row.id)), name=t.name if t else row.code, status=DistrictStatus(row.status))


class DjangoCityRepository:
    def get_by_id(self, city_id: uuid.UUID) -> City | None:
        row = orm.City.objects.filter(id=city_id).first()
        return self._to_domain(row) if row else None

    def save(self, city: City) -> City:
        try:
            row, _ = orm.City.objects.update_or_create(
                id=city.id,
                defaults={
                    "region_id": city.region_id, "district_id": city.district_id, "code": city.code.value, "status": city.status.value,
                    "center_latitude": city.center_point.coordinate.latitude.value if city.center_point else None,
                    "center_longitude": city.center_point.coordinate.longitude.value if city.center_point else None,
                    "timezone": str(city.timezone) if city.timezone else None,
                },
            )
        except IntegrityError as exc:
            raise ConflictError("A city with conflicting unique fields already exists.") from exc
        orm.CityTranslation.objects.update_or_create(city=row, locale_code=_DEFAULT_LOCALE, defaults={"name": city.name, "slug": city.slug.value})
        return city

    def code_exists(self, code: str, exclude_id: uuid.UUID | None = None) -> bool:
        qs = orm.City.objects.filter(code=code)
        if exclude_id:
            qs = qs.exclude(id=exclude_id)
        return qs.exists()

    def delete(self, city_id: uuid.UUID) -> None:
        row = orm.City.objects.filter(id=city_id).first()
        if row:
            row.delete()

    def list_by_region(self, region_id: uuid.UUID | None, page: int, page_size: int) -> tuple[list[City], int]:
        qs = orm.City.objects.filter(status=CityStatus.ACTIVE.value)
        if region_id:
            qs = qs.filter(region_id=region_id)
        total = qs.count()
        rows = qs.order_by("code")[(page - 1) * page_size : page * page_size]
        return [self._to_domain(r) for r in rows], total

    def find_nearest(self, latitude: float, longitude: float, limit: int) -> list[City]:
        """
        A bounding-box pre-filter (cheap, index-friendly) followed by an
        in-Python haversine sort for the final ranking -- avoids
        requiring PostGIS for this phase while still giving a correct
        nearest-N result for the city-count scale this table will
        realistically hold (a few thousand rows, not millions).
        """
        from apps.geo.domain.services import GeoDistanceCalculator

        degree_margin = 2.0  # ~200km box, generous enough to always contain the true nearest city for typical city density
        qs = orm.City.objects.filter(
            status=CityStatus.ACTIVE.value,
            center_latitude__gte=latitude - degree_margin, center_latitude__lte=latitude + degree_margin,
            center_longitude__gte=longitude - degree_margin, center_longitude__lte=longitude + degree_margin,
        )
        target = Coordinate.of(latitude, longitude)
        candidates = [(self._to_domain(r), GeoDistanceCalculator.distance_meters(target, Coordinate.of(r.center_latitude, r.center_longitude))) for r in qs if r.center_latitude is not None]
        candidates.sort(key=lambda pair: pair[1])
        return [c for c, _ in candidates[:limit]]

    def _to_domain(self, row: orm.City) -> City:
        t = _t(row)
        center = GeoPoint(coordinate=Coordinate.of(row.center_latitude, row.center_longitude)) if row.center_latitude is not None else None
        return City(
            id=row.id, region_id=row.region_id, district_id=row.district_id, code=CityCode(row.code), slug=LocationSlug(t.slug if t else str(row.id)),
            name=t.name if t else row.code, status=CityStatus(row.status), center_point=center, timezone=Timezone(row.timezone) if row.timezone else None,
        )


class DjangoNeighborhoodRepository:
    def get_by_id(self, neighborhood_id: uuid.UUID) -> Neighborhood | None:
        row = orm.Neighborhood.objects.filter(id=neighborhood_id).first()
        return self._to_domain(row) if row else None

    def save(self, neighborhood: Neighborhood) -> Neighborhood:
        try:
            row, _ = orm.Neighborhood.objects.update_or_create(
                id=neighborhood.id,
                defaults={
                    "city_id": neighborhood.city_id, "code": neighborhood.code.value, "status": neighborhood.status.value,
                    "center_latitude": neighborhood.center_point.coordinate.latitude.value if neighborhood.center_point else None,
                    "center_longitude": neighborhood.center_point.coordinate.longitude.value if neighborhood.center_point else None,
                },
            )
        except IntegrityError as exc:
            raise ConflictError("A neighborhood with conflicting unique fields already exists.") from exc
        orm.NeighborhoodTranslation.objects.update_or_create(neighborhood=row, locale_code=_DEFAULT_LOCALE, defaults={"name": neighborhood.name, "slug": neighborhood.slug.value})
        return neighborhood

    def code_exists(self, code: str, exclude_id: uuid.UUID | None = None) -> bool:
        qs = orm.Neighborhood.objects.filter(code=code)
        if exclude_id:
            qs = qs.exclude(id=exclude_id)
        return qs.exists()

    def delete(self, neighborhood_id: uuid.UUID) -> None:
        row = orm.Neighborhood.objects.filter(id=neighborhood_id).first()
        if row:
            row.delete()

    def list_by_city(self, city_id: uuid.UUID, page: int, page_size: int) -> tuple[list[Neighborhood], int]:
        qs = orm.Neighborhood.objects.filter(city_id=city_id, status=NeighborhoodStatus.ACTIVE.value)
        total = qs.count()
        rows = qs.order_by("code")[(page - 1) * page_size : page * page_size]
        return [self._to_domain(r) for r in rows], total

    def _to_domain(self, row: orm.Neighborhood) -> Neighborhood:
        t = _t(row)
        center = GeoPoint(coordinate=Coordinate.of(row.center_latitude, row.center_longitude)) if row.center_latitude is not None else None
        return Neighborhood(id=row.id, city_id=row.city_id, code=NeighborhoodCode(row.code), slug=LocationSlug(t.slug if t else str(row.id)), name=t.name if t else row.code, status=NeighborhoodStatus(row.status), center_point=center)


class DjangoAddressRepository:
    def get_by_id(self, address_id: uuid.UUID) -> Address | None:
        row = orm.Address.objects.filter(id=address_id).select_related("metadata").first()
        return self._to_domain(row) if row else None

    def save(self, address: Address) -> Address:
        from apps.geo.domain.services import AddressNormalizer

        signature = AddressNormalizer.normalized_signature(address.line1, address.line2, str(address.city_id), str(address.postal_code) if address.postal_code else None)
        row, _ = orm.Address.objects.update_or_create(
            id=address.id,
            defaults={
                "owner_type": address.owner_type, "owner_id": address.owner_id, "address_type": address.address_type.value,
                "country_id": address.country_id, "region_id": address.region_id, "district_id": address.district_id,
                "city_id": address.city_id, "neighborhood_id": address.neighborhood_id,
                "line1": address.line1, "line2": address.line2, "postal_code": str(address.postal_code) if address.postal_code else None,
                "recipient_name": address.recipient_name, "recipient_phone": address.recipient_phone,
                "recipient_telegram_username": address.recipient_telegram_username,
                "formatted_single_line": address.formatted.single_line if address.formatted else None,
                "formatted_lines": list(address.formatted.lines) if address.formatted else [],
                "coordinate_latitude": address.coordinate.point.coordinate.latitude.value if address.coordinate else None,
                "coordinate_longitude": address.coordinate.point.coordinate.longitude.value if address.coordinate else None,
                "coordinate_accuracy_meters": address.coordinate.point.accuracy_meters if address.coordinate else None,
                "coordinate_source": address.coordinate.source if address.coordinate else None,
                "normalized_signature": signature, "is_default": address.is_default,
            },
        )
        orm.AddressMetadata.objects.update_or_create(
            address=row,
            defaults={
                "building_name": address.metadata.building_name, "entrance": address.metadata.entrance, "floor": address.metadata.floor, "unit": address.metadata.unit,
                "delivery_instructions": address.metadata.delivery_instructions, "entrance_code": address.metadata.entrance_code,
            },
        )
        return address

    def delete(self, address_id: uuid.UUID) -> None:
        row = orm.Address.objects.filter(id=address_id).first()
        if row:
            row.delete()

    def list_signatures_for_owner(self, owner_type: str, owner_id: uuid.UUID) -> frozenset[str]:
        return frozenset(orm.Address.objects.filter(owner_type=owner_type, owner_id=owner_id).values_list("normalized_signature", flat=True))

    def list_for_owner(self, owner_type: str, owner_id: uuid.UUID) -> list[Address]:
        rows = orm.Address.objects.filter(owner_type=owner_type, owner_id=owner_id).select_related("metadata")
        return [self._to_domain(r) for r in rows]

    def _to_domain(self, row: orm.Address) -> Address:
        coordinate = None
        if row.coordinate_latitude is not None:
            coordinate = AddressCoordinate(point=GeoPoint(coordinate=Coordinate.of(row.coordinate_latitude, row.coordinate_longitude), accuracy_meters=row.coordinate_accuracy_meters), source=row.coordinate_source or "manual")
        try:
            metadata_row = row.metadata
            metadata = AddressMetadataEntity(building_name=metadata_row.building_name, entrance=metadata_row.entrance, floor=metadata_row.floor, unit=metadata_row.unit, delivery_instructions=metadata_row.delivery_instructions, entrance_code=metadata_row.entrance_code)
        except orm.AddressMetadata.DoesNotExist:
            metadata = AddressMetadataEntity()
        formatted = FormattedAddress(single_line=row.formatted_single_line, lines=tuple(row.formatted_lines)) if row.formatted_single_line else None
        return Address(
            id=row.id, owner_type=row.owner_type, owner_id=row.owner_id, address_type=AddressType(row.address_type),
            country_id=row.country_id, city_id=row.city_id, region_id=row.region_id, district_id=row.district_id, neighborhood_id=row.neighborhood_id,
            line1=row.line1, line2=row.line2, postal_code=PostalCode(row.postal_code) if row.postal_code else None,
            recipient_name=row.recipient_name, recipient_phone=row.recipient_phone, recipient_telegram_username=row.recipient_telegram_username,
            coordinate=coordinate, metadata=metadata, formatted=formatted, is_default=row.is_default, created_at=row.created_at,
        )
