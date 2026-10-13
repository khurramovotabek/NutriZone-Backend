"""
Snapshot & Validation Application Services: CreateSnapshot,
RestoreSnapshot, ValidateCart, CalculateCheckoutReadiness.
"""
from __future__ import annotations

import uuid

from django.db import transaction
from django.utils import timezone as django_timezone

from apps.cart.application.ports import CartRepository
from apps.cart.application.services._shared import CartServiceContext
from apps.cart.domain.enums import CartItemStatus
from apps.cart.domain.services import CartValidationPolicy, CheckoutReadinessPolicy, SnapshotPolicy
from common.exceptions import ResourceNotFound


class CreateSnapshot:
    def __init__(self, repo: CartRepository, ctx: CartServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, cart_id: uuid.UUID):
        cart = self._repo.get_by_id(cart_id)
        if cart is None:
            raise ResourceNotFound("Cart not found.")

        if not SnapshotPolicy.can_add_snapshot(len(cart.snapshots)):
            oldest_id = SnapshotPolicy.oldest_snapshot_id_to_prune([(s.id, s.captured_at) for s in cart.snapshots.values()])
            if oldest_id is not None:
                cart.snapshots.pop(oldest_id, None)

        snapshot, event = cart.create_snapshot(django_timezone.now())
        self._repo.save(cart)

        self._ctx.stage_events([("CartSnapshotCreated", event.to_payload())])
        self._ctx.audit().created(entity_type="CartSnapshot", entity_id=str(snapshot.id), after={"cart_id": str(cart_id)})
        self._ctx.metric("cart_snapshots_created_total")
        return snapshot


class RestoreSnapshot:
    def __init__(self, repo: CartRepository, ctx: CartServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, cart_id: uuid.UUID, snapshot_id: uuid.UUID):
        cart = self._repo.get_by_id(cart_id)
        if cart is None:
            raise ResourceNotFound("Cart not found.")

        event = cart.restore_snapshot(snapshot_id, django_timezone.now())
        saved = self._repo.save(cart)

        self._ctx.stage_events([("CartSnapshotRestored", event.to_payload())])
        self._ctx.audit().updated(entity_type="Cart", entity_id=str(cart_id), before={}, after={"snapshot_id": str(snapshot_id)})
        self._ctx.invalidate_cart_cache()
        return saved


class ValidateCart:
    def __init__(self, repo: CartRepository) -> None:
        self._repo = repo

    def execute(self, cart_id: uuid.UUID) -> list:
        cart = self._repo.get_by_id(cart_id)
        if cart is None:
            raise ResourceNotFound("Cart not found.")

        is_expired = cart.status.value == "expired"
        is_locked = cart.lock_reason is not None
        return CartValidationPolicy.validate(list(cart.items.values()), is_locked, is_expired, cart.currency.value)


class CalculateCheckoutReadiness:
    def __init__(self, repo: CartRepository) -> None:
        self._repo = repo

    def execute(self, cart_id: uuid.UUID, all_reservations_valid: bool = True) -> str:
        cart = self._repo.get_by_id(cart_id)
        if cart is None:
            raise ResourceNotFound("Cart not found.")

        structural = cart.structural_checkout_readiness()
        is_expired = cart.status.value == "expired"
        is_locked = cart.lock_reason is not None
        issues = CartValidationPolicy.validate(list(cart.items.values()), is_locked, is_expired, cart.currency.value)
        readiness = CheckoutReadinessPolicy.evaluate(structural, all_reservations_valid, issues)
        return readiness.value
