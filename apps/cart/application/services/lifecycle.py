"""
Cart Lifecycle Application Services: CreateCart, LoadCart, SaveCart,
ArchiveCart, ExpireCart, RestoreCart.
"""
from __future__ import annotations

import uuid

from django.db import transaction
from django.utils import timezone as django_timezone

from apps.cart.application.ports import CartRepository
from apps.cart.application.services._shared import CartServiceContext
from apps.cart.domain.aggregates import Cart
from apps.cart.domain.enums import CartSource, CartType
from apps.cart.domain.services import ExpirationPolicy
from apps.cart.domain.value_objects import CartCode, CartToken, CurrencyCode
from common.exceptions import ResourceNotFound


def _generate_cart_code() -> str:
    return uuid.uuid4().hex[:12].upper()


class CreateCart:
    def __init__(self, repo: CartRepository, ctx: CartServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, currency: str = "UZS", cart_type: str = CartType.GUEST.value, source: str = CartSource.WEB.value, region: str | None = None, channel: str | None = None) -> Cart:
        with self._ctx.timer("cart_create_duration"):
            from apps.cart.domain.value_objects import ChannelCode, RegionCode

            now = django_timezone.now()
            is_guest = cart_type == CartType.GUEST.value
            cart = Cart(
                id=uuid.uuid4(), code=CartCode(_generate_cart_code()), token=CartToken(uuid.uuid4()), currency=CurrencyCode(currency),
                cart_type=CartType(cart_type), source=CartSource(source), region=RegionCode(region) if region else None,
                channel=ChannelCode(channel) if channel else None, expires_at=ExpirationPolicy.compute_expiry(now, is_guest),
            )
            saved = self._repo.save(cart)

            from apps.cart.domain.events import CartCreated

            events = [("CartCreated", CartCreated(cart_id=saved.id, cart_type=cart_type, source=source).to_payload())]

            # Phase 16.8: closes a real, confirmed production blocker --
            # an "authenticated" cart with no customer_id was unusable
            # (PERMISSION_DENIED) by the very user who created it,
            # proven live via a real end-to-end HTTP flow before this fix.
            if cart_type == CartType.AUTHENTICATED.value and self._ctx.actor_id is not None:
                from apps.cart.domain.events import CustomerAssigned

                assigned_event = saved.assign_customer(self._ctx.actor_id, now)
                saved = self._repo.save(saved)
                events.append(("CustomerAssigned", assigned_event.to_payload()))

            self._ctx.stage_events(events)
            self._ctx.audit().created(entity_type="Cart", entity_id=str(saved.id), after={"cart_type": cart_type, "source": source})
            self._ctx.invalidate_cart_cache()
            self._ctx.metric("carts_created_total")
            return saved


class LoadCart:
    """By code (public URL identifier), token (guest access), or id (admin access) -- a single query service backing 'Load Cart', never mutating. `code` support added during Phase 3 (Interfaces) -- see CartRepository.get_by_code's docstring for why."""

    def __init__(self, repo: CartRepository) -> None:
        self._repo = repo

    def execute(self, cart_id: uuid.UUID | None = None, code: str | None = None, token: str | None = None) -> Cart:
        cart = None
        if cart_id:
            cart = self._repo.get_by_id(cart_id)
        elif code:
            cart = self._repo.get_by_code(code)
        elif token:
            cart = self._repo.get_by_token(token)
        if cart is None:
            raise ResourceNotFound("Cart not found.")
        return cart


class SaveCart:
    def __init__(self, repo: CartRepository, ctx: CartServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, cart_id: uuid.UUID) -> Cart:
        cart = self._repo.get_by_id(cart_id)
        if cart is None:
            raise ResourceNotFound("Cart not found.")
        event = cart.save()
        saved = self._repo.save(cart)
        self._ctx.stage_events([("CartSaved", event.to_payload())])
        self._ctx.audit().updated(entity_type="Cart", entity_id=str(cart_id), before={}, after={"status": "saved"})
        self._ctx.invalidate_cart_cache()
        return saved


class ArchiveCart:
    def __init__(self, repo: CartRepository, ctx: CartServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, cart_id: uuid.UUID) -> Cart:
        cart = self._repo.get_by_id(cart_id)
        if cart is None:
            raise ResourceNotFound("Cart not found.")
        event = cart.archive()
        saved = self._repo.save(cart)
        self._ctx.stage_events([("CartArchivedEvent", event.to_payload())])
        self._ctx.audit().updated(entity_type="Cart", entity_id=str(cart_id), before={}, after={"status": "archived"})
        self._ctx.invalidate_cart_cache()
        return saved


