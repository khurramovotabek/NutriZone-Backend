"""
Pricing list/search filter parsing.

Matches Enterprise REST API Blueprint §10's uniform `filter[field]=value`
shape, per every prior module's `interfaces/api/v1/filters.py` pattern
-- plain parsing functions, no query-building logic (that stays in the
selector/repository layer).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from apps.pricing.domain.enums import CampaignStatus, CouponStatus, PriceListStatus, PricingRuleStatus
from common.exceptions import ValidationFailed

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
ALLOWED_SORT_FIELDS = {"code", "-code", "name", "-name", "created_at", "-created_at"}


@dataclass(frozen=True, slots=True)
class PaginationParams:
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class PriceListFilterParams:
    status: str | None
    region: str | None
    sort: str
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class PricingRuleFilterParams:
    status: str | None
    rule_type: str | None
    membership_tier_code: str | None
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class CampaignFilterParams:
    status: str | None
    campaign_type: str | None
    active_only: bool
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class CouponFilterParams:
    status: str | None
    coupon_type: str | None
    page: int
    page_size: int


def _parse_pagination(query_params) -> tuple[int, int]:
    try:
        page = max(int(query_params.get("page", 1)), 1)
        page_size = min(max(int(query_params.get("page_size", DEFAULT_PAGE_SIZE)), 1), MAX_PAGE_SIZE)
    except ValueError as exc:
        raise ValidationFailed("page/page_size must be integers.") from exc
    return page, page_size


def parse_pagination(query_params) -> PaginationParams:
    page, page_size = _parse_pagination(query_params)
    return PaginationParams(page=page, page_size=page_size)


def parse_uuid_param(raw: str | None, field_name: str) -> uuid.UUID | None:
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise ValidationFailed(f"'{raw}' is not a valid UUID for {field_name}.", details={"fields": [{"field": field_name, "code": "INVALID_FORMAT"}]}) from exc


def parse_price_list_filter_params(query_params) -> PriceListFilterParams:
    page, page_size = _parse_pagination(query_params)
    status = query_params.get("filter[status]")
    if status and status not in PriceListStatus.values():
        raise ValidationFailed(f"'{status}' is not a valid status filter.", details={"fields": [{"field": "filter[status]", "code": "INVALID_CHOICE"}]})
    sort = query_params.get("sort", "-created_at")
    if sort not in ALLOWED_SORT_FIELDS:
        raise ValidationFailed(f"'{sort}' is not a sortable field. Allowed: {sorted(ALLOWED_SORT_FIELDS)}", details={"fields": [{"field": "sort", "code": "INVALID_CHOICE"}]})
    return PriceListFilterParams(status=status, region=query_params.get("filter[region]"), sort=sort, page=page, page_size=page_size)


def parse_pricing_rule_filter_params(query_params) -> PricingRuleFilterParams:
    page, page_size = _parse_pagination(query_params)
    status = query_params.get("filter[status]")
    if status and status not in PricingRuleStatus.values():
        raise ValidationFailed(f"'{status}' is not a valid status filter.", details={"fields": [{"field": "filter[status]", "code": "INVALID_CHOICE"}]})
    return PricingRuleFilterParams(status=status, rule_type=query_params.get("filter[rule_type]"), membership_tier_code=query_params.get("filter[membership_tier]"), page=page, page_size=page_size)


def parse_campaign_filter_params(query_params) -> CampaignFilterParams:
    page, page_size = _parse_pagination(query_params)
    status = query_params.get("filter[status]")
    if status and status not in CampaignStatus.values():
        raise ValidationFailed(f"'{status}' is not a valid status filter.", details={"fields": [{"field": "filter[status]", "code": "INVALID_CHOICE"}]})
    active_only = query_params.get("filter[active]", "").lower() == "true"
    return CampaignFilterParams(status=status, campaign_type=query_params.get("filter[campaign_type]"), active_only=active_only, page=page, page_size=page_size)


def parse_coupon_filter_params(query_params) -> CouponFilterParams:
    page, page_size = _parse_pagination(query_params)
    status = query_params.get("filter[status]")
    if status and status not in CouponStatus.values():
        raise ValidationFailed(f"'{status}' is not a valid status filter.", details={"fields": [{"field": "filter[status]", "code": "INVALID_CHOICE"}]})
    return CouponFilterParams(status=status, coupon_type=query_params.get("filter[coupon_type]"), page=page, page_size=page_size)
