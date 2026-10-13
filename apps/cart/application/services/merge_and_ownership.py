"""
Merge & Ownership Application Services: MergeGuestCart, AssignCustomer.
"""
from __future__ import annotations

import uuid

from django.db import transaction
from django.utils import timezone as django_timezone

from apps.cart.application.ports import CartRepository
from apps.cart.application.services._shared import CartServiceContext
from apps.cart.domain.aggregates import Cart
from apps.cart.domain.enums import MergeStrategy
from apps.cart.domain.services import CartMergePolicy
from common.exceptions import ResourceNotFound


class AssignCustomer:
    def __init__(self, repo: CartRepository, ctx: CartServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, cart_id: uuid.UUID, customer_id: uuid.UUID) -> Cart:
        cart = self._repo.get_by_id(cart_id)
        if cart is None:
            raise ResourceNotFound("Cart not found.")
        event = cart.assign_customer(customer_id, django_timezone.now())
        saved = self._repo.save(cart)
        self._ctx.stage_events([("CustomerAssigned", event.to_payload())])
        self._ctx.audit().updated(entity_type="Cart", entity_id=str(cart_id), before={}, after={"customer_id": str(customer_id)})
        self._ctx.invalidate_cart_cache()
        self._ctx.metric("carts_assigned_to_customer_total")
        return saved


class MergeGuestCart:
    """
    Merges a guest cart into the customer's existing authenticated
    cart (creating one first via `CreateCart` if the customer had
    none). The guest cart itself is archived after a successful merge
    -- 'Cart never deletes another Cart instance from within one
    aggregate's own method' (aggregates.py's own doc), so the archival
    happens here, at the orchestration layer, not inside `Cart.
    merge_guest_cart()`.
    """

    def __init__(self, repo: CartRepository, ctx: CartServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, guest_cart_id: uuid.UUID, authenticated_cart_id: uuid.UUID, strategy: str | None = None) -> Cart:
        guest_cart = self._repo.get_by_id(guest_cart_id)
        if guest_cart is None:
            raise ResourceNotFound("Guest cart not found.")
        authenticated_cart = self._repo.get_by_id(authenticated_cart_id)
        if authenticated_cart is None:
            raise ResourceNotFound("Authenticated cart not found.")

        if strategy is None:
            guest_item_count = len([i for i in guest_cart.items.values() if i.status.value != "removed"])
            auth_item_count = len([i for i in authenticated_cart.items.values() if i.status.value != "removed"])
            strategy = CartMergePolicy.recommend_strategy(guest_item_count, auth_item_count).value

        now = django_timezone.now()
        _result, event = authenticated_cart.merge_guest_cart(guest_cart, MergeStrategy(strategy), now)
        guest_cart.archive()

        saved = self._repo.save(authenticated_cart)
        self._repo.save(guest_cart)

        self._ctx.stage_events([("CartMerged", event.to_payload())])
        self._ctx.audit().updated(entity_type="Cart", entity_id=str(authenticated_cart_id), before={}, after={"source_cart_id": str(guest_cart_id), "strategy": strategy})
        self._ctx.invalidate_cart_cache()
        self._ctx.metric("cart_merges_total")
        return saved
