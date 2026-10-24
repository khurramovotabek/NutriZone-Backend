"""
Ordering ORM models.

Mirrors Phase 1's 3 aggregates (Order, OrderReturn, OrderCancellation)
plus their 8 owned entities exactly -- 11 base tables + 1 Outbox
table. Infrastructure adapts to Domain, never the reverse.

Cross-module references (OrderModel.customer_id, .cart_id,
OrderLineItemModel.product_variant_id/.price_snapshot_id/
.reservation_id, OrderPaymentReferenceModel.payment_id,
OrderFulfillmentReferenceModel.fulfillment_id) are plain UUIDField
columns, never a ForeignKey across schemas -- the same modular-
monolith rule already applied consistently in every prior module.
"""
from __future__ import annotations

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.ordering.domain.enums import (
    CancellationReason, CancellationStatus, FulfillmentReferenceStatus, InvoiceStatus, OrderChannel,
    OrderLineItemStatus, OrderLockReason, OrderStatus, OrderType, PaymentReferenceStatus, ReturnReason, ReturnStatus,
)
from common.models import AllObjectsManager, BaseModel
from common.utils import enum_field_kwargs
from core.outbox import AbstractOutboxEvent


class OrderModel(BaseModel):
    order_number = models.CharField(max_length=30, unique=True, db_index=True)
    customer_id = models.UUIDField(null=True, blank=True, db_index=True)
    cart_id = models.UUIDField(null=True, blank=True, db_index=True)
    currency = models.CharField(max_length=3, default="UZS")
    order_type = models.CharField(default=OrderType.STANDARD.value, **enum_field_kwargs(OrderType))
    channel = models.CharField(default=OrderChannel.WEB.value, **enum_field_kwargs(OrderChannel))
    status = models.CharField(default=OrderStatus.DRAFT.value, db_index=True, **enum_field_kwargs(OrderStatus))
    version = models.PositiveIntegerField(default=1)
    lock_reason = models.CharField(null=True, blank=True, **enum_field_kwargs(OrderLockReason))
    is_archived = models.BooleanField(default=False, db_index=True)
    coupon_ids = models.JSONField(default=list, blank=True)
    promotion_ids = models.JSONField(default=list, blank=True)
    note = models.TextField(null=True, blank=True)
    customer_comment = models.TextField(null=True, blank=True)
    placed_at = models.DateTimeField(null=True, blank=True)
    # Delivery or pickup, and the branch that handles the order (the pickup branch, or a branch the dispatcher
    # assigned a delivery to). That branch's owner sees and moves the order from the storefront store dashboard.
    # Not part of the Order aggregate: written by checkout / the assignment service (stores/infrastructure/store_orders.py).
    fulfilment_method = models.CharField(max_length=10, default="delivery", db_index=True, choices=[("delivery", "Yetkazib berish"), ("pickup", "Olib ketish")])
    fulfilment_store_id = models.UUIDField(null=True, blank=True, db_index=True)
    store_assigned_at = models.DateTimeField(null=True, blank=True)
    # Address snapshots -- frozen copies, embedded directly (never a ForeignKey to geo.Address).
    shipping_recipient_name = models.CharField(max_length=255)
    shipping_line1 = models.CharField(max_length=255)
    shipping_line2 = models.CharField(max_length=255, null=True, blank=True)
    shipping_city = models.CharField(max_length=120)
    shipping_region = models.CharField(max_length=120, null=True, blank=True)
    shipping_postal_code = models.CharField(max_length=32, null=True, blank=True)
    shipping_country_code = models.CharField(max_length=2)
    shipping_phone = models.CharField(max_length=32, null=True, blank=True)
    shipping_latitude = models.FloatField(null=True, blank=True)
    shipping_longitude = models.FloatField(null=True, blank=True)
    billing_recipient_name = models.CharField(max_length=255)
    billing_line1 = models.CharField(max_length=255)
    billing_line2 = models.CharField(max_length=255, null=True, blank=True)
    billing_city = models.CharField(max_length=120)
    billing_region = models.CharField(max_length=120, null=True, blank=True)
    billing_postal_code = models.CharField(max_length=32, null=True, blank=True)
    billing_country_code = models.CharField(max_length=2)
    billing_phone = models.CharField(max_length=32, null=True, blank=True)
    billing_latitude = models.FloatField(null=True, blank=True)
    billing_longitude = models.FloatField(null=True, blank=True)
    # Invoice (0-or-1 per order) -- embedded directly rather than a separate table, since it's a
    # singular, at-most-one owned entity (unlike line items, which are a genuine collection).
    invoice_id = models.UUIDField(null=True, blank=True)
    invoice_number = models.CharField(max_length=32, null=True, blank=True)
    invoice_total_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    invoice_status = models.CharField(null=True, blank=True, **enum_field_kwargs(InvoiceStatus))
    invoice_issued_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ordering_orders"
        verbose_name = _("Order")
        verbose_name_plural = _("Orders")
        indexes = [models.Index(fields=["status", "customer_id"]), models.Index(fields=["is_archived", "status"])]
        constraints = [models.CheckConstraint(condition=models.Q(version__gte=1), name="ck_orders_version_at_least_one")]

    def __str__(self) -> str:  # pragma: no cover
        return self.order_number


