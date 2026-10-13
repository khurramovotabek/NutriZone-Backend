"""
Geo & Location read-model selectors -- optimized, read-only Postgres
queries backing `application/selectors.py::GeoSelector` and the query
Application Services. No business logic, matching the pattern
established by `apps/products/infrastructure/selectors.py`.
"""
from __future__ import annotations

import uuid

from django.db.models import Q

from apps.geo.domain.enums import CityStatus, CountryStatus, DistrictStatus, NeighborhoodStatus, RegionStatus
from apps.geo.infrastructure import models as orm

_DEFAULT_LOCALE = "en"
_FALLBACK = ("uz", "en", "ru")


def _name(row) -> str:
    """The name in the request's language (Accept-Language / ?lang via LocaleMiddleware), then uz → en → ru.
    Reads the prefetched translations -- the storefront used to get every place in English ("Tashkent Region")."""
    from django.utils import translation

    names = {t.locale_code: t.name for t in row.translations.all()}
    active = (translation.get_language() or "uz")[:2]
    for code in (active, *_FALLBACK):
        if names.get(code):
            return names[code]
    return str(row.id)


def _slug(row) -> str:
    t = row.translations.filter(locale_code=_DEFAULT_LOCALE).first()
    return t.slug if t else str(row.id)


class CountryTreeSelector:
    def tree(self) -> list[dict]:
        rows = orm.Country.objects.filter(status=CountryStatus.ACTIVE.value).prefetch_related("translations").order_by("code")
        return [{"id": str(r.id), "code": r.code, "name": _name(r), "slug": _slug(r)} for r in rows]


class RegionTreeSelector:
    def tree(self, country_id: uuid.UUID) -> list[dict]:
        rows = orm.Region.objects.filter(country_id=country_id, status=RegionStatus.ACTIVE.value).prefetch_related("translations").order_by("code")
        return [{"id": str(r.id), "code": r.code, "name": _name(r), "country_id": str(r.country_id)} for r in rows]


class DistrictTreeSelector:
    def tree(self, region_id: uuid.UUID) -> list[dict]:
        rows = orm.District.objects.filter(region_id=region_id, status=DistrictStatus.ACTIVE.value).prefetch_related("translations").order_by("code")
        return [{"id": str(r.id), "code": r.code, "name": _name(r), "region_id": str(r.region_id)} for r in rows]


class CityLookupSelector:
    def list(self, region_id: uuid.UUID | None, page: int, page_size: int) -> tuple[list[dict], int]:
        qs = orm.City.objects.filter(status=CityStatus.ACTIVE.value)
        if region_id:
            qs = qs.filter(region_id=region_id)
        total = qs.count()
        start = (page - 1) * page_size
        rows = qs.prefetch_related("translations")[start : start + page_size]
        return [self._card(r) for r in rows], total

    def get_by_id(self, city_id: uuid.UUID) -> dict | None:
        row = orm.City.objects.filter(id=city_id).prefetch_related("translations").first()
        return self._card(row) if row else None

    def _card(self, row: orm.City) -> dict:
        return {
            "id": str(row.id), "code": row.code, "name": _name(row), "region_id": str(row.region_id),
            "district_id": str(row.district_id) if row.district_id else None,
            "center_latitude": row.center_latitude, "center_longitude": row.center_longitude, "timezone": row.timezone,
        }


class NeighborhoodLookupSelector:
    def list(self, city_id: uuid.UUID, page: int, page_size: int) -> tuple[list[dict], int]:
        qs = orm.Neighborhood.objects.filter(city_id=city_id, status=NeighborhoodStatus.ACTIVE.value)
        total = qs.count()
        start = (page - 1) * page_size
        rows = qs.prefetch_related("translations")[start : start + page_size]
        return [{"id": str(r.id), "code": r.code, "name": _name(r), "city_id": str(r.city_id)} for r in rows], total


