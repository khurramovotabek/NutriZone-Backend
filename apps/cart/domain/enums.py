"""
Cart domain enums.

`cart` was entirely absent from the original Foundation scaffold (see
this phase's Phase 1 completion report, Step 1) -- unlike every prior
module, there is no "Domain Architecture Specification §N" reference
to cite here, since no placeholder ever existed. This module is new
scaffolding, not a fill-in of a pre-existing stub.
"""
from __future__ import annotations

from common.utils import DomainStrEnum


class CartStatus(DomainStrEnum):
    ACTIVE = "active"
    SAVED = "saved"
    LOCKED = "locked"
    EXPIRED = "expired"
    ARCHIVED = "archived"
    CONVERTED = "converted"  # became an Order -- Cart never imports Ordering; this is a terminal, ID-free status


class CartType(DomainStrEnum):
    GUEST = "guest"
    AUTHENTICATED = "authenticated"
    SAVED = "saved"
    WISHLIST = "wishlist"


class CartSource(DomainStrEnum):
    """Which channel created this cart -- backs 'Channel-aware Cart'."""

    WEB = "web"
    MOBILE = "mobile"
    POS = "pos"
    API = "api"
    TELEGRAM = "telegram"


class CartCurrencyMode(DomainStrEnum):
    """Backs 'Multi-currency Support' -- SINGLE means the cart is pinned to one currency for its lifetime; MULTI means line items may carry independently-priced currencies (e.g. a cross-border catalog), reconciled at checkout by a later module."""

    SINGLE_CURRENCY = "single_currency"
    MULTI_CURRENCY = "multi_currency"


class CartItemStatus(DomainStrEnum):
    ACTIVE = "active"
    REMOVED = "removed"
    OUT_OF_STOCK = "out_of_stock"
    PRICE_CHANGED = "price_changed"
    INVALID = "invalid"


class MergeStrategy(DomainStrEnum):
    """Backs 'Anonymous Cart Merge' -- how a guest cart's items combine into an authenticated cart at login."""

    SUM_QUANTITIES = "sum_quantities"
    KEEP_AUTHENTICATED = "keep_authenticated"
    REPLACE_WITH_GUEST = "replace_with_guest"


class CheckoutReadiness(DomainStrEnum):
    READY = "ready"
    NOT_READY = "not_ready"
    BLOCKED = "blocked"


class CartValidationSeverity(DomainStrEnum):
    WARNING = "warning"
    ERROR = "error"


class CartValidationIssueCode(DomainStrEnum):
    """Closed, named set of validation problems `CartValidationPolicy` can raise -- a plain string code field would let call sites invent ad hoc values."""

    EMPTY_CART = "empty_cart"
    ITEM_OUT_OF_STOCK = "item_out_of_stock"
    ITEM_PRICE_CHANGED = "item_price_changed"
    ITEM_INVALID = "item_invalid"
    CART_LOCKED = "cart_locked"
    CART_EXPIRED = "cart_expired"
    NO_PRICE_SNAPSHOT = "no_price_snapshot"
    CURRENCY_MISMATCH = "currency_mismatch"


class CartLockReason(DomainStrEnum):
    CHECKOUT_IN_PROGRESS = "checkout_in_progress"
    ADMIN_HOLD = "admin_hold"
    FRAUD_REVIEW = "fraud_review"