class OrderLineItemModel(BaseModel):
    order = models.ForeignKey(OrderModel, on_delete=models.CASCADE, related_name="lines")
    product_variant_id = models.UUIDField(db_index=True)
    quantity = models.PositiveIntegerField()
    unit_price_amount = models.DecimalField(max_digits=14, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(default=OrderLineItemStatus.ACTIVE.value, db_index=True, **enum_field_kwargs(OrderLineItemStatus))
    price_snapshot_id = models.UUIDField(null=True, blank=True)
    reservation_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "ordering_order_lines"
        verbose_name = _("Order Line Item")
        verbose_name_plural = _("Order Line Items")
        indexes = [models.Index(fields=["order", "status"])]
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0), name="ck_order_lines_quantity_positive")]


class OrderStatusHistoryEntryModel(models.Model):
    """Append-only -- no update/delete path exposed, mirroring `apps.pricing`'s `PriceHistoryEntryModel`."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    order = models.ForeignKey(OrderModel, on_delete=models.CASCADE, related_name="status_history")
    from_status = models.CharField(max_length=32, null=True, blank=True)
    to_status = models.CharField(max_length=32)
    reason = models.TextField(null=True, blank=True)
    changed_at = models.DateTimeField(db_index=True)
    actor_id = models.UUIDField(null=True, blank=True)

    objects = AllObjectsManager()

    class Meta:
        db_table = "ordering_order_status_history"
        indexes = [models.Index(fields=["order", "changed_at"])]


class OrderPaymentReferenceModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    order = models.ForeignKey(OrderModel, on_delete=models.CASCADE, related_name="payment_references")
    payment_id = models.UUIDField(db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(default=PaymentReferenceStatus.PENDING.value, **enum_field_kwargs(PaymentReferenceStatus))
    processed_at = models.DateTimeField(null=True, blank=True)

    objects = AllObjectsManager()

    class Meta:
        db_table = "ordering_order_payment_references"
        constraints = [models.CheckConstraint(condition=models.Q(amount__gte=0), name="ck_order_payment_refs_amount_non_negative")]


class OrderFulfillmentReferenceModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    order = models.ForeignKey(OrderModel, on_delete=models.CASCADE, related_name="fulfillment_references")
    fulfillment_id = models.UUIDField(db_index=True)
    status = models.CharField(default=FulfillmentReferenceStatus.PENDING.value, **enum_field_kwargs(FulfillmentReferenceStatus))
    tracking_number = models.CharField(max_length=32, null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    objects = AllObjectsManager()

    class Meta:
        db_table = "ordering_order_fulfillment_references"


class OrderFailureModel(models.Model):
    """Append-only -- a structured record of a failed checkout attempt."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    order = models.ForeignKey(OrderModel, on_delete=models.CASCADE, related_name="failures")
    reason = models.CharField(max_length=32)
    detail = models.TextField()
    occurred_at = models.DateTimeField(db_index=True)

    objects = AllObjectsManager()

    class Meta:
        db_table = "ordering_order_failures"


class OrderReturnModel(BaseModel):
    return_number = models.CharField(max_length=30, unique=True, db_index=True)
    order_id = models.UUIDField(db_index=True)
    status = models.CharField(default=ReturnStatus.REQUESTED.value, db_index=True, **enum_field_kwargs(ReturnStatus))
    reason = models.CharField(default=ReturnReason.OTHER.value, **enum_field_kwargs(ReturnReason))
    refund_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    refund_currency = models.CharField(max_length=3, null=True, blank=True)
    requested_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    # Staff-facing: why it was rejected, what was found on receipt, etc. Not part of the domain aggregate (the repository never overwrites it).
    note = models.TextField(blank=True, default="")
    # Customer-facing: the reason given when the request was rejected (shown on the order page and in the notification).
    rejection_reason = models.TextField(blank=True, default="")

    class Meta:
        db_table = "ordering_returns"
        verbose_name = _("Order Return")
        verbose_name_plural = _("Order Returns")
        indexes = [models.Index(fields=["order_id", "status"])]


class ReturnLineItemModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    order_return = models.ForeignKey(OrderReturnModel, on_delete=models.CASCADE, related_name="lines")
    order_line_item_id = models.UUIDField(db_index=True)
    quantity = models.PositiveIntegerField()

    objects = AllObjectsManager()

    class Meta:
        db_table = "ordering_return_lines"
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0), name="ck_return_lines_quantity_positive")]