class AddressLookupSelector:
    def get_by_id(self, address_id: uuid.UUID) -> dict | None:
        row = orm.Address.objects.filter(id=address_id).select_related("metadata", "city", "country").first()
        if row is None:
            return None
        return {
            "id": str(row.id), "owner_type": row.owner_type, "owner_id": str(row.owner_id), "address_type": row.address_type,
            "line1": row.line1, "line2": row.line2, "formatted_single_line": row.formatted_single_line,
            "city_id": str(row.city_id), "country_id": str(row.country_id),
            "coordinate_latitude": row.coordinate_latitude, "coordinate_longitude": row.coordinate_longitude,
            "is_default": row.is_default,
        }


class HierarchyTraversalSelector:
    """Backs the 'Administrative Hierarchy' requirement -- given a City, walks up to its Region and Country in one shaped payload, avoiding N+1 lookups a client would otherwise need three separate requests for."""

    def ancestors_of_city(self, city_id: uuid.UUID) -> dict | None:
        row = orm.City.objects.filter(id=city_id).select_related("region__country", "district").prefetch_related("translations", "region__translations", "region__country__translations").first()
        if row is None:
            return None
        return {
            "city": {"id": str(row.id), "name": _name(row)},
            "district": {"id": str(row.district_id), "name": _name(row.district)} if row.district_id else None,
            "region": {"id": str(row.region_id), "name": _name(row.region)},
            "country": {"id": str(row.region.country_id), "name": _name(row.region.country)},
        }


class BoundingBoxSelector:
    """Backs map-viewport queries -- coarse index-friendly bounding-box filter over active cities."""

    def cities_within(self, north_east_lat: float, north_east_lng: float, south_west_lat: float, south_west_lng: float) -> list[dict]:
        rows = orm.City.objects.filter(
            status=CityStatus.ACTIVE.value,
            center_latitude__gte=south_west_lat, center_latitude__lte=north_east_lat,
            center_longitude__gte=south_west_lng, center_longitude__lte=north_east_lng,
        ).prefetch_related("translations")
        return [{"id": str(r.id), "name": _name(r), "center_latitude": r.center_latitude, "center_longitude": r.center_longitude} for r in rows]


class DjangoGeoSearchBackend:
    """Implements `application/selectors.py::GeoSearchBackend` -- Postgres ILIKE/trigram search across country/region/city/neighborhood translation names, per Domain Architecture Specification §2.16's launch-stage approach (same as Products' search backend)."""

    def search(self, query: str, geo_level: str | None, page: int, page_size: int) -> tuple[list[dict], int]:
        results: list[dict] = []
        level_models = {
            "country": (orm.CountryTranslation, "country"),
            "region": (orm.RegionTranslation, "region"),
            "district": (orm.DistrictTranslation, "district"),
            "city": (orm.CityTranslation, "city"),
            "neighborhood": (orm.NeighborhoodTranslation, "neighborhood"),
        }
        levels_to_search = {geo_level: level_models[geo_level]} if geo_level and geo_level in level_models else level_models

        for level, (translation_model, fk_name) in levels_to_search.items():
            matches = translation_model.objects.filter(locale_code=_DEFAULT_LOCALE, name__icontains=query).select_related(fk_name)
            for m in matches:
                entity = getattr(m, fk_name)
                results.append({"id": str(entity.id), "geo_level": level, "name": m.name, "slug": m.slug})

        total = len(results)
        start = (page - 1) * page_size
        return results[start : start + page_size], total

    def autocomplete(self, partial: str, limit: int) -> list[str]:
        names: set[str] = set()
        for translation_model in (orm.CountryTranslation, orm.RegionTranslation, orm.CityTranslation, orm.NeighborhoodTranslation):
            names.update(translation_model.objects.filter(locale_code=_DEFAULT_LOCALE, name__istartswith=partial).values_list("name", flat=True)[:limit])
        return sorted(names)[:limit]
