"""
Geo & Location list/search filter parsing.

Matches Enterprise REST API Blueprint §10's uniform `filter[field]=value`
shape, per `apps.products.interfaces.api.v1.filters`'s exact pattern --
plain parsing functions, no query-building logic (that stays in the
selector/repository layer).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from common.exceptions import ValidationFailed

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


@dataclass(frozen=True, slots=True)
class PaginationParams:
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class SearchParams:
    query: str
    geo_level: str | None
    page: int
    page_size: int


def parse_pagination(query_params) -> PaginationParams:
    try:
        page = max(int(query_params.get("page", 1)), 1)
        page_size = min(max(int(query_params.get("page_size", DEFAULT_PAGE_SIZE)), 1), MAX_PAGE_SIZE)
    except ValueError as exc:
        raise ValidationFailed("page/page_size must be integers.") from exc
    return PaginationParams(page=page, page_size=page_size)


def parse_uuid_param(raw: str | None, field_name: str) -> uuid.UUID | None:
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise ValidationFailed(f"'{raw}' is not a valid UUID for {field_name}.", details={"fields": [{"field": field_name, "code": "INVALID_FORMAT"}]}) from exc


def parse_search_params(query_params) -> SearchParams:
    pagination = parse_pagination(query_params)
    geo_level = query_params.get("filter[geo_level]")
    allowed_levels = {"country", "region", "district", "city", "neighborhood", None}
    if geo_level not in allowed_levels:
        raise ValidationFailed(f"'{geo_level}' is not a valid geo_level filter.", details={"fields": [{"field": "filter[geo_level]", "code": "INVALID_CHOICE"}]})
    return SearchParams(query=query_params.get("q", ""), geo_level=geo_level, page=pagination.page, page_size=pagination.page_size)


def parse_bounding_box_params(query_params) -> dict:
    required = ["ne_lat", "ne_lng", "sw_lat", "sw_lng"]
    values = {}
    for key in required:
        raw = query_params.get(key)
        if raw is None:
            raise ValidationFailed(f"'{key}' is required for a bounding-box query.", details={"fields": [{"field": key, "code": "REQUIRED"}]})
        try:
            values[key] = float(raw)
        except ValueError as exc:
            raise ValidationFailed(f"'{key}' must be a number.", details={"fields": [{"field": key, "code": "INVALID_FORMAT"}]}) from exc
    return values


def parse_reverse_geocode_params(query_params) -> tuple[float, float]:
    lat_raw, lng_raw = query_params.get("latitude"), query_params.get("longitude")
    if lat_raw is None or lng_raw is None:
        raise ValidationFailed("latitude and longitude are both required.", details={"fields": [{"field": "latitude", "code": "REQUIRED"}]})
    try:
        return float(lat_raw), float(lng_raw)
    except ValueError as exc:
        raise ValidationFailed("latitude/longitude must be numbers.") from exc
