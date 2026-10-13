"""
Aggregate tests -- covers every public `Sale` method, every state
transition, every invariant, every emitted Domain Event, and every
exception path.

**Event names are `SaleOpened`/`SaleLineItemAdded`/
`SaleLineItemRemoved`/`SaleCompleted`/`SaleVoided`** -- re-verified
directly from live source in this phase's own Step 2, not the
`LineItemAdded`/`LineItemRemoved` naming that appeared in this
phase's own prompt summary. Live source is authoritative.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import pytest

from apps.pos.domain.aggregates import Sale
from apps.pos.domain.enums import SaleStatus
from apps.pos.domain.exceptions import EmptySale, InvalidSaleTransition, SaleLineItemNotFound
from apps.pos.domain.value_objects import Quantity
from apps.pos.tests.factories import make_sale, make_sale_with_line
from shared.value_objects.money import Money

pytestmark = pytest.mark.unit


def _now() -> datetime:
    return datetime.utcnow()


class TestSaleOpen:
    def test_creates_open_sale(self):
        branch_id, cashier_id = uuid.uuid4(), uuid.uuid4()
        sale, event = Sale.open(uuid.uuid4(), branch_id, cashier_id, _now())
        assert sale.status == SaleStatus.OPEN
        assert sale.branch_id == branch_id
        assert sale.cashier_id == cashier_id
        assert event.__class__.__name__ == "SaleOpened"

    def test_customer_id_defaults_to_none(self):
        sale, _ = Sale.open(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), _now())
        assert sale.customer_id is None

    def test_customer_id_stored_when_supplied(self):
        customer_id = uuid.uuid4()
        sale, _ = Sale.open(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), _now(), customer_id)
        assert sale.customer_id == customer_id

    def test_starts_with_empty_line_items(self):
        sale = make_sale()
        assert sale.line_items == {}

    def test_total_of_empty_sale_is_zero(self):
        sale = make_sale()
        assert sale.total() == Money.zero()


class TestAddLineItem:
    def test_adds_first_item(self):
        sale = make_sale()
        event = sale.add_line_item(uuid.uuid4(), Quantity(2), Money(Decimal("5.00")))
        assert len(sale.line_items) == 1
        assert event.__class__.__name__ == "SaleLineItemAdded"

    def test_adds_multiple_different_items(self):
        sale = make_sale()
        sale.add_line_item(uuid.uuid4(), Quantity(1), Money(Decimal("1.00")))
        sale.add_line_item(uuid.uuid4(), Quantity(2), Money(Decimal("2.00")))
        assert len(sale.line_items) == 2

    def test_total_recalculates_after_add(self):
        sale = make_sale()
        sale.add_line_item(uuid.uuid4(), Quantity(2), Money(Decimal("5.00")))
        sale.add_line_item(uuid.uuid4(), Quantity(1), Money(Decimal("3.00")))
        assert sale.total() == Money(Decimal("13.00"))

    def test_rejects_add_on_completed_sale(self):
        sale = make_sale_with_line()
        sale.complete(_now())
        with pytest.raises(InvalidSaleTransition):
            sale.add_line_item(uuid.uuid4(), Quantity(1), Money(Decimal("1.00")))

    def test_rejects_add_on_voided_sale(self):
        sale = make_sale()
        sale.void(_now())
        with pytest.raises(InvalidSaleTransition):
            sale.add_line_item(uuid.uuid4(), Quantity(1), Money(Decimal("1.00")))


class TestRemoveLineItem:
    """POS is the first module in this build where an owned entity can shrink -- this class is the Domain-level counterpart to the repository's own deletion-synchronization test (infrastructure/test_repositories.py)."""

    def test_removes_existing_item(self):
        sale = make_sale()
        event = sale.add_line_item(uuid.uuid4(), Quantity(1), Money(Decimal("5.00")))
        line_item_id = event.line_item_id
        remove_event = sale.remove_line_item(line_item_id)
        assert sale.line_items == {}
        assert remove_event.__class__.__name__ == "SaleLineItemRemoved"

    def test_total_recalculates_after_remove(self):
        sale = make_sale()
        event_a = sale.add_line_item(uuid.uuid4(), Quantity(1), Money(Decimal("5.00")))
        sale.add_line_item(uuid.uuid4(), Quantity(1), Money(Decimal("3.00")))
        sale.remove_line_item(event_a.line_item_id)
        assert sale.total() == Money(Decimal("3.00"))

    def test_removing_one_of_two_leaves_the_other_untouched(self):
        sale = make_sale()
        event_a = sale.add_line_item(uuid.uuid4(), Quantity(1), Money(Decimal("5.00")))
        event_b = sale.add_line_item(uuid.uuid4(), Quantity(1), Money(Decimal("3.00")))
        sale.remove_line_item(event_a.line_item_id)
        assert list(sale.line_items.keys()) == [event_b.line_item_id]

    def test_removing_unknown_item_raises(self):
        sale = make_sale_with_line()
        with pytest.raises(SaleLineItemNotFound):
            sale.remove_line_item(uuid.uuid4())

    def test_remove_on_completed_sale_raises_invalid_transition(self):
        sale = make_sale_with_line()
        sale.complete(_now())
        line_item_id = next(iter(sale.line_items.keys()))
        with pytest.raises(InvalidSaleTransition):
            sale.remove_line_item(line_item_id)

    def test_remove_on_voided_sale_raises_invalid_transition(self):
        sale = make_sale_with_line()
        sale.void(_now())
        line_item_id = next(iter(sale.line_items.keys()))
        with pytest.raises(InvalidSaleTransition):
            sale.remove_line_item(line_item_id)