class OrderCancellationModel(BaseModel):
    order_id = models.UUIDField(db_index=True)
    status = models.CharField(default=CancellationStatus.REQUESTED.value, db_index=True, **enum_field_kwargs(CancellationStatus))
    reason = models.CharField(default=CancellationReason.CUSTOMER_REQUEST.value, **enum_field_kwargs(CancellationReason))
    refund_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    refund_currency = models.CharField(max_length=3, null=True, blank=True)
    requested_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True, default="")  # staff-facing, see OrderReturnModel.note
    rejection_reason = models.TextField(blank=True, default="")  # customer-facing, see OrderReturnModel.rejection_reason

    class Meta:
        db_table = "ordering_cancellations"
        verbose_name = _("Order Cancellation")
        verbose_name_plural = _("Order Cancellations")
        indexes = [models.Index(fields=["order_id", "status"])]


class CancellationLineItemModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    cancellation = models.ForeignKey(OrderCancellationModel, on_delete=models.CASCADE, related_name="lines")
    order_line_item_id = models.UUIDField(db_index=True)
    quantity = models.PositiveIntegerField()

    objects = AllObjectsManager()

    class Meta:
        db_table = "ordering_cancellation_lines"
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0), name="ck_cancellation_lines_quantity_positive")]


class OrderingOutboxEvent(AbstractOutboxEvent):
    class Meta:
        db_table = "ordering_outbox_events"
        ordering = ["created_at"]


class PaymentWebhookDeliveryStatus(models.TextChoices):
    PROCESSED = "processed", "Processed"
    REJECTED = "rejected", "Rejected"


class PaymentWebhookDelivery(BaseModel):
    """
    Phase 02E's payment-webhook replay-protection and provider-
    reference-uniqueness invariant (Step 6/8/17). `(provider,
    provider_transaction_id)` is the correct uniqueness boundary --
    confirmed by inspecting `OrderPaymentReference.payment_id`
    (`apps/ordering/domain/entities.py`), which is itself an opaque,
    externally-supplied id with no built-in provider namespace, so a
    single global uniqueness on that id alone would be wrong if two
    different providers ever happened to issue overlapping reference
    values. A real PostgreSQL unique constraint, not an
    application-level `if exists()` check, is what actually decides a
    concurrent/duplicate delivery race -- the same "let the database
    decide" discipline already proven correct by Phase 02B's
    IdempotencyRecord, Phase 02C's OrderRewardRecord, and Phase 02D's
    ReturnRewardReversalRecord.

    A rejected delivery (signature failure, unknown order, amount/
    currency mismatch) is still recorded here -- Step 16's own
    observability requirement, and a second copy of the identical
    rejected payload must not be reprocessed as if it were new.
    """

    provider = models.CharField(max_length=64)
    provider_transaction_id = models.CharField(max_length=255)
    order_id = models.UUIDField(db_index=True)
    payment_reference_id = models.UUIDField(null=True, blank=True)
    event_type = models.CharField(max_length=32)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=16, choices=PaymentWebhookDeliveryStatus.choices)
    rejection_reason = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "ordering_payment_webhook_deliveries"
        constraints = [
            models.UniqueConstraint(fields=["provider", "provider_transaction_id"], name="uq_payment_webhook_provider_transaction"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"PaymentWebhookDelivery(provider={self.provider}, provider_transaction_id={self.provider_transaction_id}, status={self.status})"


# ---------------------------------------------------------------------------
# Delivery (Yetkazib berish markazi -- apps/ordering/infrastructure/admin_delivery.py)
# ---------------------------------------------------------------------------


class Courier(BaseModel):
    """A person who takes delivery orders to customers (own staff or a hired courier); picked on the delivery desk."""

    name = models.CharField(_("Name"), max_length=120)
    phone = models.CharField(_("Phone"), max_length=32, blank=True, default="")
    vehicle = models.CharField(_("Transport"), max_length=60, blank=True, default="", help_text=_("e.g. Damas 01 A 123 BC, scooter, on foot"))
    telegram_username = models.CharField(_("Telegram"), max_length=64, blank=True, default="")
    is_active = models.BooleanField(_("Active"), default=True)

    class Meta:
        db_table = "ordering_couriers"
        ordering = ("-is_active", "name")
        verbose_name = _("Courier")
        verbose_name_plural = _("Couriers")

    def __str__(self) -> str:
        return self.name


class DeliveryAssignment(BaseModel):
    """Who takes an order and when -- one row per delivery order, written only by the delivery desk. The order status
    itself still changes only through the ordering lifecycle services."""

    order = models.OneToOneField(OrderModel, on_delete=models.CASCADE, related_name="delivery")
    courier = models.ForeignKey(Courier, on_delete=models.SET_NULL, null=True, blank=True, related_name="deliveries")
    planned_date = models.DateField(_("Delivery date"), null=True, blank=True)
    time_slot = models.CharField(_("Time window"), max_length=40, blank=True, default="", help_text=_("e.g. 14:00-18:00"))
    fee = models.DecimalField(_("Courier fee"), max_digits=12, decimal_places=2, null=True, blank=True)
    note = models.CharField(_("Note for the courier"), max_length=300, blank=True, default="")
    assigned_by = models.CharField(max_length=150, blank=True, default="")

    class Meta:
        db_table = "ordering_delivery_assignments"
        verbose_name = _("Delivery")
        verbose_name_plural = _("Deliveries")
