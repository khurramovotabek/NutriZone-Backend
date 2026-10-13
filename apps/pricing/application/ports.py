"""
Application-layer ports (abstract interfaces) for Pricing.

Matches the pattern established by every prior module's
application/ports.py. Cross-cutting ports (Cache/Audit/Metrics/Outbox/
Clock/Health) are consumed directly from `core/`, not redeclared.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol

from apps.pricing.domain.aggregates import Campaign, Coupon, PriceList, PriceSnapshot, PricingRule


class PriceListRepository(Protocol):
    def get_by_id(self, price_list_id: uuid.UUID) -> PriceList | None: ...

    def get_by_code(self, code: str) -> PriceList | None: ...

    def get_active_for_region(self, region: str | None) -> PriceList | None: ...

    def save(self, price_list: PriceList) -> PriceList: ...

    def code_exists(self, code: str, exclude_id: uuid.UUID | None = None) -> bool: ...

    def list_for_admin(self, status: str | None, page: int, page_size: int) -> tuple[list[PriceList], int]: ...


class PricingRuleRepository(Protocol):
    def get_by_id(self, pricing_rule_id: uuid.UUID) -> PricingRule | None: ...

    def save(self, pricing_rule: PricingRule) -> PricingRule: ...

    def list_active_at(self, at: datetime, rule_type: str | None = None) -> list[PricingRule]: ...


class CampaignRepository(Protocol):
    def get_by_id(self, campaign_id: uuid.UUID) -> Campaign | None: ...

    def save(self, campaign: Campaign) -> Campaign: ...

    def list_active_for_target(self, target_type: str, target_id: uuid.UUID, at: datetime) -> list[Campaign]: ...


class CouponRepository(Protocol):
    def get_by_id(self, coupon_id: uuid.UUID) -> Coupon | None: ...

    def get_by_code(self, code: str) -> Coupon | None: ...

    def save(self, coupon: Coupon) -> Coupon: ...

    def code_exists(self, code: str, exclude_id: uuid.UUID | None = None) -> bool: ...


class PriceSnapshotRepository(Protocol):
    def get_by_id(self, snapshot_id: uuid.UUID) -> PriceSnapshot | None: ...

    def get_by_token(self, token: str) -> PriceSnapshot | None: ...

    def save(self, snapshot: PriceSnapshot) -> PriceSnapshot: ...


class PricingSearchGateway(Protocol):
    """Anti-Corruption Layer boundary for pricing search -- same launch-stage Postgres-backed approach as every other module's search backend."""

    def search(self, query: str, filters: dict, page: int, page_size: int) -> tuple[list[dict], int]: ...
