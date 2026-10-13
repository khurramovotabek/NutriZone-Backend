"""
POS ORM models.

Mirrors Phase 1's 1 aggregate (`Sale`) plus its 1 owned entity
(`SaleLineItem`) exactly -- 2 base tables + 1 Outbox table.

**Every cross-context reference is a plain `UUIDField`, never a
Django `ForeignKey`** -- `branch_id`, `cashier_id`, `customer_id`
(`SaleModel`) and `product_id` (`SaleLineItemModel`). This matches
real, explicit, already-documented precedent found during this
phase's own Step 1: `apps.identity.infrastructure.models` stores
`store_id = models.UUIDField(...)  # cross-schema ref to stores.
stores, no FK` -- the identical pattern, cited directly, not
invented. `entry.sale` (the owned entity's reference to its own
aggregate root) correctly IS a real `ForeignKey`, matching the
intra-aggregate FK precedent already established throughout this
build (e.g. `ParticipantModel.conversation`, `NotificationDeliveryModel.
notification`).

**`Money` persistence matches Wallet's and Ordering's own exact,
established convention** (`amount: DecimalField(max_digits=14,
decimal_places=2)`, `currency: CharField(max_length=3)`) -- verified
directly during Step 1, not invented. `Quantity` persists as a plain
`PositiveIntegerField`, preserving its certified integer-only, always
positive semantics exactly -- never converted to float, Decimal, or
string.

**No `total` field is stored anywhere** -- `Sale.total()` is computed
on demand from its line items (certified Domain decision); persisting
a redundant, potentially-inconsistent stored total was never
evidenced as required.

**No `Cashier`/`POSOperator`/`Employee` model exists** --
`apps.store.infrastructure.models.StoreEmployee` (with its own
`EmployeeRole.CASHIER` member) already owns that authorization
concept; `SaleModel.cashier_id` is simply a plain UUID reference to
Identity's own `User`, confirmed during Step 1.
"""
from __future__ import annotations

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.pos.domain.enums import PaymentMethod, SaleChannel, SaleStatus
from common.models import SoftDeleteModel
from common.utils import enum_field_kwargs
from core.outbox import AbstractOutboxEvent

MONEY_MAX_DIGITS = 14
MONEY_DECIMAL_PLACES = 2
CURRENCY_MAX_LENGTH = 3


