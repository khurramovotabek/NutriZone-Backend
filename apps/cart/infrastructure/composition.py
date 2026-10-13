"""
Composition root for the `cart` module's interfaces layer.

Wires concrete `infrastructure/` implementations into `application/
services/` constructors -- matching every prior module's composition
root exactly. No service locator: every `build_*()` factory explicitly
constructs and returns one fully-wired object.
"""
from __future__ import annotations

import uuid

from apps.cart.application.selectors import CartSelector as ApplicationCartSelector
from apps.cart.application.services._shared import CartServiceContext
from apps.cart.application.services.items import AddItem, BulkUpdateItems, ClearCart, RemoveItem, UpdateQuantity
from apps.cart.application.services.lifecycle import ArchiveCart, CreateCart, ExpireCart, LoadCart, LockCart, RestoreCart, SaveCart, UnlockCart, UpdateCartDetails
from apps.cart.application.services.merge_and_ownership import AssignCustomer, MergeGuestCart
from apps.cart.application.services.pricing_recalculation import RecalculateCartPricing
from apps.cart.application.services.queries import AdminListCarts, GetCart, GetSnapshotHistory, ListCustomerCarts, SearchCart
from apps.cart.application.services.references import (
    ApplyCouponReference, ApplyCouponToCartWithoutRepricing, AttachPriceSnapshot, AttachReservation, DetachPriceSnapshot, DetachReservation, RemoveCouponReference,
)
from apps.cart.application.services.snapshots_and_validation import (
    CalculateCheckoutReadiness, CreateSnapshot, RestoreSnapshot, ValidateCart,
)
from apps.cart.infrastructure import models as orm
from apps.cart.infrastructure.repositories import DjangoCartRepository
from apps.cart.infrastructure.selectors import DjangoCartSearchBackend
from core.outbox import stage_event


def stage_cart_events(events: list[tuple[str, dict]]) -> None:
    for event_type, payload in events:
        stage_event(orm.CartOutboxEvent, event_type, payload)


def build_cart_service_context(actor_id: uuid.UUID | None = None) -> CartServiceContext:
    return CartServiceContext(stage_events=stage_cart_events, actor_id=actor_id)


def build_cart_repository() -> DjangoCartRepository:
    """Also directly exposed so no future Interfaces-layer view has any reason to instantiate one directly -- the fix already applied pre-emptively in every module's infra phase since Store."""
    return DjangoCartRepository()


def build_cart_selector() -> ApplicationCartSelector:
    return ApplicationCartSelector(DjangoCartSearchBackend())


# --- Lifecycle -------------------------------------------------------

def build_create_cart(actor_id=None) -> CreateCart:
    return CreateCart(DjangoCartRepository(), build_cart_service_context(actor_id))


def build_load_cart() -> LoadCart:
    return LoadCart(DjangoCartRepository())


def build_save_cart(actor_id=None) -> SaveCart:
    return SaveCart(DjangoCartRepository(), build_cart_service_context(actor_id))


def build_archive_cart(actor_id=None) -> ArchiveCart:
    return ArchiveCart(DjangoCartRepository(), build_cart_service_context(actor_id))


def build_expire_cart(actor_id=None) -> ExpireCart:
    return ExpireCart(DjangoCartRepository(), build_cart_service_context(actor_id))


def build_restore_cart(actor_id=None) -> RestoreCart:
    return RestoreCart(DjangoCartRepository(), build_cart_service_context(actor_id))


def build_lock_cart(actor_id=None) -> LockCart:
    return LockCart(DjangoCartRepository(), build_cart_service_context(actor_id))


def build_unlock_cart(actor_id=None) -> UnlockCart:
    return UnlockCart(DjangoCartRepository(), build_cart_service_context(actor_id))


def build_update_cart_details(actor_id=None) -> UpdateCartDetails:
    return UpdateCartDetails(DjangoCartRepository(), build_cart_service_context(actor_id))


