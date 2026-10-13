from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from apps.cart.domain import exceptions as exc
from apps.cart.domain.entities import CartItem
from apps.cart.domain.enums import CartItemStatus, CheckoutReadiness, MergeStrategy
from apps.cart.domain.services import (
    CartMergePolicy,
    CartValidationPolicy,
    CheckoutReadinessPolicy,
    CurrencyConversionPolicy,
    ExpirationPolicy,
    QuantityPolicy,
    SnapshotPolicy,
)
from apps.cart.domain.validators import (
    CartCodeValidator,
    CartNoteValidator,
    CurrencyValidator,
    GiftMessageValidator,
    ItemCountValidator,
    MaxQuantityValidator,
    QuantityValidator,
    RegionValidator,
)
from apps.cart.domain.value_objects import Money, Quantity
from common.exceptions import DomainException, ValidationFailed

pytestmark = pytest.mark.unit


class TestCartMergePolicy:
    def test_recommends_replace_when_authenticated_empty(self):
        assert CartMergePolicy.recommend_strategy(3, 0) == MergeStrategy.REPLACE_WITH_GUEST

    def test_recommends_keep_authenticated_when_guest_empty(self):
        assert CartMergePolicy.recommend_strategy(0, 3) == MergeStrategy.KEEP_AUTHENTICATED

    def test_recommends_sum_when_both_populated(self):
        assert CartMergePolicy.recommend_strategy(2, 2) == MergeStrategy.SUM_QUANTITIES


class TestQuantityPolicy:
    def test_within_max_passes(self):
        QuantityPolicy.assert_within_max(500)

    def test_exceeds_max_raises(self):
        with pytest.raises(exc.InvalidQuantity):
            QuantityPolicy.assert_within_max(1000)


class TestExpirationPolicy:
    def test_guest_expiry_is_seven_days(self):
        now = datetime(2026, 1, 1)
        expiry = ExpirationPolicy.compute_expiry(now, is_guest=True)
        assert expiry == now + timedelta(days=7)

    def test_authenticated_expiry_is_thirty_days(self):
        now = datetime(2026, 1, 1)
        expiry = ExpirationPolicy.compute_expiry(now, is_guest=False)
        assert expiry == now + timedelta(days=30)

    def test_is_due_for_expiry_true(self):
        assert ExpirationPolicy.is_due_for_expiry(datetime(2026, 1, 1), datetime(2026, 1, 2)) is True

    def test_is_due_for_expiry_false_when_no_expiry_set(self):
        assert ExpirationPolicy.is_due_for_expiry(None, datetime(2026, 1, 2)) is False


class TestSnapshotPolicy:
    def test_can_add_below_max(self):
        assert SnapshotPolicy.can_add_snapshot(5) is True

    def test_cannot_add_at_max(self):
        assert SnapshotPolicy.can_add_snapshot(SnapshotPolicy.MAX_SNAPSHOTS_PER_CART) is False

    def test_oldest_snapshot_to_prune(self):
        id_a, id_b = uuid.uuid4(), uuid.uuid4()
        oldest = SnapshotPolicy.oldest_snapshot_id_to_prune([(id_a, datetime(2026, 1, 2)), (id_b, datetime(2026, 1, 1))])
        assert oldest == id_b

    def test_oldest_snapshot_empty_list_returns_none(self):
        assert SnapshotPolicy.oldest_snapshot_id_to_prune([]) is None


class TestCartValidationPolicy:
    def test_empty_cart_produces_error(self):
        issues = CartValidationPolicy.validate([], is_locked=False, is_expired=False, currency="UZS")
        assert any(i.code.value == "empty_cart" for i in issues)

    def test_locked_cart_produces_error(self):
        item = CartItem(id=uuid.uuid4(), product_variant_id=uuid.uuid4(), quantity=Quantity(1))
        issues = CartValidationPolicy.validate([item], is_locked=True, is_expired=False, currency="UZS")
        assert any(i.code.value == "cart_locked" for i in issues)

    def test_out_of_stock_item_produces_error(self):
        item = CartItem(id=uuid.uuid4(), product_variant_id=uuid.uuid4(), quantity=Quantity(1), status=CartItemStatus.OUT_OF_STOCK)
        issues = CartValidationPolicy.validate([item], is_locked=False, is_expired=False, currency="UZS")
        assert any(i.code.value == "item_out_of_stock" and i.severity.value == "error" for i in issues)

    def test_unpriced_item_produces_warning_not_error(self):
        item = CartItem(id=uuid.uuid4(), product_variant_id=uuid.uuid4(), quantity=Quantity(1))
        issues = CartValidationPolicy.validate([item], is_locked=False, is_expired=False, currency="UZS")
        no_price_issue = next(i for i in issues if i.code.value == "no_price_snapshot")
        assert no_price_issue.severity.value == "warning"

    def test_has_blocking_errors_true(self):
        issues = CartValidationPolicy.validate([], is_locked=False, is_expired=False, currency="UZS")
        assert CartValidationPolicy.has_blocking_errors(issues) is True

    def test_has_blocking_errors_false_for_warnings_only(self):
        from apps.cart.domain.entities import PriceReference
        from apps.cart.domain.value_objects import Money as _Money

        item = CartItem(id=uuid.uuid4(), product_variant_id=uuid.uuid4(), quantity=Quantity(1), price_reference=PriceReference(price_snapshot_id=uuid.uuid4(), unit_amount=_Money(amount=Decimal("10.00"), currency="UZS"), applied_at=datetime.utcnow()))
        issues = CartValidationPolicy.validate([item], is_locked=False, is_expired=False, currency="UZS")
        assert CartValidationPolicy.has_blocking_errors(issues) is False