class SaleModel(SoftDeleteModel):
    branch_id = models.UUIDField(db_index=True)
    cashier_id = models.UUIDField(db_index=True)
    customer_id = models.UUIDField(null=True, blank=True, db_index=True)
    status = models.CharField(default=SaleStatus.OPEN.value, db_index=True, **enum_field_kwargs(SaleStatus))
    completed_at = models.DateTimeField(null=True, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    # Checkout-only amount the cashier enters on the POS terminal. It is
    # not part of the Sale aggregate's product total (no line item), so the
    # domain never reads it -- recorded here for sales history/reporting.
    delivery_fee_amount = models.DecimalField(
        max_digits=MONEY_MAX_DIGITS, decimal_places=MONEY_DECIMAL_PLACES, default=0, verbose_name=_("Yetkazib berish puli"),
    )
    # Checkout facts recorded at completion (infrastructure-only, like delivery_fee
    # above -- the Sale aggregate's lifecycle doesn't depend on them).
    channel = models.CharField(default=SaleChannel.DASHBOARD.value, db_index=True, verbose_name=_("Channel"), **enum_field_kwargs(SaleChannel))
    payment_method = models.CharField(default=PaymentMethod.CASH.value, verbose_name=_("Payment method"), **enum_field_kwargs(PaymentMethod))
    amount_tendered = models.DecimalField(max_digits=MONEY_MAX_DIGITS, decimal_places=MONEY_DECIMAL_PLACES, null=True, blank=True, verbose_name=_("Amount tendered"))
    change_amount = models.DecimalField(max_digits=MONEY_MAX_DIGITS, decimal_places=MONEY_DECIMAL_PLACES, null=True, blank=True, verbose_name=_("Change given"))
    # Store terminals: the loyalty coins that covered part of this sale (1 coin = 1 so'm;
    # the rest was paid by `payment_method`), and the cash-register shifts the sale
    # was rung up / refunded in (plain UUID refs to stores.CashSession, no FK).
    coins_redeemed = models.DecimalField(max_digits=MONEY_MAX_DIGITS, decimal_places=MONEY_DECIMAL_PLACES, default=0, verbose_name=_("Paid with coins"))
    cash_session_id = models.UUIDField(null=True, blank=True, db_index=True)
    refund_cash_session_id = models.UUIDField(null=True, blank=True, db_index=True)
    # A cashier's discount on the whole basket (so'm), with its reason. Line prices stay
    # the catalogue prices; what the customer paid = Σ lines − discount − coins.
    discount_amount = models.DecimalField(max_digits=MONEY_MAX_DIGITS, decimal_places=MONEY_DECIMAL_PLACES, default=0, verbose_name=_("Discount"))
    discount_reason = models.CharField(max_length=120, blank=True, default="", verbose_name=_("Discount reason"))
    # Fiscal-style receipt identity, assigned once at completion (see receipts.assign):
    # a gap-free-ish sequential number printed on the receipt ("NZ-000124") and an
    # unguessable token for the public e-receipt link / QR code.
    receipt_number = models.CharField(max_length=20, unique=True, null=True, blank=True, verbose_name=_("Receipt number"))
    receipt_token = models.CharField(max_length=32, unique=True, null=True, blank=True, editable=False)
    # How the money part was paid, split by method: [{"method": "cash", "amount": "50000.00"}, {"method": "uzcard", ...}].
    # Σ amounts = what was paid in money. `payment_method` is that method, or "mixed" for a split payment.
    payments = models.JSONField(default=list, blank=True, verbose_name=_("Payments"))
    # Running totals of (partial) returns -- the detail is in SaleRefundModel.
    refunded_amount = models.DecimalField(max_digits=MONEY_MAX_DIGITS, decimal_places=MONEY_DECIMAL_PLACES, default=0, verbose_name=_("Refunded (money)"))
    refunded_coins = models.DecimalField(max_digits=MONEY_MAX_DIGITS, decimal_places=MONEY_DECIMAL_PLACES, default=0, verbose_name=_("Refunded (coins)"))
    refunded_split = models.JSONField(default=dict, blank=True)  # {"cash": "20000.00", "uzcard": "..."}
    # A basket put on hold at the till ("kutishga qo'yish"): still OPEN, but not the cashier's current one.
    parked_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Parked at"))
    parked_label = models.CharField(max_length=60, blank=True, default="", verbose_name=_("Parked label"))

    class Meta:
        db_table = "pos_sales"
        verbose_name=_("Sale")
        verbose_name_plural = _("Sales")
        indexes = [
            models.Index(fields=["branch_id", "status"]),
            models.Index(fields=["cashier_id", "created_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        """The receipt number ("NZ-000124"), or the short id for a sale that never completed ("#A40CE932")."""
        return self.receipt_number or "#" + str(self.id)[:8].upper()


class SaleLineItemModel(models.Model):
    """Owned, non-root entity -- see this module's own docstring for the plain-UUID-vs-ForeignKey distinction between `sale` (FK, intra-aggregate) and `product_id` (plain UUID, cross-context)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale = models.ForeignKey(SaleModel, on_delete=models.CASCADE, related_name="line_items")
    product_id = models.UUIDField(db_index=True)
    quantity = models.PositiveIntegerField()
    unit_price_amount = models.DecimalField(max_digits=MONEY_MAX_DIGITS, decimal_places=MONEY_DECIMAL_PLACES)
    unit_price_currency = models.CharField(max_length=CURRENCY_MAX_LENGTH)
    # The exact variant sold (size/flavour). The domain line only knows the product;
    # store terminals need the variant to move the store's own per-variant stock.
    product_variant_id = models.UUIDField(null=True, blank=True, db_index=True)
    # Units already returned (partial refunds); the line itself is never edited after the sale.
    refunded_quantity = models.PositiveIntegerField(default=0)
    # Units scanned with a batch barcode: {"<batch>|<YYYY-MM-DD>": units}. Completing the sale takes exactly these
    # batches off the store's stock; the rest of the line leaves by FEFO (stores.stock_service).
    batches = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "pos_sale_line_items"
        indexes = [models.Index(fields=["sale"])]


class SaleRefundModel(models.Model):
    """
    One return (vozvrat) against a completed sale -- some units of some lines, or
    everything that is left. The value returned is the lines' share of what the
    customer actually paid (the basket discount is spread pro rata); that value
    goes back partly as coins (in the proportion coins covered the sale) and the
    rest as money, split over the sale's payment methods in the same proportion.
    Append-only: a return is never edited, a mistake is a new sale.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale = models.ForeignKey(SaleModel, on_delete=models.CASCADE, related_name="refunds")
    number = models.CharField(max_length=24, verbose_name=_("Return number"))
    cashier_id = models.UUIDField(db_index=True)
    cash_session_id = models.UUIDField(null=True, blank=True, db_index=True)
    reason = models.CharField(max_length=255, blank=True, verbose_name=_("Reason"))
    lines = models.JSONField(default=list)  # [{"line_id", "variant_id", "product_id", "quantity", "unit_price", "value"}]
    value = models.DecimalField(max_digits=MONEY_MAX_DIGITS, decimal_places=MONEY_DECIMAL_PLACES, verbose_name=_("Value returned"))
    amount = models.DecimalField(max_digits=MONEY_MAX_DIGITS, decimal_places=MONEY_DECIMAL_PLACES, verbose_name=_("Money returned"))
    coins = models.DecimalField(max_digits=MONEY_MAX_DIGITS, decimal_places=MONEY_DECIMAL_PLACES, default=0, verbose_name=_("Coins returned"))
    split = models.JSONField(default=dict)  # money returned per method {"cash": "…", "uzcard": "…"}
    cashback_reversed = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "pos_sale_refunds"
        ordering = ["created_at"]
        verbose_name = _("Return")
        verbose_name_plural = _("Returns")

    def __str__(self) -> str:  # pragma: no cover
        return self.number


class PosOutboxEvent(AbstractOutboxEvent):
    class Meta:
        db_table = "pos_outbox_events"
        ordering = ["created_at"]
