from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import pytest

from apps.cart.domain.entities import (
    CartAuditEntry,
    CartItem,
    CartSnapshot,
    CartValidationIssue,
    InventoryReservationReference,
    PriceReference,
    ShippingEstimateReference,
    TaxEstimateReference,
)
from apps.cart.domain.enums import CartItemStatus, CartValidationIssueCode, CartValidationSeverity
from apps.cart.domain.value_objects import EstimatedAmount, Money, Quantity, SnapshotToken

pytestmark = pytest.mark.unit


class TestCartItem:
    def test_default_status_is_active(self):
        item = CartItem(id=uuid.uuid4(), product_variant_id=uuid.uuid4(), quantity=Quantity(1))
        assert item.status == CartItemStatus.ACTIVE

    def test_line_total_none_without_price(self):
        item = CartItem(id=uuid.uuid4(), product_variant_id=uuid.uuid4(), quantity=Quantity(3))
        assert item.line_total() is None

    def test_line_total_computed_with_price(self):
        price_ref = PriceReference(price_snapshot_id=uuid.uuid4(), unit_amount=Money(amount=Decimal("10.00"), currency="UZS"), applied_at=datetime.utcnow())
        item = CartItem(id=uuid.uuid4(), product_variant_id=uuid.uuid4(), quantity=Quantity(3), price_reference=price_ref)
        assert item.line_total().amount == Decimal("30.00")

    def test_mutation_quantity(self):
        item = CartItem(id=uuid.uuid4(), product_variant_id=uuid.uuid4(), quantity=Quantity(1))
        item.quantity = Quantity(5)
        assert item.quantity.value == 5


class TestPriceReference:
    def test_construction(self):
        ref = PriceReference(price_snapshot_id=uuid.uuid4(), unit_amount=Money(amount=Decimal("10.00"), currency="UZS"), applied_at=datetime.utcnow())
        assert ref.unit_amount.amount == Decimal("10.00")


class TestInventoryReservationReference:
    def test_construction_without_expiry(self):
        ref = InventoryReservationReference(reservation_id=uuid.uuid4(), reserved_at=datetime.utcnow())
        assert ref.expires_at is None

    def test_construction_with_expiry(self):
        expiry = datetime.utcnow()
        ref = InventoryReservationReference(reservation_id=uuid.uuid4(), reserved_at=datetime.utcnow(), expires_at=expiry)
        assert ref.expires_at == expiry


class TestCartSnapshot:
    def test_construction(self):
        snapshot = CartSnapshot(id=uuid.uuid4(), token=SnapshotToken(uuid.uuid4()), version_at_capture=3, captured_at=datetime.utcnow(), items_snapshot=({"product_variant_id": "x", "quantity": 2},))
        assert snapshot.version_at_capture == 3
        assert len(snapshot.items_snapshot) == 1

    def test_default_empty_items(self):
        snapshot = CartSnapshot(id=uuid.uuid4(), token=SnapshotToken(uuid.uuid4()), version_at_capture=1, captured_at=datetime.utcnow())
        assert snapshot.items_snapshot == ()


class TestCartAuditEntry:
    def test_construction_with_details(self):
        entry = CartAuditEntry(id=uuid.uuid4(), action="item_added", actor_id=None, occurred_at=datetime.utcnow(), details={"quantity": 3})
        assert entry.details["quantity"] == 3

    def test_default_empty_details(self):
        entry = CartAuditEntry(id=uuid.uuid4(), action="cart_cleared", actor_id=None, occurred_at=datetime.utcnow())
        assert entry.details == {}


class TestCartValidationIssue:
    def test_construction(self):
        issue = CartValidationIssue(id=uuid.uuid4(), severity=CartValidationSeverity.ERROR, code=CartValidationIssueCode.EMPTY_CART, message="The cart has no active items.")
        assert issue.item_id is None

    def test_construction_with_item_id(self):
        item_id = uuid.uuid4()
        issue = CartValidationIssue(id=uuid.uuid4(), severity=CartValidationSeverity.WARNING, code=CartValidationIssueCode.ITEM_PRICE_CHANGED, message="Price changed.", item_id=item_id)
        assert issue.item_id == item_id


class TestShippingAndTaxEstimateReferences:
    def test_shipping_estimate_reference(self):
        ref = ShippingEstimateReference(shipping_estimate_id=uuid.uuid4(), estimated_amount=EstimatedAmount(amount=Money(amount=Decimal("5.00"), currency="UZS")), estimated_at=datetime.utcnow())
        assert ref.estimated_amount.is_final is False

    def test_tax_estimate_reference(self):
        ref = TaxEstimateReference(tax_estimate_id=uuid.uuid4(), estimated_amount=EstimatedAmount(amount=Money(amount=Decimal("2.00"), currency="UZS"), is_final=True), estimated_at=datetime.utcnow())
        assert ref.estimated_amount.is_final is True
