from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import pytest

from apps.pos.application.services._shared import PosServiceContext
from apps.pos.application.services.sale import AddLineItem, CompleteSale, LoadSale, OpenSale, RemoveLineItem, VoidSale
from apps.pos.domain.exceptions import EmptySale, InvalidQuantity, InvalidSaleTransition, SaleLineItemNotFound
from apps.pos.tests.application.fakes import FakeSaleRepository, collect_events
from apps.pos.tests.factories import make_sale, make_sale_with_line
from common.exceptions import ResourceNotFound

pytestmark = pytest.mark.django_db


def _ctx():
    events: list = []
    return PosServiceContext(stage_events=collect_events(events), actor_id=uuid.uuid4()), events


class TestOpenSale:
    def test_opens_a_new_sale(self):
        repo = FakeSaleRepository()
        ctx, events = _ctx()
        branch_id, cashier_id = uuid.uuid4(), uuid.uuid4()
        sale = OpenSale(repo, ctx).execute(branch_id=branch_id, cashier_id=cashier_id)
        assert sale.branch_id == branch_id
        assert sale.cashier_id == cashier_id
        assert sale.status.value == "open"
        assert repo.get_by_id(sale.id) is sale
        assert any(e[0] == "SaleOpened" for e in events)

    def test_customer_id_passed_through(self):
        repo = FakeSaleRepository()
        ctx, _ = _ctx()
        customer_id = uuid.uuid4()
        sale = OpenSale(repo, ctx).execute(branch_id=uuid.uuid4(), cashier_id=uuid.uuid4(), customer_id=customer_id)
        assert sale.customer_id == customer_id


class TestLoadSale:
    def test_returns_existing_sale(self):
        repo = FakeSaleRepository()
        sale = make_sale()
        repo.save(sale)
        assert LoadSale(repo).execute(sale.id) is sale

    def test_missing_raises_resource_not_found(self):
        repo = FakeSaleRepository()
        with pytest.raises(ResourceNotFound):
            LoadSale(repo).execute(uuid.uuid4())


class TestAddLineItem:
    def test_adds_a_line_item_to_an_existing_sale(self):
        repo = FakeSaleRepository()
        sale = make_sale()
        repo.save(sale)
        ctx, events = _ctx()
        product_id = uuid.uuid4()

        updated = AddLineItem(repo, ctx).execute(sale_id=sale.id, product_id=product_id, quantity=3, unit_price_amount=Decimal("9.99"), unit_price_currency="UZS")

        assert len(updated.line_items) == 1
        entry = next(iter(updated.line_items.values()))
        assert entry.product_id == product_id
        assert entry.quantity.value == 3
        assert entry.unit_price.amount == Decimal("9.99")
        assert any(e[0] == "SaleLineItemAdded" for e in events)

    def test_missing_sale_raises_resource_not_found(self):
        repo = FakeSaleRepository()
        ctx, events = _ctx()
        with pytest.raises(ResourceNotFound):
            AddLineItem(repo, ctx).execute(sale_id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=1, unit_price_amount=Decimal("1.00"), unit_price_currency="UZS")
        assert events == []

    def test_invalid_quantity_propagates_domain_exception_untouched(self):
        repo = FakeSaleRepository()
        sale = make_sale()
        repo.save(sale)
        ctx, events = _ctx()
        with pytest.raises(InvalidQuantity):
            AddLineItem(repo, ctx).execute(sale_id=sale.id, product_id=uuid.uuid4(), quantity=0, unit_price_amount=Decimal("1.00"), unit_price_currency="UZS")
        assert events == []

    def test_invalid_state_raises_invalid_sale_transition(self):
        repo = FakeSaleRepository()
        sale = make_sale_with_line()
        sale.complete(datetime.utcnow())
        repo.save(sale)
        ctx, _ = _ctx()
        with pytest.raises(InvalidSaleTransition):
            AddLineItem(repo, ctx).execute(sale_id=sale.id, product_id=uuid.uuid4(), quantity=1, unit_price_amount=Decimal("1.00"), unit_price_currency="UZS")


class TestRemoveLineItem:
    def test_removes_an_existing_line_item(self):
        repo = FakeSaleRepository()
        sale = make_sale()
        repo.save(sale)
        ctx, _ = _ctx()
        added = AddLineItem(repo, ctx).execute(sale_id=sale.id, product_id=uuid.uuid4(), quantity=1, unit_price_amount=Decimal("5.00"), unit_price_currency="UZS")
        line_item_id = next(iter(added.line_items.keys()))

        ctx2, events = _ctx()
        updated = RemoveLineItem(repo, ctx2).execute(sale_id=sale.id, line_item_id=line_item_id)
        assert updated.line_items == {}
        assert any(e[0] == "SaleLineItemRemoved" for e in events)

    def test_missing_sale_raises_resource_not_found(self):
        repo = FakeSaleRepository()
        ctx, events = _ctx()
        with pytest.raises(ResourceNotFound):
            RemoveLineItem(repo, ctx).execute(sale_id=uuid.uuid4(), line_item_id=uuid.uuid4())
        assert events == []

    def test_unknown_line_item_propagates_domain_exception(self):
        repo = FakeSaleRepository()
        sale = make_sale()
        repo.save(sale)
        ctx, _ = _ctx()
        with pytest.raises(SaleLineItemNotFound):
            RemoveLineItem(repo, ctx).execute(sale_id=sale.id, line_item_id=uuid.uuid4())


class TestCompleteSale:
    def test_completes_a_sale_with_line_items(self):
        repo = FakeSaleRepository()
        sale = make_sale_with_line()
        repo.save(sale)
        ctx, events = _ctx()
        updated = CompleteSale(repo, ctx).execute(sale.id)
        assert updated.status.value == "completed"
        assert any(e[0] == "SaleCompleted" for e in events)

    def test_missing_sale_raises_resource_not_found(self):
        repo = FakeSaleRepository()
        ctx, _ = _ctx()
        with pytest.raises(ResourceNotFound):
            CompleteSale(repo, ctx).execute(uuid.uuid4())

    def test_empty_sale_raises_empty_sale(self):
        repo = FakeSaleRepository()
        sale = make_sale()
        repo.save(sale)
        ctx, events = _ctx()
        with pytest.raises(EmptySale):
            CompleteSale(repo, ctx).execute(sale.id)
        assert events == []

    def test_double_complete_raises_invalid_transition(self):
        repo = FakeSaleRepository()
        sale = make_sale_with_line()
        sale.complete(datetime.utcnow())
        repo.save(sale)
        ctx, _ = _ctx()
        with pytest.raises(InvalidSaleTransition):
            CompleteSale(repo, ctx).execute(sale.id)


class TestVoidSale:
    def test_voids_an_open_sale(self):
        repo = FakeSaleRepository()
        sale = make_sale()
        repo.save(sale)
        ctx, events = _ctx()
        updated = VoidSale(repo, ctx).execute(sale.id)
        assert updated.status.value == "voided"
        assert any(e[0] == "SaleVoided" for e in events)

    def test_missing_sale_raises_resource_not_found(self):
        repo = FakeSaleRepository()
        ctx, _ = _ctx()
        with pytest.raises(ResourceNotFound):
            VoidSale(repo, ctx).execute(uuid.uuid4())

    def test_void_completed_sale_raises_invalid_transition(self):
        repo = FakeSaleRepository()
        sale = make_sale_with_line()
        sale.complete(datetime.utcnow())
        repo.save(sale)
        ctx, _ = _ctx()
        with pytest.raises(InvalidSaleTransition):
            VoidSale(repo, ctx).execute(sale.id)