class ExpireCart:
    def __init__(self, repo: CartRepository, ctx: CartServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, cart_id: uuid.UUID) -> Cart:
        cart = self._repo.get_by_id(cart_id)
        if cart is None:
            raise ResourceNotFound("Cart not found.")
        event = cart.expire(django_timezone.now())
        saved = self._repo.save(cart)
        self._ctx.stage_events([("CartExpiredEvent", event.to_payload())])
        self._ctx.audit().updated(entity_type="Cart", entity_id=str(cart_id), before={}, after={"status": "expired"})
        self._ctx.invalidate_cart_cache()
        self._ctx.metric("carts_expired_total")
        return saved


class RestoreCart:
    def __init__(self, repo: CartRepository, ctx: CartServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, cart_id: uuid.UUID) -> Cart:
        cart = self._repo.get_by_id(cart_id)
        if cart is None:
            raise ResourceNotFound("Cart not found.")
        event = cart.restore()
        saved = self._repo.save(cart)
        self._ctx.stage_events([("CartRestored", event.to_payload())])
        self._ctx.audit().updated(entity_type="Cart", entity_id=str(cart_id), before={}, after={"status": "active"})
        self._ctx.invalidate_cart_cache()
        return saved


class LockCart:
    """
    Added during Phase 3 (Interfaces) as a minimum-necessary fix --
    `POST /cart/{code}/lock/` is a required endpoint with no backing
    Application Service in Phase 1's original set, and the view layer
    cannot legally call `Cart.lock()` directly (that would be business
    logic in the view, which this phase's own rules forbid). See the
    Phase 3 certification report for the full explanation.
    """

    def __init__(self, repo: CartRepository, ctx: CartServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, cart_id: uuid.UUID, reason: str) -> Cart:
        from apps.cart.domain.enums import CartLockReason

        cart = self._repo.get_by_id(cart_id)
        if cart is None:
            raise ResourceNotFound("Cart not found.")
        event = cart.lock(CartLockReason(reason))
        saved = self._repo.save(cart)
        self._ctx.stage_events([("CartLockedEvent", event.to_payload())])
        self._ctx.audit().updated(entity_type="Cart", entity_id=str(cart_id), before={}, after={"lock_reason": reason})
        self._ctx.invalidate_cart_cache()
        return saved


class UnlockCart:
    """Same rationale as `LockCart` above -- added during Phase 3 as a minimum-necessary fix."""

    def __init__(self, repo: CartRepository, ctx: CartServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, cart_id: uuid.UUID) -> Cart:
        cart = self._repo.get_by_id(cart_id)
        if cart is None:
            raise ResourceNotFound("Cart not found.")
        event = cart.unlock()
        saved = self._repo.save(cart)
        self._ctx.stage_events([("CartUnlocked", event.to_payload())])
        self._ctx.audit().updated(entity_type="Cart", entity_id=str(cart_id), before={}, after={"lock_reason": None})
        self._ctx.invalidate_cart_cache()
        return saved


class UpdateCartDetails:
    """
    Added during Phase 3 (Interfaces) for the same reason as `LockCart`/
    `UnlockCart` above -- `PATCH /cart/{code}/` (note/gift_message) has
    no backing Application Service in Phase 1's original set, and a
    view cannot legally construct `CartNote`/`GiftMessage` value
    objects and mutate the aggregate directly. This has no domain
    event of its own (note/gift_message changes are not part of
    Phase 1's original 22-event catalogue) -- it still audits and
    invalidates cache like every other mutation, it simply doesn't
    stage an Outbox event for a field change nothing else in the
    platform currently needs to react to asynchronously.
    """

    def __init__(self, repo: CartRepository, ctx: CartServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, cart_id: uuid.UUID, note: str | None = None, gift_message: str | None = None) -> Cart:
        from apps.cart.domain.value_objects import CartNote, GiftMessage

        cart = self._repo.get_by_id(cart_id)
        if cart is None:
            raise ResourceNotFound("Cart not found.")

        if note is not None:
            cart.note = CartNote(note) if note else None
        if gift_message is not None:
            cart.gift_message = GiftMessage(gift_message) if gift_message else None

        saved = self._repo.save(cart)
        self._ctx.audit().updated(entity_type="Cart", entity_id=str(cart_id), before={}, after={"note_changed": note is not None, "gift_message_changed": gift_message is not None})
        self._ctx.invalidate_cart_cache()
        return saved
