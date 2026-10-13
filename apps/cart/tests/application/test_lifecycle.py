from __future__ import annotations

import uuid

import pytest

from apps.cart.application.services._shared import CartServiceContext
from apps.cart.application.services.lifecycle import (
    ArchiveCart, CreateCart, ExpireCart, LoadCart, LockCart, RestoreCart, SaveCart, UnlockCart, UpdateCartDetails,
)
from apps.cart.domain.enums import CartLockReason
from apps.cart.tests.application.fakes import FakeCartRepository, collect_events
from apps.cart.tests.factories import make_cart
from common.exceptions import ResourceNotFound

pytestmark = pytest.mark.django_db  # every service uses @transaction.atomic -- same documented rationale as every prior module


def _ctx():
    events: list = []
    return CartServiceContext(stage_events=collect_events(events), actor_id=uuid.uuid4()), events


class TestCreateCart:
    def test_creates_guest_cart_with_expiry(self):
        repo = FakeCartRepository()
        ctx, events = _ctx()
        cart = CreateCart(repo, ctx).execute()
        assert cart.status.value == "active"
        assert cart.expires_at is not None
        assert any(e[0] == "CartCreated" for e in events)

    def test_guest_cart_has_no_customer_id(self):
        """Correct, unchanged behavior for guest carts -- only authenticated carts should be auto-assigned."""
        repo = FakeCartRepository()
        ctx, events = _ctx()
        cart = CreateCart(repo, ctx).execute(cart_type="guest")
        assert cart.customer_id is None

    def test_authenticated_cart_is_assigned_to_the_actor_who_created_it(self):
        """
        Phase 16.8: closes a real, confirmed, severe production blocker
        -- proven live via a real end-to-end HTTP flow that an
        "authenticated" cart with no customer_id resulted in
        PERMISSION_DENIED for the very user who had just created it,
        since every ownership check requires a matching customer_id
        that was never being set.
        """
        repo = FakeCartRepository()
        ctx, events = _ctx()
        cart = CreateCart(repo, ctx).execute(cart_type="authenticated")
        assert cart.customer_id == ctx.actor_id
        assert any(e[0] == "CustomerAssigned" for e in events)

    def test_authenticated_cart_without_an_actor_id_does_not_crash(self):
        """Defensive guard: an authenticated cart created with no resolvable actor (e.g. a system/background process) must not raise, just remain unassigned."""
        repo = FakeCartRepository()
        events: list = []
        ctx = CartServiceContext(stage_events=collect_events(events), actor_id=None)
        cart = CreateCart(repo, ctx).execute(cart_type="authenticated")
        assert cart.customer_id is None


class TestLoadCart:
    def test_load_by_id(self):
        repo = FakeCartRepository()
        cart = make_cart()
        repo.save(cart)
        assert LoadCart(repo).execute(cart_id=cart.id).id == cart.id

    def test_load_by_code(self):
        """Added during Phase 3 -- see certification report for why get_by_code exists."""
        repo = FakeCartRepository()
        cart = make_cart()
        repo.save(cart)
        assert LoadCart(repo).execute(code=cart.code.value).id == cart.id

    def test_load_by_token(self):
        repo = FakeCartRepository()
        cart = make_cart()
        repo.save(cart)
        assert LoadCart(repo).execute(token=str(cart.token)).id == cart.id

    def test_load_missing_raises(self):
        with pytest.raises(ResourceNotFound):
            LoadCart(FakeCartRepository()).execute(cart_id=uuid.uuid4())


class TestSaveArchiveExpireRestore:
    def test_save_cart(self):
        repo = FakeCartRepository()
        cart = make_cart()
        repo.save(cart)
        ctx, events = _ctx()
        saved = SaveCart(repo, ctx).execute(cart.id)
        assert saved.status.value == "saved"
        assert any(e[0] == "CartSaved" for e in events)

    def test_archive_cart(self):
        repo = FakeCartRepository()
        cart = make_cart()
        repo.save(cart)
        ctx, events = _ctx()
        archived = ArchiveCart(repo, ctx).execute(cart.id)
        assert archived.status.value == "archived"
        assert any(e[0] == "CartArchivedEvent" for e in events)

    def test_restore_cart(self):
        repo = FakeCartRepository()
        cart = make_cart()
        cart.archive()
        repo.save(cart)
        ctx, events = _ctx()
        restored = RestoreCart(repo, ctx).execute(cart.id)
        assert restored.status.value == "active"
        assert any(e[0] == "CartRestored" for e in events)

    def test_expire_missing_cart_raises(self):
        ctx, _ = _ctx()
        with pytest.raises(ResourceNotFound):
            ExpireCart(FakeCartRepository(), ctx).execute(uuid.uuid4())


class TestLockUnlockUpdateDetails:
    """Added during Phase 3 -- LockCart/UnlockCart/UpdateCartDetails did not exist in Phase 1's original 28-service set. See certification report."""

    def test_lock_cart(self):
        repo = FakeCartRepository()
        cart = make_cart()
        repo.save(cart)
        ctx, events = _ctx()
        locked = LockCart(repo, ctx).execute(cart_id=cart.id, reason=CartLockReason.CHECKOUT_IN_PROGRESS.value)
        assert locked.lock_reason == CartLockReason.CHECKOUT_IN_PROGRESS
        assert any(e[0] == "CartLockedEvent" for e in events)

    def test_unlock_cart(self):
        repo = FakeCartRepository()
        cart = make_cart()
        cart.lock(CartLockReason.ADMIN_HOLD)
        repo.save(cart)
        ctx, events = _ctx()
        unlocked = UnlockCart(repo, ctx).execute(cart.id)
        assert unlocked.lock_reason is None
        assert any(e[0] == "CartUnlocked" for e in events)

    def test_update_cart_details_note(self):
        repo = FakeCartRepository()
        cart = make_cart()
        repo.save(cart)
        ctx, _ = _ctx()
        updated = UpdateCartDetails(repo, ctx).execute(cart_id=cart.id, note="Deliver after 6pm")
        assert updated.note.text == "Deliver after 6pm"

    def test_update_cart_details_gift_message(self):
        repo = FakeCartRepository()
        cart = make_cart()
        repo.save(cart)
        ctx, _ = _ctx()
        updated = UpdateCartDetails(repo, ctx).execute(cart_id=cart.id, gift_message="Happy Birthday!")
        assert updated.gift_message.text == "Happy Birthday!"
