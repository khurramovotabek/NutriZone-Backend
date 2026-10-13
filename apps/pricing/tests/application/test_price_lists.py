from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.pricing.application.services._shared import PricingServiceContext
from apps.pricing.application.services.price_lists import ActivatePriceList, ArchivePriceList, CreatePriceList, SetPrice
from apps.pricing.domain.aggregates import PriceList
from apps.pricing.domain.value_objects import PriceListCode
from apps.pricing.tests.application.fakes import FakePriceListRepository, collect_events
from common.exceptions import ConflictError, ResourceNotFound

pytestmark = pytest.mark.django_db  # every service uses @transaction.atomic -- same documented rationale as every prior module


def _ctx():
    events: list = []
    return PricingServiceContext(stage_events=collect_events(events), actor_id=uuid.uuid4()), events


class TestCreatePriceList:
    def test_creates_price_list(self):
        repo = FakePriceListRepository()
        ctx, events = _ctx()
        price_list = CreatePriceList(repo, ctx).execute(code="DEFAULT-UZS", name="Default", currency="UZS")
        assert price_list.status.value == "draft"
        assert any(e[0] == "PriceListCreated" for e in events)

    def test_duplicate_code_raises(self):
        repo = FakePriceListRepository()
        ctx, _ = _ctx()
        CreatePriceList(repo, ctx).execute(code="DEFAULT-UZS", name="Default", currency="UZS")
        with pytest.raises(ConflictError):
            CreatePriceList(repo, ctx).execute(code="DEFAULT-UZS", name="Another", currency="UZS")

    def test_with_region(self):
        repo = FakePriceListRepository()
        ctx, _ = _ctx()
        price_list = CreatePriceList(repo, ctx).execute(code="TASH-UZS", name="Tashkent", currency="UZS", region="UZ-TASH")
        assert price_list.region.value == "UZ-TASH"


class TestActivateArchivePriceList:
    def test_activate_missing_raises(self):
        ctx, _ = _ctx()
        with pytest.raises(ResourceNotFound):
            ActivatePriceList(FakePriceListRepository(), ctx).execute(uuid.uuid4())

    def test_activate_then_archive(self):
        repo = FakePriceListRepository()
        price_list = PriceList(id=uuid.uuid4(), code=PriceListCode("DEFAULT-UZS"), name="Default", currency="UZS")
        repo.save(price_list)
        ctx, events = _ctx()

        activated = ActivatePriceList(repo, ctx).execute(price_list.id)
        assert activated.status.value == "active"

        archived = ArchivePriceList(repo, ctx).execute(price_list.id)
        assert archived.status.value == "archived"
        event_types = [e[0] for e in events]
        assert "PriceListActivated" in event_types
        assert "PriceListArchivedEvent" in event_types


class TestSetPrice:
    def test_sets_base_price(self):
        repo = FakePriceListRepository()
        price_list = PriceList(id=uuid.uuid4(), code=PriceListCode("DEFAULT-UZS"), name="Default", currency="UZS")
        repo.save(price_list)
        ctx, events = _ctx()

        variant_id = uuid.uuid4()
        updated = SetPrice(repo, ctx).execute(price_list_id=price_list.id, product_variant_id=variant_id, base_amount=Decimal("100.00"), currency="UZS")
        entry = updated.entry_for_variant(variant_id)
        assert entry.base_price.amount == Decimal("100.00")
        assert any(e[0] == "PriceSet" for e in events)

    def test_sets_all_four_price_slots(self):
        repo = FakePriceListRepository()
        price_list = PriceList(id=uuid.uuid4(), code=PriceListCode("DEFAULT-UZS"), name="Default", currency="UZS")
        repo.save(price_list)
        ctx, _ = _ctx()

        variant_id = uuid.uuid4()
        updated = SetPrice(repo, ctx).execute(
            price_list_id=price_list.id, product_variant_id=variant_id, base_amount=Decimal("100.00"), currency="UZS",
            cost_amount=Decimal("60.00"), sale_amount=Decimal("80.00"), compare_at_amount=Decimal("120.00"),
        )
        entry = updated.entry_for_variant(variant_id)
        assert entry.cost_price.amount == Decimal("60.00")
        assert entry.sale_price.amount == Decimal("80.00")
        assert entry.compare_at_price.amount == Decimal("120.00")

    def test_set_price_on_missing_list_raises(self):
        ctx, _ = _ctx()
        with pytest.raises(ResourceNotFound):
            SetPrice(FakePriceListRepository(), ctx).execute(price_list_id=uuid.uuid4(), product_variant_id=uuid.uuid4(), base_amount=Decimal("10.00"), currency="UZS")
