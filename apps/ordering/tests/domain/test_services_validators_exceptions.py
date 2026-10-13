from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from apps.ordering.domain import exceptions as exc
from apps.ordering.domain.entities import OrderLineItem
from apps.ordering.domain.enums import OrderStatus
from apps.ordering.domain.services import (
    CancellationPolicy,
    CheckoutPolicy,
    InvoiceNumberPolicy,
    OrderCreationPolicy,
    OrderExpirationPolicy,
    OrderValidationPolicy,
    ReturnEligibilityPolicy,
)
from apps.ordering.domain.validators import (
    AddressSnapshotValidator,
    OrderNoteValidator,
    OrderNumberValidator,
    ReturnNumberValidator,
    TrackingNumberValidator,
)
from apps.ordering.domain.value_objects import Money, ReturnWindow
from common.exceptions import DomainException

pytestmark = pytest.mark.unit


class TestCheckoutPolicy:
    def test_eligible_when_all_conditions_met(self):
        assert CheckoutPolicy.is_eligible(has_items=True, all_items_priced=True, is_locked=False) is True

    def test_ineligible_when_empty(self):
        assert CheckoutPolicy.is_eligible(has_items=False, all_items_priced=True, is_locked=False) is False

    def test_ineligible_when_locked(self):
        assert CheckoutPolicy.is_eligible(has_items=True, all_items_priced=True, is_locked=True) is False


class TestOrderCreationPolicy:
    def test_no_problems_when_valid(self):
        assert OrderCreationPolicy.validate_preconditions(1, True, True) == []

    def test_flags_zero_lines(self):
        problems = OrderCreationPolicy.validate_preconditions(0, True, True)
        assert len(problems) == 1

    def test_flags_missing_addresses(self):
        problems = OrderCreationPolicy.validate_preconditions(1, False, False)
        assert len(problems) == 2


class TestOrderValidationPolicy:
    def test_no_mismatch(self):
        line = OrderLineItem(id=uuid.uuid4(), product_variant_id=uuid.uuid4(), quantity=1, unit_price=Money(amount=Decimal("10.00"), currency="UZS"), discount_amount=Money(amount=Decimal("0"), currency="UZS"), tax_amount=Money(amount=Decimal("0"), currency="UZS"))
        assert OrderValidationPolicy.validate_currency_consistency([line], "UZS") == []

    def test_flags_mismatch(self):
        line = OrderLineItem(id=uuid.uuid4(), product_variant_id=uuid.uuid4(), quantity=1, unit_price=Money(amount=Decimal("10.00"), currency="USD"), discount_amount=Money(amount=Decimal("0"), currency="USD"), tax_amount=Money(amount=Decimal("0"), currency="USD"))
        problems = OrderValidationPolicy.validate_currency_consistency([line], "UZS")
        assert len(problems) == 1


class TestOrderExpirationPolicy:
    def test_compute_expiry_is_two_hours(self):
        created = datetime(2026, 1, 1, 10, 0)
        assert OrderExpirationPolicy.compute_expiry(created) == datetime(2026, 1, 1, 12, 0)

    def test_is_due_for_expiry_true(self):
        created = datetime(2026, 1, 1, 10, 0)
        assert OrderExpirationPolicy.is_due_for_expiry(created, datetime(2026, 1, 1, 13, 0)) is True

    def test_is_due_for_expiry_false(self):
        created = datetime(2026, 1, 1, 10, 0)
        assert OrderExpirationPolicy.is_due_for_expiry(created, datetime(2026, 1, 1, 10, 30)) is False


class TestCancellationPolicy:
    def test_eligible_for_direct_cancellation_when_confirmed(self):
        assert CancellationPolicy.is_eligible_for_direct_cancellation(OrderStatus.CONFIRMED) is True

    def test_ineligible_for_direct_cancellation_when_shipped(self):
        assert CancellationPolicy.is_eligible_for_direct_cancellation(OrderStatus.SHIPPED) is False

    def test_requires_formal_approval_when_shipped(self):
        assert CancellationPolicy.requires_formal_approval(OrderStatus.SHIPPED) is True

    def test_does_not_require_formal_approval_when_pending(self):
        assert CancellationPolicy.requires_formal_approval(OrderStatus.PENDING_PAYMENT) is False


