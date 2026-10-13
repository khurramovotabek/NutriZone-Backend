"""
Ordering domain enums.

`ordering` is Domain Architecture Specification §2.6, confirmed by
reading the module's own placeholder scaffold before any code was
written (its README cited that section explicitly).
"""
from __future__ import annotations

from common.utils import DomainStrEnum


class OrderStatus(DomainStrEnum):
    """The primary, customer-visible order lifecycle. Cancellation/return WORKFLOWS have their own dedicated aggregates (OrderCancellation/OrderReturn) with richer sub-lifecycles, but their outcome still surfaces here as the order's own terminal status -- a customer looking at one order needs one status, not three."""

    DRAFT = "draft"
    PENDING_PAYMENT = "pending_payment"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    RETURNED = "returned"
    FAILED = "failed"


class OrderLineItemStatus(DomainStrEnum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    RETURNED = "returned"
    FULFILLED = "fulfilled"


class OrderChannel(DomainStrEnum):
    """Mirrors `apps.cart.domain.enums.CartSource` -- Ordering defines its own copy rather than importing Cart's, per the modular-monolith isolation rule."""

    WEB = "web"
    MOBILE = "mobile"
    POS = "pos"
    API = "api"
    TELEGRAM = "telegram"


class OrderType(DomainStrEnum):
    STANDARD = "standard"
    GIFT = "gift"


class PaymentReferenceStatus(DomainStrEnum):
    """Tracks the STATE of a payment as reported by a future Payments/Wallet module -- Ordering never executes payment itself, only records what it was told happened, referenced by ID."""

    PENDING = "pending"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class FulfillmentReferenceStatus(DomainStrEnum):
    """Tracks the STATE of a fulfillment as reported by a future Fulfillment/Shipping module -- Ordering never executes shipment itself."""

    PENDING = "pending"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    FAILED = "failed"


class InvoiceStatus(DomainStrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    VOID = "void"


class ReturnStatus(DomainStrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    RECEIVED = "received"
    REFUNDED = "refunded"
    CLOSED = "closed"


class ReturnReason(DomainStrEnum):
    DEFECTIVE = "defective"
    WRONG_ITEM = "wrong_item"
    NOT_AS_DESCRIBED = "not_as_described"
    CHANGED_MIND = "changed_mind"
    DAMAGED_IN_TRANSIT = "damaged_in_transit"
    OTHER = "other"


class CancellationStatus(DomainStrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"


class CancellationReason(DomainStrEnum):
    CUSTOMER_REQUEST = "customer_request"
    OUT_OF_STOCK = "out_of_stock"
    PAYMENT_FAILED = "payment_failed"
    FRAUD_SUSPECTED = "fraud_suspected"
    ADMIN_ACTION = "admin_action"
    OTHER = "other"


class OrderFailureReason(DomainStrEnum):
    """Backs the `OrderFailure` entity -- a structured record of why a checkout attempt didn't produce a confirmed order (distinct from CancellationReason, which applies to an already-successful order being cancelled afterward)."""

    PAYMENT_DECLINED = "payment_declined"
    INVENTORY_UNAVAILABLE = "inventory_unavailable"
    PRICE_MISMATCH = "price_mismatch"
    VALIDATION_FAILED = "validation_failed"
    SYSTEM_ERROR = "system_error"


class OrderLockReason(DomainStrEnum):
    """Backs 'Lock Order'/'Unlock Order' -- orthogonal to OrderStatus (a CONFIRMED order under fraud review is still CONFIRMED, just also locked). Mirrors `apps.cart.domain.enums.CartLockReason`'s shape."""

    FRAUD_REVIEW = "fraud_review"
    MANUAL_INTERVENTION = "manual_intervention"
    DISPUTE = "dispute"
