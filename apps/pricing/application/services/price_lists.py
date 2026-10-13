"""
Price List Application Services: CreatePriceList, ActivatePriceList,
ArchivePriceList, SetPrice.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from django.db import transaction
from django.utils import timezone as django_timezone

from apps.pricing.application.ports import PriceListRepository
from apps.pricing.application.services._shared import PricingServiceContext
from apps.pricing.domain.aggregates import PriceList
from apps.pricing.domain.enums import PriceChangeReason
from apps.pricing.domain.value_objects import Money, PriceListCode, RegionCode
from common.exceptions import ConflictError, ResourceNotFound


class CreatePriceList:
    def __init__(self, repo: PriceListRepository, ctx: PricingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, code: str, name: str, currency: str, region: str | None = None) -> PriceList:
        if self._repo.code_exists(code):
            raise ConflictError(f"Price list code '{code}' already exists.")

        price_list = PriceList(id=uuid.uuid4(), code=PriceListCode(code), name=name, currency=currency, region=RegionCode(region) if region else None)
        saved = self._repo.save(price_list)

        from apps.pricing.domain.events import PriceListCreated

        self._ctx.stage_events([("PriceListCreated", PriceListCreated(price_list_id=saved.id, code=code).to_payload())])
        self._ctx.audit().created(entity_type="PriceList", entity_id=str(saved.id), after={"code": code, "name": name})
        self._ctx.invalidate_pricing_cache()
        self._ctx.metric("price_lists_created_total")
        return saved


class ActivatePriceList:
    def __init__(self, repo: PriceListRepository, ctx: PricingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, price_list_id: uuid.UUID) -> PriceList:
        price_list = self._repo.get_by_id(price_list_id)
        if price_list is None:
            raise ResourceNotFound("Price list not found.")

        event = price_list.activate()
        saved = self._repo.save(price_list)

        self._ctx.stage_events([("PriceListActivated", event.to_payload())])
        self._ctx.audit().updated(entity_type="PriceList", entity_id=str(price_list_id), before={}, after={"status": "active"})
        self._ctx.invalidate_pricing_cache()
        return saved


class ArchivePriceList:
    def __init__(self, repo: PriceListRepository, ctx: PricingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, price_list_id: uuid.UUID) -> PriceList:
        price_list = self._repo.get_by_id(price_list_id)
        if price_list is None:
            raise ResourceNotFound("Price list not found.")

        event = price_list.archive()
        saved = self._repo.save(price_list)

        self._ctx.stage_events([("PriceListArchivedEvent", event.to_payload())])
        self._ctx.audit().updated(entity_type="PriceList", entity_id=str(price_list_id), before={}, after={"status": "archived"})
        self._ctx.invalidate_pricing_cache()
        return saved


class SetPrice:
    """Backs Base/Cost/Sale/Compare-at Price -- one service, since PriceList.set_price() already handles all four slots atomically per this phase's 'no duplicated pricing calculation' discipline."""

    def __init__(self, repo: PriceListRepository, ctx: PricingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, price_list_id: uuid.UUID, product_variant_id: uuid.UUID, base_amount, currency: str, cost_amount=None, sale_amount=None, compare_at_amount=None, reason: str = PriceChangeReason.MANUAL.value) -> PriceList:
        price_list = self._repo.get_by_id(price_list_id)
        if price_list is None:
            raise ResourceNotFound("Price list not found.")

        event = price_list.set_price(
            product_variant_id=product_variant_id, base_price=Money(amount=base_amount, currency=currency),
            reason=PriceChangeReason(reason),
            cost_price=Money(amount=cost_amount, currency=currency) if cost_amount is not None else None,
            sale_price=Money(amount=sale_amount, currency=currency) if sale_amount is not None else None,
            compare_at_price=Money(amount=compare_at_amount, currency=currency) if compare_at_amount is not None else None,
            at=django_timezone.now(),
        )
        saved = self._repo.save(price_list)

        self._ctx.stage_events([("PriceSet", event.to_payload())])
        self._ctx.audit().updated(entity_type="PriceList", entity_id=str(price_list_id), before={}, after={"product_variant_id": str(product_variant_id), "base_amount": str(base_amount)})
        self._ctx.invalidate_pricing_cache()
        self._ctx.metric("prices_set_total")
        return saved
