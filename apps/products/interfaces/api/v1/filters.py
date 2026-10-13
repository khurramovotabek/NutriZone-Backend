"""
Products list/search filter parsing.

Matches Enterprise REST API Blueprint §10's uniform `filter[field]=value`
query-parameter shape, exactly matching the pattern established by
`apps/identity/interfaces/api/v1/filters.py`. Kept as plain parsing
functions rather than a django-filter FilterSet, since the Application
Services (queries.py) take plain keyword arguments, not a queryset --
this module's only job is translating `request.query_params` into
those calls' arguments, with no query-building logic of its own (that
stays inside the repository/selector layer, per Django Implementation
Blueprint §3).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from apps.products.domain.enums import AgeGroup, Availability, Gender, NutritionCategory, ProductStatus
from common.exceptions import ValidationFailed

ALLOWED_SORT_FIELDS = {"created_at", "-created_at", "name", "-name", "relevance", "price", "-price", "-rating", "-popularity", "-discount"}
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class CatalogListParams:
    category_id: uuid.UUID | None
    brand_id: uuid.UUID | None
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class SearchParams:
    query: str
    filters: dict = field(default_factory=dict)
    sort: str = "-created_at"
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE


@dataclass(frozen=True, slots=True)
class AdminCatalogListParams:
    status: str | None
    query: str | None
    page: int
    page_size: int


def _parse_uuid(raw: str | None, field_name: str) -> uuid.UUID | None:
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise ValidationFailed(f"'{raw}' is not a valid UUID for {field_name}.", details={"fields": [{"field": field_name, "code": "INVALID_FORMAT"}]}) from exc


def _parse_pagination(query_params) -> tuple[int, int]:
    try:
        page = max(int(query_params.get("page", 1)), 1)
        page_size = min(max(int(query_params.get("page_size", DEFAULT_PAGE_SIZE)), 1), MAX_PAGE_SIZE)
    except ValueError as exc:
        raise ValidationFailed("page/page_size must be integers.") from exc
    return page, page_size


def parse_catalog_list_params(query_params) -> CatalogListParams:
    page, page_size = _parse_pagination(query_params)
    return CatalogListParams(
        category_id=_parse_uuid(query_params.get("filter[category_id]"), "filter[category_id]"),
        brand_id=_parse_uuid(query_params.get("filter[brand_id]"), "filter[brand_id]"),
        page=page, page_size=page_size,
    )


def _csv(raw: str | None) -> list[str]:
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


def _parse_range_filters(query_params) -> dict:
    """Minimum rating (1..5) and price range, validated as numbers."""
    filters: dict = {}
    rating_gte = query_params.get("filter[rating][gte]")
    if rating_gte:
        try:
            rating_value = float(rating_gte)
        except ValueError:
            rating_value = -1
        if not 1 <= rating_value <= 5:
            raise ValidationFailed("filter[rating][gte] must be a number from 1 to 5.", details={"fields": [{"field": "filter[rating][gte]", "code": "INVALID"}]})
        filters["rating_gte"] = rating_gte
    price_min = query_params.get("filter[price][gte]")
    price_max = query_params.get("filter[price][lte]")
    for raw, name in ((price_min, "filter[price][gte]"), (price_max, "filter[price][lte]")):
        if raw:
            try:
                float(raw)
            except ValueError:
                raise ValidationFailed(f"{name} must be a number.", details={"fields": [{"field": name, "code": "INVALID"}]}) from None
    if price_min or price_max:
        filters["price"] = {"gte": price_min, "lte": price_max}

    return filters


def _parse_storefront_filters(query_params) -> dict:
    """The storefront catalog's own filters: brands, flavours and sizes (each one value or a comma-separated "any of" list), minimum rating, and price range."""
    filters: dict = {}
    # filter[brand_id], filter[flavor_id] and filter[size] accept one value or a comma-separated list ("any of").
    brand_ids = [str(_parse_uuid(b, "filter[brand_id]")) for b in _csv(query_params.get("filter[brand_id]"))]
    if brand_ids:
        filters["brand_ids"] = brand_ids
        filters["brand_id"] = brand_ids[0]  # kept for callers that read the single value
    flavour_ids = [str(_parse_uuid(f, "filter[flavor_id]")) for f in _csv(query_params.get("filter[flavor_id]"))]
    if flavour_ids:
        filters["flavour_ids"] = flavour_ids
        filters["flavor_id"] = flavour_ids[0]
    sizes = _csv(query_params.get("filter[size]"))
    if sizes:
        filters["sizes"] = sizes
    goals = _csv(query_params.get("filter[goal]"))
    if goals:
        from apps.products.infrastructure.goals import GOALS

        bad = [g for g in goals if g not in GOALS]
        if bad:
            raise ValidationFailed(f"Unknown goal: {bad[0]}. Allowed: {', '.join(GOALS)}", details={"fields": [{"field": "filter[goal]", "code": "INVALID_CHOICE"}]})
        filters["goals"] = goals
    filters.update(_parse_range_filters(query_params))
    if query_params.get("filter[on_sale]") in ("1", "true"):
        filters["on_sale"] = True
    return filters


