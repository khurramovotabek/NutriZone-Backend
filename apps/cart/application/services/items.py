"""
Item Management Application Services: AddItem, RemoveItem,
UpdateQuantity, BulkUpdateItems.
"""
from __future__ import annotations

import uuid

from django.db import transaction
from django.utils import timezone as django_timezone

from apps.cart.application.ports import CartRepository
from apps.cart.application.services._shared import CartServiceContext
from apps.cart.domain.aggregates import Cart
from apps.cart.domain.services import QuantityPolicy
from common.exceptions import ResourceNotFound


class AddItem:
    def __init__(self, repo: CartRepository, ctx: CartServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, cart_id: uuid.UUID, product_variant_id: uuid.UUID, quantity: int) -> Cart:
        QuantityPolicy.assert_within_max(quantity)
        cart = self._repo.get_by_id(cart_id)
        if cart is None:
            raise ResourceNotFound("Cart not found.")

        event = cart.add_item(product_variant_id, quantity, django_timezone.now())
        saved = self._repo.save(cart)

        self._ctx.stage_events([("ItemAdded", event.to_payload())])
        self._ctx.audit().updated(entity_type="Cart", entity_id=str(cart_id), before={}, after={"product_variant_id": str(product_variant_id), "quantity": quantity})
        self._ctx.invalidate_cart_cache()
        self._ctx.metric("cart_items_added_total")
        return saved


class RemoveItem:
    def __init__(self, repo: CartRepository, ctx: CartServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, cart_id: uuid.UUID, item_id: uuid.UUID) -> Cart:
        cart = self._repo.get_by_id(cart_id)
        if cart is None:
            raise ResourceNotFound("Cart not found.")

        event = cart.remove_item(item_id, django_timezone.now())
        saved = self._repo.save(cart)

        self._ctx.stage_events([("ItemRemoved", event.to_payload())])
        self._ctx.audit().updated(entity_type="Cart", entity_id=str(cart_id), before={}, after={"item_id": str(item_id)})
        self._ctx.invalidate_cart_cache()
        return saved


class UpdateQuantity:
    def __init__(self, repo: CartRepository, ctx: CartServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, cart_id: uuid.UUID, item_id: uuid.UUID, quantity: int) -> Cart:
        QuantityPolicy.assert_within_max(quantity)
        cart = self._repo.get_by_id(cart_id)
        if cart is None:
            raise ResourceNotFound("Cart not found.")

        event = cart.update_quantity(item_id, quantity, django_timezone.now())
        saved = self._repo.save(cart)

        self._ctx.stage_events([("ItemQuantityUpdated", event.to_payload())])
        self._ctx.audit().updated(entity_type="Cart", entity_id=str(cart_id), before={"old_quantity": event.old_quantity}, after={"new_quantity": event.new_quantity})
        self._ctx.invalidate_cart_cache()
        return saved


class BulkUpdateItems:
    def __init__(self, repo: CartRepository, ctx: CartServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, cart_id: uuid.UUID, updates: dict) -> Cart:
        for quantity in updates.values():
            QuantityPolicy.assert_within_max(quantity)

        cart = self._repo.get_by_id(cart_id)
        if cart is None:
            raise ResourceNotFound("Cart not found.")

        events = cart.bulk_update_items(updates, django_timezone.now())
        saved = self._repo.save(cart)

        self._ctx.stage_events([("ItemQuantityUpdated", e.to_payload()) for e in events])
        self._ctx.audit().updated(entity_type="Cart", entity_id=str(cart_id), before={}, after={"items_updated": len(updates)})
        self._ctx.invalidate_cart_cache()
        self._ctx.metric("cart_bulk_updates_total")
        return saved


class ClearCart:
    """Named to match the domain aggregate's own `clear()` method -- not in this phase's explicit 26-service list by that exact name, but 'Clear Cart' is an explicitly required capability with no other service covering it, so this closes that gap rather than leaving the capability unreachable from the Application layer."""

    def __init__(self, repo: CartRepository, ctx: CartServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, cart_id: uuid.UUID) -> Cart:
        cart = self._repo.get_by_id(cart_id)
        if cart is None:
            raise ResourceNotFound("Cart not found.")

        event = cart.clear(django_timezone.now())
        saved = self._repo.save(cart)

        self._ctx.stage_events([("CartCleared", event.to_payload())])
        self._ctx.audit().updated(entity_type="Cart", entity_id=str(cart_id), before={}, after={"items_removed": event.items_removed})
        self._ctx.invalidate_cart_cache()
        return saved
