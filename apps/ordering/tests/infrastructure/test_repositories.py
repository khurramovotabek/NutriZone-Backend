"""
Repository integration tests -- require a real PostgreSQL database.
Matches every prior module's `tests/infrastructure/test_repositories.py`
pattern. Includes explicit database-constraint verification tests
(IntegrityError mapping), collection reconciliation, and delete-orphan
behavior, not just repository round-trip tests.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from datetime import datetime

import pytest
from django.db import IntegrityError

from apps.ordering.domain.value_objects import Money
from apps.ordering.infrastructure.repositories import (
    DjangoOrderCancellationRepository, DjangoOrderRepository, DjangoOrderReturnRepository,
)
from apps.ordering.tests.factories import make_cancellation, make_order_with_line, make_return

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestDjangoOrderRepository:
    def test_save_then_get_by_id_round_trips(self):
        repo = DjangoOrderRepository()
        order = make_order_with_line()
        repo.save(order)

        fetched = repo.get_by_id(order.id)
        assert fetched is not None
        assert fetched.order_number.value == order.order_number.value

    def test_get_by_order_number(self):
        repo = DjangoOrderRepository()
        order = make_order_with_line()
        repo.save(order)
        assert repo.get_by_order_number(order.order_number.value).id == order.id

    def test_get_by_cart_id(self):
        repo = DjangoOrderRepository()
        order = make_order_with_line()
        repo.save(order)
        assert repo.get_by_cart_id(order.cart_id).id == order.id

    def test_line_items_and_addresses_round_trip(self):
        repo = DjangoOrderRepository()
        order = make_order_with_line()
        repo.save(order)

        fetched = repo.get_by_id(order.id)
        assert len(fetched.lines) == 1
        assert fetched.shipping_address.city == order.shipping_address.city

    def test_stale_line_item_removed_from_database_on_save(self):
        """Verifies save() actually deletes rows for lines no longer present in the aggregate -- collection reconciliation, not just upserts."""
        repo = DjangoOrderRepository()
        order = make_order_with_line()
        repo.save(order)
        line_id = next(iter(order.lines))

        del order.lines[line_id]
        repo.save(order)

        from apps.ordering.infrastructure import models as orm

        assert not orm.OrderLineItemModel.objects.filter(id=line_id).exists()

    def test_payment_and_fulfillment_references_round_trip(self):
        repo = DjangoOrderRepository()
        order = make_order_with_line()
        order.attach_payment_reference(uuid.uuid4(), Money(amount=Decimal("100.00"), currency="UZS"))
        order.attach_fulfillment_reference(uuid.uuid4())
        repo.save(order)

        fetched = repo.get_by_id(order.id)
        assert len(fetched.payment_references) == 1
        assert len(fetched.fulfillment_references) == 1

    def test_invoice_round_trips(self):
        repo = DjangoOrderRepository()
        order = make_order_with_line()
        order.issue_invoice("INV-2026-00000001", Money(amount=Decimal("100.00"), currency="UZS"), datetime.utcnow())
        repo.save(order)

        fetched = repo.get_by_id(order.id)
        assert fetched.invoice is not None
        assert fetched.invoice.invoice_number == "INV-2026-00000001"

    def test_status_history_round_trips(self):
        repo = DjangoOrderRepository()
        order = make_order_with_line()
        order.confirm(datetime.utcnow())
        repo.save(order)

        fetched = repo.get_by_id(order.id)
        assert len(fetched.status_history) == 1  # confirm only -- no synthetic "created" entry, since make_order_with_line() constructs the Order via the raw dataclass constructor, not the real create_from_cart_data() flow that would add one

    def test_database_level_quantity_constraint(self):
        """Verifies the CheckConstraint actually rejects a non-positive quantity at the database layer."""
        from apps.ordering.infrastructure import models as orm

        order_row = orm.OrderModel.objects.create(order_number="ORD-CONSTRAINTTST", currency="UZS", shipping_recipient_name="X", shipping_line1="X", shipping_city="X", shipping_country_code="UZ", billing_recipient_name="X", billing_line1="X", billing_city="X", billing_country_code="UZ")
        with pytest.raises(IntegrityError):
            orm.OrderLineItemModel.objects.create(order=order_row, product_variant_id=uuid.uuid4(), quantity=0, unit_price_amount=Decimal("10.00"))

    def test_database_level_unique_order_number_constraint(self):
        from apps.ordering.infrastructure import models as orm

        kwargs = dict(currency="UZS", shipping_recipient_name="X", shipping_line1="X", shipping_city="X", shipping_country_code="UZ", billing_recipient_name="X", billing_line1="X", billing_city="X", billing_country_code="UZ")
        orm.OrderModel.objects.create(order_number="ORD-UNIQUETEST01", **kwargs)
        with pytest.raises(IntegrityError):
            orm.OrderModel.objects.create(order_number="ORD-UNIQUETEST01", **kwargs)

    def test_list_for_customer(self):
        repo = DjangoOrderRepository()
        customer_id = uuid.uuid4()
        repo.save(make_order_with_line(customer_id=customer_id))
        results, total = repo.list_for_customer(customer_id, status=None, page=1, page_size=20)
        assert total == 1


class TestDjangoOrderReturnRepository:
    def test_save_then_get_by_id_round_trips(self):
        repo = DjangoOrderReturnRepository()
        order_return = make_return()
        repo.save(order_return)
        fetched = repo.get_by_id(order_return.id)
        assert fetched.return_number.value == order_return.return_number.value

    def test_lines_round_trip(self):
        repo = DjangoOrderReturnRepository()
        order_return = make_return()
        order_return.add_line(uuid.uuid4(), 2)
        repo.save(order_return)
        fetched = repo.get_by_id(order_return.id)
        assert len(fetched.lines) == 1

    def test_database_level_unique_return_number_constraint(self):
        from apps.ordering.infrastructure import models as orm

        orm.OrderReturnModel.objects.create(return_number="RET-UNIQUETEST1", order_id=uuid.uuid4())
        with pytest.raises(IntegrityError):
            orm.OrderReturnModel.objects.create(return_number="RET-UNIQUETEST1", order_id=uuid.uuid4())

    def test_list_for_order(self):
        repo = DjangoOrderReturnRepository()
        order_id = uuid.uuid4()
        repo.save(make_return(order_id=order_id))
        assert len(repo.list_for_order(order_id)) == 1


class TestDjangoOrderCancellationRepository:
    def test_save_then_get_by_id_round_trips(self):
        repo = DjangoOrderCancellationRepository()
        cancellation = make_cancellation()
        repo.save(cancellation)
        fetched = repo.get_by_id(cancellation.id)
        assert fetched.order_id == cancellation.order_id

    def test_lines_round_trip(self):
        repo = DjangoOrderCancellationRepository()
        cancellation = make_cancellation()
        cancellation.add_line(uuid.uuid4(), 1)
        repo.save(cancellation)
        fetched = repo.get_by_id(cancellation.id)
        assert len(fetched.lines) == 1

    def test_list_for_order(self):
        repo = DjangoOrderCancellationRepository()
        order_id = uuid.uuid4()
        repo.save(make_cancellation(order_id=order_id))
        assert len(repo.list_for_order(order_id)) == 1