def parse_search_params(query_params) -> SearchParams:
    page, page_size = _parse_pagination(query_params)
    sort = query_params.get("sort", "-created_at")
    if sort not in ALLOWED_SORT_FIELDS:
        raise ValidationFailed(f"'{sort}' is not a sortable field. Allowed: {sorted(ALLOWED_SORT_FIELDS)}", details={"fields": [{"field": "sort", "code": "INVALID_CHOICE"}]})

    filters: dict = _parse_storefront_filters(query_params)
    category_id = _parse_uuid(query_params.get("filter[category_id]"), "filter[category_id]")
    if category_id:
        filters["category_id"] = str(category_id)

    manufacturer_id = query_params.get("filter[manufacturer_id]")
    if manufacturer_id:
        filters["manufacturer_id"] = manufacturer_id  # validated as UUID at the selector layer's own boundary
    package_size_id = query_params.get("filter[package_size_id]")
    if package_size_id:
        filters["package_size_id"] = package_size_id
    product_form_id = query_params.get("filter[product_form_id]")
    if product_form_id:
        filters["product_form_id"] = product_form_id

    tags = query_params.get("filter[tags]")
    if tags:
        filters["tags"] = tags.split(",")

    availability = query_params.get("filter[availability]")
    if availability:
        if availability not in Availability.values():
            raise ValidationFailed(f"'{availability}' is not a valid availability filter.", details={"fields": [{"field": "filter[availability]", "code": "INVALID_CHOICE"}]})
        filters["availability"] = availability

    nutrition_category = query_params.get("filter[nutrition_category]")
    if nutrition_category:
        if nutrition_category not in NutritionCategory.values():
            raise ValidationFailed(f"'{nutrition_category}' is not a valid nutrition category filter.", details={"fields": [{"field": "filter[nutrition_category]", "code": "INVALID_CHOICE"}]})
        filters["nutrition_category"] = nutrition_category

    gender = query_params.get("filter[gender]")
    if gender:
        if gender not in Gender.values():
            raise ValidationFailed(f"'{gender}' is not a valid gender filter.", details={"fields": [{"field": "filter[gender]", "code": "INVALID_CHOICE"}]})
        filters["gender"] = gender

    age_group = query_params.get("filter[age_group]")
    if age_group:
        if age_group not in AgeGroup.values():
            raise ValidationFailed(f"'{age_group}' is not a valid age_group filter.", details={"fields": [{"field": "filter[age_group]", "code": "INVALID_CHOICE"}]})
        filters["age_group"] = age_group

    for date_field in ("created_at", "updated_at"):
        gte = query_params.get(f"filter[{date_field}][gte]")
        lte = query_params.get(f"filter[{date_field}][lte]")
        if gte or lte:
            filters[date_field] = {"gte": gte, "lte": lte}

    for exact_field in ("sku", "slug", "barcode"):
        value = query_params.get(f"filter[{exact_field}]")
        if value:
            filters[exact_field] = value

    return SearchParams(query=query_params.get("q", ""), filters=filters, sort=sort, page=page, page_size=page_size)


def parse_admin_catalog_list_params(query_params) -> AdminCatalogListParams:
    page, page_size = _parse_pagination(query_params)
    status = query_params.get("filter[status]")
    if status and status not in ProductStatus.values():
        raise ValidationFailed(f"'{status}' is not a valid status filter.", details={"fields": [{"field": "filter[status]", "code": "INVALID_CHOICE"}]})
    return AdminCatalogListParams(status=status, query=query_params.get("q"), page=page, page_size=page_size)
