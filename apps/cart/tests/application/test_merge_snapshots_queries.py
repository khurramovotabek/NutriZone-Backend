from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from apps.cart.application.services._shared import CartServiceContext
from apps.cart.application.services.merge_and_ownership import AssignCustomer, MergeGuestCart
from apps.cart.application.services.queries import AdminListCarts, GetCart, GetSnapshotHistory, ListCustomerCarts
from apps.cart.application.services.snapshots_and_validation import (
    CalculateCheckoutReadiness, CreateSnapshot, RestoreSnapshot, ValidateCart,
)
from apps.cart.domain.enums import CartType
from apps.cart.tests.application.fakes import FakeCartRepository, collect_events
from apps.cart.tests.factories import make_active_cart, make_cart
from common.exceptions import ResourceNotFound

pytestmark = pytest.mark.django_db


def _ctx():
    events: list = []
    return CartServiceContext(stage_events=collect_events(events), actor_id=uuid.uuid4()), events


class TestAssignCustomerAndMerge:
    def test_assign_customer(self):
        repo = FakeCartRepository()
        cart = make_cart()
        repo.save(cart)
        ctx, events = _ctx()
        customer_id = uuid.uuid4()
        updated = AssignCustomer(repo, ctx).execute(cart_id=cart.id, customer_id=customer_id)
        assert updated.customer_id == customer_id
        assert any(e[0] == "CustomerAssigned" for e in events)

    def test_merge_guest_cart_with_explicit_strategy(self):
        repo = FakeCartRepository()
        auth_cart = make_cart(cart_type=CartType.AUTHENTICATED)
        guest_cart = make_cart()
        variant_id = uuid.uuid4()
        auth_cart.add_item(variant_id, 2, datetime.utcnow())
        guest_cart.add_item(variant_id, 3, datetime.utcnow())
        repo.save(auth_cart)
        repo.save(guest_cart)

        ctx, events = _ctx()
        merged = MergeGuestCart(repo, ctx).execute(guest_cart_id=guest_cart.id, authenticated_cart_id=auth_cart.id, strategy="sum_quantities")
        merged_item = next(i for i in merged.items.values() if i.product_variant_id == variant_id)
        assert merged_item.quantity.value == 5
        assert any(e[0] == "CartMerged" for e in events)

    def test_merge_archives_guest_cart(self):
        repo = FakeCartRepository()
        auth_cart = make_cart(cart_type=CartType.AUTHENTICATED)
        guest_cart = make_cart()
        repo.save(auth_cart)
        repo.save(guest_cart)

        ctx, _ = _ctx()
        MergeGuestCart(repo, ctx).execute(guest_cart_id=guest_cart.id, authenticated_cart_id=auth_cart.id, strategy="sum_quantities")
        assert repo.get_by_id(guest_cart.id).status.value == "archived"

    def test_merge_missing_guest_cart_raises(self):
        repo = FakeCartRepository()
        auth_cart = make_cart(cart_type=CartType.AUTHENTICATED)
        repo.save(auth_cart)
        ctx, _ = _ctx()
        with pytest.raises(ResourceNotFound):
            MergeGuestCart(repo, ctx).execute(guest_cart_id=uuid.uuid4(), authenticated_cart_id=auth_cart.id)


class TestSnapshotsAndValidation:
    def test_create_and_restore_snapshot(self):
        repo = FakeCartRepository()
        cart = make_cart()
        cart.add_item(uuid.uuid4(), 3, datetime.utcnow())
        repo.save(cart)
        ctx, events = _ctx()

        snapshot = CreateSnapshot(repo, ctx).execute(cart.id)
        assert any(e[0] == "CartSnapshotCreated" for e in events)

        cart_reloaded = repo.get_by_id(cart.id)
        cart_reloaded.add_item(uuid.uuid4(), 1, datetime.utcnow())
        repo.save(cart_reloaded)

        restored = RestoreSnapshot(repo, ctx).execute(cart_id=cart.id, snapshot_id=snapshot.id)
        active_items = [i for i in restored.items.values() if i.status.value != "removed"]
        assert len(active_items) == 1
        assert any(e[0] == "CartSnapshotRestored" for e in events)

    def test_validate_cart_reports_issues(self):
        repo = FakeCartRepository()
        cart = make_cart()
        repo.save(cart)
        issues = ValidateCart(repo).execute(cart.id)
        assert any(i.code.value == "empty_cart" for i in issues)

    def test_calculate_checkout_readiness_ready(self):
        repo = FakeCartRepository()
        cart = make_active_cart()
        repo.save(cart)
        readiness = CalculateCheckoutReadiness(repo).execute(cart.id)
        assert readiness == "ready"

    def test_calculate_checkout_readiness_blocked_when_empty(self):
        """BLOCKED, not NOT_READY: an empty cart produces an ERROR-severity EMPTY_CART validation issue (CartValidationPolicy.validate()), which CheckoutReadinessPolicy.evaluate() correctly escalates to the more severe BLOCKED state -- confirmed by reading the real policy logic, not assumed."""
        repo = FakeCartRepository()
        cart = make_cart()
        repo.save(cart)
        readiness = CalculateCheckoutReadiness(repo).execute(cart.id)
        assert readiness == "blocked"


class TestQueries:
    def test_get_cart(self):
        repo = FakeCartRepository()
        cart = make_cart()
        repo.save(cart)
        assert GetCart(repo).execute(cart.id).id == cart.id

    def test_get_cart_missing_raises(self):
        with pytest.raises(ResourceNotFound):
            GetCart(FakeCartRepository()).execute(uuid.uuid4())

    def test_list_customer_carts(self):
        repo = FakeCartRepository()
        customer_id = uuid.uuid4()
        repo.save(make_cart(customer_id=customer_id, cart_type=CartType.AUTHENTICATED))
        results, total = ListCustomerCarts(repo).execute(customer_id)
        assert total == 1

    def test_admin_list_carts(self):
        repo = FakeCartRepository()
        repo.save(make_cart())
        results, total = AdminListCarts(repo).execute()
        assert total == 1

    def test_get_snapshot_history(self):
        repo = FakeCartRepository()
        cart = make_cart()
        cart.create_snapshot(datetime.utcnow())
        repo.save(cart)
        history = GetSnapshotHistory(repo).execute(cart.id)
        assert len(history) == 1

    def test_search_cart(self):
        from apps.cart.application.services.queries import SearchCart

        class _FakeSearchGateway:
            def search(self, query, filters, page, page_size):
                return [{"code": "TESTCART0001"}], 1

        results, total = SearchCart(_FakeSearchGateway()).execute("TESTCART", {})
        assert total == 1
