"""
Repository integration tests -- require a real PostgreSQL database.
Matches every prior module's `tests/infrastructure/test_repositories.py`
pattern. Includes explicit database-constraint verification tests, not
just repository round-trip tests.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import pytest
from django.db import IntegrityError

from apps.cart.domain.value_objects import Money
from apps.cart.infrastructure.repositories import DjangoCartRepository
from apps.cart.tests.factories import make_cart

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestDjangoCartRepository:
    def test_save_then_get_by_id_round_trips(self):
        repo = DjangoCartRepository()
        cart = make_cart()
        repo.save(cart)

        fetched = repo.get_by_id(cart.id)
        assert fetched is not None
        assert fetched.code.value == cart.code.value

    def test_get_by_code(self):
        """Added during Phase 3 -- see certification report for why this method exists."""
        repo = DjangoCartRepository()
        cart = make_cart()
        repo.save(cart)
        assert repo.get_by_code(cart.code.value).id == cart.id

    def test_get_by_token(self):
        repo = DjangoCartRepository()
        cart = make_cart()
        repo.save(cart)
        assert repo.get_by_token(str(cart.token)).id == cart.id

    def test_items_and_price_reservation_references_round_trip(self):
        repo = DjangoCartRepository()
        cart = make_cart()
        added = cart.add_item(uuid.uuid4(), 3, datetime.utcnow())
        cart.attach_price_snapshot(added.item_id, uuid.uuid4(), Money(amount=Decimal("25.00"), currency="UZS"), datetime.utcnow())
        cart.attach_reservation(added.item_id, uuid.uuid4(), datetime.utcnow())
        repo.save(cart)

        fetched = repo.get_by_id(cart.id)
        item = fetched.items[added.item_id]
        assert item.price_reference.unit_amount.amount == Decimal("25.00")
        assert item.reservation_reference is not None

    def test_snapshots_and_audit_log_round_trip(self):
        repo = DjangoCartRepository()
        cart = make_cart()
        cart.add_item(uuid.uuid4(), 1, datetime.utcnow())
        cart.create_snapshot(datetime.utcnow())
        repo.save(cart)

        fetched = repo.get_by_id(cart.id)
        assert len(fetched.snapshots) == 1
        assert len(fetched.audit_log) >= 1

    def test_stale_item_removed_from_database_on_save(self):
        """Verifies save() actually deletes rows for items no longer present in the aggregate, not just upserts."""
        repo = DjangoCartRepository()
        cart = make_cart()
        added = cart.add_item(uuid.uuid4(), 1, datetime.utcnow())
        repo.save(cart)

        del cart.items[added.item_id]
        repo.save(cart)

        from apps.cart.infrastructure import models as orm

        assert not orm.CartItemModel.objects.filter(id=added.item_id).exists()

    def test_database_level_quantity_constraint(self):
        """Verifies the CheckConstraint actually rejects a negative quantity at the database layer, bypassing the domain aggregate's own Quantity value object entirely."""
        from apps.cart.infrastructure import models as orm

        cart_row = orm.CartModel.objects.create(code="CONSTRAINTTEST", currency="UZS")
        with pytest.raises(IntegrityError):
            orm.CartItemModel.objects.create(cart=cart_row, product_variant_id=uuid.uuid4(), quantity=-1)

    def test_database_level_unique_code_constraint(self):
        from apps.cart.infrastructure import models as orm

        orm.CartModel.objects.create(code="UNIQUECARTCODE", currency="UZS")
        with pytest.raises(IntegrityError):
            orm.CartModel.objects.create(code="UNIQUECARTCODE", currency="UZS")

    def test_database_level_unique_token_constraint(self):
        from apps.cart.infrastructure import models as orm

        token = uuid.uuid4()
        orm.CartModel.objects.create(code="TOKENTEST0001", currency="UZS", token=token)
        with pytest.raises(IntegrityError):
            orm.CartModel.objects.create(code="TOKENTEST0002", currency="UZS", token=token)

    def test_database_level_one_price_reference_per_item_constraint(self):
        """Verifies the OneToOneField actually prevents a second PriceSnapshotReference for the same item at the database level."""
        from apps.cart.infrastructure import models as orm

        cart_row = orm.CartModel.objects.create(code="ONETOONETEST", currency="UZS")
        item_row = orm.CartItemModel.objects.create(cart=cart_row, product_variant_id=uuid.uuid4(), quantity=1)
        orm.PriceSnapshotReferenceModel.objects.create(item=item_row, price_snapshot_id=uuid.uuid4(), unit_amount=Decimal("10.00"), currency="UZS", applied_at=datetime.utcnow())
        with pytest.raises(IntegrityError):
            orm.PriceSnapshotReferenceModel.objects.create(item=item_row, price_snapshot_id=uuid.uuid4(), unit_amount=Decimal("20.00"), currency="UZS", applied_at=datetime.utcnow())

    def test_list_expiring_before(self):
        from datetime import timedelta

        repo = DjangoCartRepository()
        cart = make_cart(expires_at=datetime.utcnow() - timedelta(minutes=1))
        repo.save(cart)
        expiring = repo.list_expiring_before(datetime.utcnow())
        assert any(c.id == cart.id for c in expiring)
