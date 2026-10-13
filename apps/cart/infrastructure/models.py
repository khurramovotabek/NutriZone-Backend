"""
Cart ORM models.

Mirrors Phase 1's single `Cart` aggregate plus its owned entities.
`CartValidationIssue` has NO table -- its own Phase 1 docstring is
explicit that it's computed fresh on demand, never persisted;
`PriceReference`/`InventoryReservationReference` are singular
(at-most-one-per-item) value holders, modeled here as their own
OneToOne tables (matching this phase's explicit "PriceSnapshotReference"/
"AttachedReservation" naming) rather than flattened columns on
CartItemModel, so each has a clean, independently-queryable identity.

Cross-module references (CartItemModel.product_variant_id ->
products.ProductVariant, PriceSnapshotReferenceModel.price_snapshot_id
-> pricing.PriceSnapshot, AttachedReservationModel.reservation_id ->
inventory.Reservation, CartModel.customer_id -> identity.User) are
plain UUIDField columns, never a ForeignKey across schemas -- the same
modular-monolith rule already applied consistently in every prior
module.
"""
from __future__ import annotations

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.cart.domain.enums import (
    CartItemStatus,
    CartLockReason,
    CartSource,
    CartStatus,
    CartType,
)
from common.models import AllObjectsManager, BaseModel
from common.utils import enum_field_kwargs
from core.outbox import AbstractOutboxEvent


class CartModel(BaseModel):
    code = models.CharField(max_length=24, unique=True, db_index=True)
    token = models.UUIDField(unique=True, db_index=True, default=uuid.uuid4)
    version = models.PositiveIntegerField(default=1)
    currency = models.CharField(max_length=3, default="UZS")
    cart_type = models.CharField(default=CartType.GUEST.value, db_index=True, **enum_field_kwargs(CartType))
    source = models.CharField(default=CartSource.WEB.value, **enum_field_kwargs(CartSource))
    status = models.CharField(default=CartStatus.ACTIVE.value, db_index=True, **enum_field_kwargs(CartStatus))
    region = models.CharField(max_length=16, null=True, blank=True)
    channel = models.CharField(max_length=32, null=True, blank=True)
    customer_id = models.UUIDField(null=True, blank=True, db_index=True)
    coupon_ids = models.JSONField(default=list, blank=True)
    promotion_ids = models.JSONField(default=list, blank=True)
    note = models.TextField(null=True, blank=True)
    gift_message = models.CharField(max_length=500, null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    lock_reason = models.CharField(null=True, blank=True, **enum_field_kwargs(CartLockReason))
    # Shipping/Tax estimates are singular, at-most-one-per-cart references -- embedded directly rather than
    # given their own tables, unlike the per-item PriceSnapshotReference/AttachedReservation (which are
    # explicitly named as expected persistence in this phase's brief and are genuinely per-line-item).
    shipping_estimate_id = models.UUIDField(null=True, blank=True)
    shipping_estimated_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    shipping_estimated_currency = models.CharField(max_length=3, null=True, blank=True)
    shipping_estimate_is_final = models.BooleanField(default=False)
    shipping_estimated_at = models.DateTimeField(null=True, blank=True)
    tax_estimate_id = models.UUIDField(null=True, blank=True)
    tax_estimated_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    tax_estimated_currency = models.CharField(max_length=3, null=True, blank=True)
    tax_estimate_is_final = models.BooleanField(default=False)
    tax_estimated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "cart_carts"
        verbose_name=_("Cart")
        verbose_name_plural = _("Carts")
        indexes = [models.Index(fields=["status", "cart_type"]), models.Index(fields=["customer_id", "status"])]
        constraints = [models.CheckConstraint(condition=models.Q(version__gte=1), name="ck_carts_version_at_least_one")]

    def __str__(self) -> str:  # pragma: no cover
        return self.code


class CartItemModel(BaseModel):
    cart = models.ForeignKey(CartModel, on_delete=models.CASCADE, related_name="items")
    product_variant_id = models.UUIDField(db_index=True)
    quantity = models.PositiveIntegerField()
    status = models.CharField(default=CartItemStatus.ACTIVE.value, db_index=True, **enum_field_kwargs(CartItemStatus))
    note = models.TextField(null=True, blank=True)
    added_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "cart_items"
        verbose_name=_("Cart Item")
        verbose_name_plural = _("Cart Items")
        indexes = [models.Index(fields=["cart", "status"]), models.Index(fields=["product_variant_id"])]
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gte=0), name="ck_cart_items_quantity_non_negative")]


class PriceSnapshotReferenceModel(models.Model):
    """OneToOne with CartItem -- 'Applied Price Snapshot' / this phase's explicit 'PriceSnapshotReference' persistence expectation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    item = models.OneToOneField(CartItemModel, on_delete=models.CASCADE, related_name="price_reference")
    price_snapshot_id = models.UUIDField(db_index=True)
    unit_amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3)
    applied_at = models.DateTimeField()

    objects = AllObjectsManager()

    class Meta:
        db_table = "cart_price_snapshot_references"
        verbose_name = _("Price snapshot")
        verbose_name_plural = _("Price snapshots")
        constraints = [models.CheckConstraint(condition=models.Q(unit_amount__gte=0), name="ck_price_snapshot_refs_amount_non_negative")]


class AttachedReservationModel(models.Model):
    """OneToOne with CartItem -- 'Inventory Reservation Reference' / this phase's explicit 'AttachedReservation' persistence expectation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    item = models.OneToOneField(CartItemModel, on_delete=models.CASCADE, related_name="reservation_reference")
    reservation_id = models.UUIDField(db_index=True)
    reserved_at = models.DateTimeField()
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = AllObjectsManager()

    class Meta:
        db_table = "cart_attached_reservations"
        verbose_name = _("Cart reservation")
        verbose_name_plural = _("Cart reservations")


class CartSnapshotModel(models.Model):
    """Append-only -- no update path is exposed by its repository, backing 'Cart Snapshot'/'Cart Versioning'."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    cart = models.ForeignKey(CartModel, on_delete=models.CASCADE, related_name="snapshots")
    token = models.UUIDField(unique=True, db_index=True)
    version_at_capture = models.PositiveIntegerField()
    captured_at = models.DateTimeField(db_index=True)
    items_snapshot = models.JSONField(default=list)

    objects = AllObjectsManager()

    class Meta:
        db_table = "cart_snapshots"
        verbose_name = _("Cart snapshot")
        verbose_name_plural = _("Cart snapshots")
        indexes = [models.Index(fields=["cart", "captured_at"])]


class CartAuditEntryModel(models.Model):
    """Append-only -- 'Cart Audit Events' as a queryable, same-aggregate timeline (distinct from the Outbox-published events below, which are for cross-module/async consumption)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    cart = models.ForeignKey(CartModel, on_delete=models.CASCADE, related_name="audit_entries")
    action = models.CharField(max_length=64)
    actor_id = models.UUIDField(null=True, blank=True)
    occurred_at = models.DateTimeField(db_index=True)
    details = models.JSONField(default=dict, blank=True)

    objects = AllObjectsManager()

    class Meta:
        db_table = "cart_audit_entries"
        verbose_name = _("Cart history entry")
        verbose_name_plural = _("Cart history")
        indexes = [models.Index(fields=["cart", "occurred_at"])]


class CartOutboxEvent(AbstractOutboxEvent):
    class Meta:
        db_table = "cart_outbox_events"
        ordering = ["created_at"]