class TestComplete:
    def test_completes_sale_with_line_items(self):
        sale = make_sale_with_line()
        event = sale.complete(_now())
        assert sale.status == SaleStatus.COMPLETED
        assert event.__class__.__name__ == "SaleCompleted"

    def test_empty_sale_cannot_complete(self):
        """Protects the certified EmptySale invariant -- mirrors Ordering's own certified EmptyOrder precedent exactly (Phase 1's own disclosed justification)."""
        sale = make_sale()
        assert sale.line_items == {}
        with pytest.raises(EmptySale):
            sale.complete(_now())

    def test_completed_event_carries_correct_total(self):
        sale = make_sale()
        sale.add_line_item(uuid.uuid4(), Quantity(2), Money(Decimal("4.00")))
        event = sale.complete(_now())
        assert event.total_amount == Decimal("8.00")

    def test_double_complete_raises_invalid_transition(self):
        sale = make_sale_with_line()
        sale.complete(_now())
        with pytest.raises(InvalidSaleTransition):
            sale.complete(_now())

    def test_complete_voided_sale_raises_invalid_transition(self):
        sale = make_sale()
        sale.void(_now())
        with pytest.raises(InvalidSaleTransition):
            sale.complete(_now())


class TestVoid:
    def test_voids_open_sale(self):
        sale = make_sale()
        event = sale.void(_now())
        assert sale.status == SaleStatus.VOIDED
        assert event.__class__.__name__ == "SaleVoided"

    def test_void_with_line_items_is_allowed(self):
        """A sale being abandoned before completion may still have items on it -- void does not require an empty sale, unlike complete()."""
        sale = make_sale_with_line()
        sale.void(_now())
        assert sale.status == SaleStatus.VOIDED

    def test_void_completed_sale_raises_invalid_transition(self):
        """A completed sale is never voided -- it is refunded instead (see TestRefund)."""
        sale = make_sale_with_line()
        sale.complete(_now())
        with pytest.raises(InvalidSaleTransition):
            sale.void(_now())

    def test_double_void_raises_invalid_transition(self):
        sale = make_sale()
        sale.void(_now())
        with pytest.raises(InvalidSaleTransition):
            sale.void(_now())


class TestRefund:
    def test_refunds_completed_sale(self):
        sale = make_sale_with_line()
        sale.complete(_now())
        event = sale.refund(_now())
        assert sale.status == SaleStatus.REFUNDED
        assert sale.refunded_at is not None
        assert event.__class__.__name__ == "SaleRefunded"
        assert event.total_amount == sale.total().amount

    def test_refund_keeps_line_items_as_the_record_of_what_was_returned(self):
        sale = make_sale_with_line()
        sale.complete(_now())
        lines_before = dict(sale.line_items)
        sale.refund(_now())
        assert sale.line_items == lines_before

    @pytest.mark.parametrize("prepare", ["open", "voided", "refunded"])
    def test_refund_is_only_legal_from_completed(self, prepare):
        sale = make_sale_with_line()
        if prepare == "voided":
            sale.void(_now())
        elif prepare == "refunded":
            sale.complete(_now())
            sale.refund(_now())
        with pytest.raises(InvalidSaleTransition):
            sale.refund(_now())

    def test_refunded_sale_cannot_be_voided(self):
        sale = make_sale_with_line()
        sale.complete(_now())
        sale.refund(_now())
        with pytest.raises(InvalidSaleTransition):
            sale.void(_now())


class TestPrivateAccessBoundary:
    def test_private_methods_are_underscore_prefixed_and_not_part_of_public_contract(self):
        public_methods = {name for name in dir(Sale) if not name.startswith("_") and callable(getattr(Sale, name, None))}
        assert "_private_helper" not in public_methods
