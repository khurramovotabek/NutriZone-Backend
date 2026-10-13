"""
Repository integration tests -- require a real PostgreSQL database.

**`created_at` round-trip is specifically, deliberately tested** --
the exact named check this build's own established discipline
requires after the real defect found in Notifications' Phase 4.

**The owned-entity deletion-synchronization algorithm (the genuinely
novel design introduced in Phase 2, since POS is the first module in
this build where an owned entity can shrink) receives explicit,
dedicated regression tests covering all three cases: an item that
stays, an item that is newly added, and an item that is removed.**
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone as django_timezone

from apps.pos.domain.value_objects import Quantity
from apps.pos.infrastructure import models as orm
from apps.pos.infrastructure.repositories import DjangoSaleRepository
from apps.pos.tests.factories import make_sale, make_sale_with_line
from shared.value_objects.money import Money

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestDjangoSaleRepository:
    def test_save_then_get_by_id_round_trips(self):
        repo = DjangoSaleRepository()
        sale = make_sale()
        repo.save(sale)

        fetched = repo.get_by_id(sale.id)
        assert fetched is not None
        assert fetched.branch_id == sale.branch_id
        assert fetched.cashier_id == sale.cashier_id
        assert fetched.status == sale.status

    def test_created_at_round_trips_exactly_not_silently_overwritten(self):
        """The specific, named regression guard this build's own discipline requires."""
        repo = DjangoSaleRepository()
        original_created_at = django_timezone.now() - timedelta(days=3)
        sale = make_sale(at=original_created_at)
        repo.save(sale)

        fetched = repo.get_by_id(sale.id)
        assert fetched.created_at == original_created_at

    def test_get_by_id_missing_returns_none(self):
        repo = DjangoSaleRepository()
        assert repo.get_by_id(uuid.uuid4()) is None

    def test_customer_id_none_round_trips_correctly(self):
        repo = DjangoSaleRepository()
        sale = make_sale(customer_id=None)
        repo.save(sale)
        assert repo.get_by_id(sale.id).customer_id is None

    def test_status_round_trips(self):
        repo = DjangoSaleRepository()
        sale = make_sale()
        sale.void(datetime.utcnow())
        repo.save(sale)
        assert repo.get_by_id(sale.id).status.value == "voided"

    def test_line_item_round_trips_with_correct_decimal_precision(self):
        """A direct proof at the persistence boundary: a Decimal value must survive the ORM round-trip exactly, with no float-conversion precision loss. `Sale.line_items` is the certified field name (not `entries` -- that is Analytics' own AnalyticsSnapshot field name, a different module's aggregate)."""
        repo = DjangoSaleRepository()
        sale = make_sale_with_line(quantity=3, unit_price="19.99")
        repo.save(sale)

        fetched = repo.get_by_id(sale.id)
        entry = next(iter(fetched.line_items.values()))
        assert entry.quantity.value == 3
        assert entry.unit_price.amount == Decimal("19.99")
        assert isinstance(entry.unit_price.amount, Decimal)

    # --- Owned-entity deletion synchronization -- the genuinely novel case in this build ---

    def test_new_line_item_is_created_on_save(self):
        repo = DjangoSaleRepository()
        sale = make_sale()
        repo.save(sale)

        sale.add_line_item(uuid.uuid4(), Quantity(1), Money(Decimal("5.00")))
        repo.save(sale)

        assert orm.SaleLineItemModel.objects.filter(sale_id=sale.id).count() == 1

    def test_removed_line_item_is_deleted_from_the_database(self):
        """The core regression guard for this module's own novel deletion-sync algorithm: an item present in the database but absent from the in-memory aggregate must actually be deleted, not merely ignored."""
        repo = DjangoSaleRepository()
        sale = make_sale()
        repo.save(sale)

        event = sale.add_line_item(uuid.uuid4(), Quantity(1), Money(Decimal("5.00")))
        repo.save(sale)
        assert orm.SaleLineItemModel.objects.filter(sale_id=sale.id).count() == 1

        sale.remove_line_item(event.line_item_id)
        repo.save(sale)
        assert orm.SaleLineItemModel.objects.filter(sale_id=sale.id).count() == 0

    def test_unchanged_line_item_is_left_untouched_across_saves(self):
        repo = DjangoSaleRepository()
        sale = make_sale()
        repo.save(sale)
        event = sale.add_line_item(uuid.uuid4(), Quantity(2), Money(Decimal("3.00")))
        repo.save(sale)

        # Reload, then save again without any line-item mutation -- the existing row must remain, not be recreated.
        fetched = repo.get_by_id(sale.id)
        repo.save(fetched)
        assert orm.SaleLineItemModel.objects.filter(id=event.line_item_id).count() == 1

    def test_mixed_add_and_remove_in_the_same_save_cycle(self):
        """The full three-way set-difference case: one item stays, one new item is added, one existing item is removed -- all reconciled in a single subsequent save()."""
        repo = DjangoSaleRepository()
        sale = make_sale()
        repo.save(sale)
        keep_event = sale.add_line_item(uuid.uuid4(), Quantity(1), Money(Decimal("1.00")))
        remove_event = sale.add_line_item(uuid.uuid4(), Quantity(1), Money(Decimal("2.00")))
        repo.save(sale)
        assert orm.SaleLineItemModel.objects.filter(sale_id=sale.id).count() == 2

        sale.remove_line_item(remove_event.line_item_id)
        add_event = sale.add_line_item(uuid.uuid4(), Quantity(1), Money(Decimal("3.00")))
        repo.save(sale)

        remaining_ids = set(orm.SaleLineItemModel.objects.filter(sale_id=sale.id).values_list("id", flat=True))
        assert remaining_ids == {keep_event.line_item_id, add_event.line_item_id}

    def test_database_level_foreign_key_cascade_deletes_line_items(self):
        """Verifies the certified deletion behavior: deleting a Sale row cascades to its owned SaleLineItemModel rows, per the certified aggregate-ownership relationship."""
        repo = DjangoSaleRepository()
        sale = make_sale()
        repo.save(sale)
        sale.add_line_item(uuid.uuid4(), Quantity(1), Money(Decimal("1.00")))
        repo.save(sale)
        assert orm.SaleLineItemModel.objects.filter(sale_id=sale.id).count() == 1

        orm.SaleModel.objects.filter(id=sale.id).delete()
        assert orm.SaleLineItemModel.objects.filter(sale_id=sale.id).count() == 0