class TestReturnEligibilityPolicy:
    def test_eligible_when_delivered_and_within_window(self):
        window = ReturnWindow(timedelta(days=14))
        assert ReturnEligibilityPolicy.is_eligible(OrderStatus.DELIVERED, datetime(2026, 1, 1), datetime(2026, 1, 5), window) is True

    def test_ineligible_when_not_delivered(self):
        window = ReturnWindow(timedelta(days=14))
        assert ReturnEligibilityPolicy.is_eligible(OrderStatus.PROCESSING, datetime(2026, 1, 1), datetime(2026, 1, 5), window) is False

    def test_ineligible_when_no_delivery_date(self):
        window = ReturnWindow(timedelta(days=14))
        assert ReturnEligibilityPolicy.is_eligible(OrderStatus.DELIVERED, None, datetime(2026, 1, 5), window) is False

    def test_ineligible_when_window_expired(self):
        window = ReturnWindow(timedelta(days=14))
        assert ReturnEligibilityPolicy.is_eligible(OrderStatus.DELIVERED, datetime(2026, 1, 1), datetime(2026, 2, 1), window) is False


class TestInvoiceNumberPolicy:
    def test_format(self):
        assert InvoiceNumberPolicy.format(5, 2026) == "INV-2026-00000005"

    def test_format_pads_correctly(self):
        assert InvoiceNumberPolicy.format(1, 2026) == "INV-2026-00000001"


class TestValidators:
    def test_order_number_validator(self):
        assert OrderNumberValidator("ORD-A1B2C3").value == "ORD-A1B2C3"

    def test_return_number_validator(self):
        assert ReturnNumberValidator("RET-A1B2C3").value == "RET-A1B2C3"

    def test_tracking_number_validator(self):
        assert TrackingNumberValidator("1Z999AA10123456784").value == "1Z999AA10123456784"

    def test_order_note_validator(self):
        assert OrderNoteValidator("hello").text == "hello"

    def test_address_snapshot_validator(self):
        addr = AddressSnapshotValidator(recipient_name="Jane Doe", line1="123 Main St", city="Tashkent", country_code="UZ")
        assert addr.city == "Tashkent"


@pytest.mark.parametrize(
    "exception_cls",
    [
        exc.InvalidOrderLifecycleTransition, exc.OrderNotModifiable, exc.OrderLineItemNotFound, exc.EmptyOrder,
        exc.OrderAlreadyCancelled, exc.OrderAlreadyCompleted, exc.InvalidReturnLifecycleTransition, exc.ReturnWindowExpired,
        exc.ReturnQuantityExceedsOrdered, exc.InvalidCancellationLifecycleTransition, exc.CancellationQuantityExceedsOrdered,
        exc.OrderNotEligibleForCancellation, exc.InvalidInvoiceLifecycleTransition, exc.InvoiceAlreadyIssued,
        exc.PaymentReferenceNotFound, exc.FulfillmentReferenceNotFound, exc.CurrencyMismatch, exc.OrderEntityNotFound,
        exc.OrderAlreadyLocked, exc.OrderNotLocked, exc.OrderLocked, exc.InvalidOrderArchivalTransition,
    ],
)
def test_every_exception_subclasses_domain_exception(exception_cls):
    assert issubclass(exception_cls, DomainException)
    instance = exception_cls("test message")
    assert instance.message == "test message"
    assert instance.code


def test_programmatically_verify_exactly_22_exceptions():
    """AST-parses exceptions.py directly, per this phase's explicit instruction to verify programmatically rather than trust a hardcoded count."""
    import ast

    import apps.ordering.domain.exceptions as exceptions_module

    tree = ast.parse(open(exceptions_module.__file__).read())
    class_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    assert len(class_names) == 22, f"Expected exactly 22 Ordering domain exceptions, found {len(class_names)}: {class_names}"