class TestCheckoutReadinessPolicy:
    def test_structural_blocked_stays_blocked(self):
        result = CheckoutReadinessPolicy.evaluate(CheckoutReadiness.BLOCKED, all_reservations_valid=True, validation_issues=[])
        assert result == CheckoutReadiness.BLOCKED

    def test_invalid_reservations_forces_not_ready(self):
        result = CheckoutReadinessPolicy.evaluate(CheckoutReadiness.READY, all_reservations_valid=False, validation_issues=[])
        assert result == CheckoutReadiness.NOT_READY

    def test_ready_when_all_signals_good(self):
        result = CheckoutReadinessPolicy.evaluate(CheckoutReadiness.READY, all_reservations_valid=True, validation_issues=[])
        assert result == CheckoutReadiness.READY


class TestCurrencyConversionPolicy:
    def test_accepts_matching_target_currency(self):
        original = Money(amount=Decimal("10.00"), currency="USD")
        converted = Money(amount=Decimal("120000.00"), currency="UZS")
        result = CurrencyConversionPolicy.apply_supplied_conversion(original, converted, "UZS")
        assert result.currency == "UZS"

    def test_rejects_mismatched_target_currency(self):
        original = Money(amount=Decimal("10.00"), currency="USD")
        converted = Money(amount=Decimal("120000.00"), currency="UZS")
        with pytest.raises(ValidationFailed):
            CurrencyConversionPolicy.apply_supplied_conversion(original, converted, "EUR")


class TestValidators:
    def test_cart_code_validator(self):
        assert CartCodeValidator("A1B2C3D4E5").value == "A1B2C3D4E5"

    def test_quantity_validator(self):
        assert QuantityValidator(5).value == 5

    def test_cart_note_validator(self):
        assert CartNoteValidator("hello").text == "hello"

    def test_gift_message_validator(self):
        assert GiftMessageValidator("hi").text == "hi"

    def test_currency_validator(self):
        assert CurrencyValidator("UZS").value == "UZS"

    def test_region_validator(self):
        assert RegionValidator("UZ").value == "UZ"

    def test_max_quantity_validator_passes(self):
        MaxQuantityValidator(500)

    def test_max_quantity_validator_raises(self):
        with pytest.raises(exc.InvalidQuantity):
            MaxQuantityValidator(1000)

    def test_item_count_validator_passes(self):
        ItemCountValidator(50)

    def test_item_count_validator_raises_at_max(self):
        with pytest.raises(ValidationFailed):
            ItemCountValidator(200)


@pytest.mark.parametrize(
    "exception_cls",
    [
        exc.CartLocked, exc.CartAlreadyLocked, exc.CartNotLocked, exc.CartExpired, exc.CartArchived,
        exc.CartAlreadyConverted, exc.InvalidCartLifecycleTransition, exc.CartItemNotFound, exc.InvalidQuantity,
        exc.EmptyCart, exc.CartNotEligibleForCheckout, exc.CartOwnershipConflict, exc.CartMergeConflict,
        exc.CartSnapshotNotFound, exc.CurrencyMismatch, exc.CartValidationFailed, exc.CartEntityNotFound,
    ],
)
def test_every_exception_subclasses_domain_exception(exception_cls):
    assert issubclass(exception_cls, DomainException)
    instance = exception_cls("test message")
    assert instance.message == "test message"
    assert instance.code


def test_exception_count_matches_source_exactly():
    import ast

    import apps.cart.domain.exceptions as exceptions_module

    tree = ast.parse(open(exceptions_module.__file__).read())
    class_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    assert len(class_names) == 17
