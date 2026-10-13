from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import pytest

from apps.ordering.domain.entities import (
    CancellationLineItem,
    OrderFailure,
    OrderFulfillmentReference,
    OrderInvoice,
    OrderLineItem,
    OrderPaymentReference,
    OrderStatusHistoryEntry,
    ReturnLineItem,
)
from apps.ordering.domain.enums import (
    FulfillmentReferenceStatus,
    InvoiceStatus,
    OrderFailureReason,
    OrderLineItemStatus,
    PaymentReferenceStatus,
)
from apps.ordering.domain.value_objects import Money
from common.exceptions import ValidationFailed

pytestmark = pytest.mark.unit


def _money(amount: str) -> Money:
    return Money(amount=Decimal(amount), currency="UZS")


class TestOrderLineItem:
    def test_default_status_active(self):
        line = OrderLineItem(id=uuid.uuid4(), product_variant_id=uuid.uuid4(), quantity=2, unit_price=_money("50.00"), discount_amount=_money("0.00"), tax_amount=_money("0.00"))
        assert line.status == OrderLineItemStatus.ACTIVE

    def test_rejects_non_positive_quantity(self):
        with pytest.raises(ValidationFailed):
            OrderLineItem(id=uuid.uuid4(), product_variant_id=uuid.uuid4(), quantity=0, unit_price=_money("50.00"), discount_amount=_money("0.00"), tax_amount=_money("0.00"))

    def test_line_total_computation(self):
        line = OrderLineItem(id=uuid.uuid4(), product_variant_id=uuid.uuid4(), quantity=3, unit_price=_money("50.00"), discount_amount=_money("10.00"), tax_amount=_money("5.00"))
        assert line.line_total().amount == Decimal("145.00")  # (50*3) - 10 + 5

    def test_optional_references_default_none(self):
        line = OrderLineItem(id=uuid.uuid4(), product_variant_id=uuid.uuid4(), quantity=1, unit_price=_money("50.00"), discount_amount=_money("0.00"), tax_amount=_money("0.00"))
        assert line.price_snapshot_id is None
        assert line.reservation_id is None


class TestOrderStatusHistoryEntry:
    def test_construction(self):
        entry = OrderStatusHistoryEntry(id=uuid.uuid4(), from_status="draft", to_status="pending_payment", reason="created", changed_at=datetime.utcnow())
        assert entry.from_status == "draft"

    def test_first_entry_has_no_from_status(self):
        entry = OrderStatusHistoryEntry(id=uuid.uuid4(), from_status=None, to_status="draft", reason=None, changed_at=datetime.utcnow())
        assert entry.from_status is None


class TestOrderPaymentReference:
    def test_default_status_pending(self):
        ref = OrderPaymentReference(id=uuid.uuid4(), payment_id=uuid.uuid4(), amount=_money("100.00"))
        assert ref.status == PaymentReferenceStatus.PENDING
        assert ref.processed_at is None


class TestOrderFulfillmentReference:
    def test_default_status_pending(self):
        ref = OrderFulfillmentReference(id=uuid.uuid4(), fulfillment_id=uuid.uuid4())
        assert ref.status == FulfillmentReferenceStatus.PENDING
        assert ref.tracking_number is None


class TestOrderInvoice:
    def test_default_status_draft(self):
        invoice = OrderInvoice(id=uuid.uuid4(), invoice_number="INV-2026-00000001", total_amount=_money("100.00"))
        assert invoice.status == InvoiceStatus.DRAFT
        assert invoice.issued_at is None


class TestOrderFailure:
    def test_construction(self):
        failure = OrderFailure(id=uuid.uuid4(), reason=OrderFailureReason.PAYMENT_DECLINED, detail="Card declined", occurred_at=datetime.utcnow())
        assert failure.reason == OrderFailureReason.PAYMENT_DECLINED


class TestReturnLineItem:
    def test_construction(self):
        line = ReturnLineItem(id=uuid.uuid4(), order_line_item_id=uuid.uuid4(), quantity=1)
        assert line.quantity == 1

    def test_rejects_non_positive_quantity(self):
        with pytest.raises(ValidationFailed):
            ReturnLineItem(id=uuid.uuid4(), order_line_item_id=uuid.uuid4(), quantity=0)


class TestCancellationLineItem:
    def test_construction(self):
        line = CancellationLineItem(id=uuid.uuid4(), order_line_item_id=uuid.uuid4(), quantity=1)
        assert line.quantity == 1

    def test_rejects_non_positive_quantity(self):
        with pytest.raises(ValidationFailed):
            CancellationLineItem(id=uuid.uuid4(), order_line_item_id=uuid.uuid4(), quantity=-1)