# --- Items --------------------------------------------------------------

def build_add_item(actor_id=None) -> AddItem:
    return AddItem(DjangoCartRepository(), build_cart_service_context(actor_id))


def build_remove_item(actor_id=None) -> RemoveItem:
    return RemoveItem(DjangoCartRepository(), build_cart_service_context(actor_id))


def build_update_quantity(actor_id=None) -> UpdateQuantity:
    return UpdateQuantity(DjangoCartRepository(), build_cart_service_context(actor_id))


def build_bulk_update_items(actor_id=None) -> BulkUpdateItems:
    return BulkUpdateItems(DjangoCartRepository(), build_cart_service_context(actor_id))


def build_clear_cart(actor_id=None) -> ClearCart:
    return ClearCart(DjangoCartRepository(), build_cart_service_context(actor_id))


# --- References -----------------------------------------------------

def build_apply_coupon_reference(actor_id=None) -> ApplyCouponReference:
    return ApplyCouponReference(DjangoCartRepository(), build_cart_service_context(actor_id))


def build_apply_coupon_to_cart_without_repricing(actor_id=None) -> ApplyCouponToCartWithoutRepricing:
    return ApplyCouponToCartWithoutRepricing(DjangoCartRepository(), build_cart_service_context(actor_id))


def build_remove_coupon_reference(actor_id=None) -> RemoveCouponReference:
    return RemoveCouponReference(DjangoCartRepository(), build_cart_service_context(actor_id))


def build_attach_price_snapshot(actor_id=None) -> AttachPriceSnapshot:
    return AttachPriceSnapshot(DjangoCartRepository(), build_cart_service_context(actor_id))


def build_recalculate_cart_pricing(actor_id=None) -> RecalculateCartPricing:
    return RecalculateCartPricing(DjangoCartRepository(), build_cart_service_context(actor_id))


def build_detach_price_snapshot(actor_id=None) -> DetachPriceSnapshot:
    return DetachPriceSnapshot(DjangoCartRepository(), build_cart_service_context(actor_id))


def build_attach_reservation(actor_id=None) -> AttachReservation:
    return AttachReservation(DjangoCartRepository(), build_cart_service_context(actor_id))


def build_detach_reservation(actor_id=None) -> DetachReservation:
    return DetachReservation(DjangoCartRepository(), build_cart_service_context(actor_id))


# --- Merge / Ownership -------------------------------------------------

def build_assign_customer(actor_id=None) -> AssignCustomer:
    return AssignCustomer(DjangoCartRepository(), build_cart_service_context(actor_id))


def build_merge_guest_cart(actor_id=None) -> MergeGuestCart:
    return MergeGuestCart(DjangoCartRepository(), build_cart_service_context(actor_id))


# --- Snapshots / Validation ---------------------------------------------

def build_create_snapshot(actor_id=None) -> CreateSnapshot:
    return CreateSnapshot(DjangoCartRepository(), build_cart_service_context(actor_id))


def build_restore_snapshot(actor_id=None) -> RestoreSnapshot:
    return RestoreSnapshot(DjangoCartRepository(), build_cart_service_context(actor_id))


def build_validate_cart() -> ValidateCart:
    return ValidateCart(DjangoCartRepository())


def build_calculate_checkout_readiness() -> CalculateCheckoutReadiness:
    return CalculateCheckoutReadiness(DjangoCartRepository())


# --- Queries --------------------------------------------------------------

def build_get_cart() -> GetCart:
    return GetCart(DjangoCartRepository())


def build_list_customer_carts() -> ListCustomerCarts:
    return ListCustomerCarts(DjangoCartRepository())


def build_admin_list_carts() -> AdminListCarts:
    return AdminListCarts(DjangoCartRepository())


def build_search_cart() -> SearchCart:
    return SearchCart(DjangoCartSearchBackend())


def build_get_snapshot_history() -> GetSnapshotHistory:
    return GetSnapshotHistory(DjangoCartRepository())
