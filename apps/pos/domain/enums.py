"""
POS domain enums.

`pos` is Domain Architecture Specification §2.15, confirmed by reading
the module's own placeholder scaffold before any code was written.

**Lifecycle**: OPEN -> COMPLETED or OPEN -> VOIDED, plus
COMPLETED -> REFUNDED (a whole-sale return). A POS sale is not an
Ordering `Order`, so Ordering's own OrderReturn/OrderCancellation can
never reach it -- the in-store return therefore lives here, on the
Sale itself (product decision; previously out of scope).
"""
from __future__ import annotations

from common.utils import DomainStrEnum


class SaleStatus(DomainStrEnum):
    """OPEN -> COMPLETED or OPEN -> VOIDED; COMPLETED -> REFUNDED. VOIDED and REFUNDED are terminal -- a completed sale is never voided, it is refunded."""

    OPEN = "open"
    COMPLETED = "completed"
    VOIDED = "voided"
    REFUNDED = "refunded"


class PaymentMethod(DomainStrEnum):
    """
    How a completed sale was paid. Live: CASH and the two domestic card
    schemes (UZCARD / HUMO) taken on the store's own bank card terminal --
    the POS only records the method and amount, it never talks to the bank.
    Click / Payme / Uzum are declared so a provider integration only has to
    flip `LIVE_PAYMENT_METHODS` -- no schema or API change. CARD is legacy
    (a generic card, before the scheme was recorded).
    """

    CASH = "cash"
    UZCARD = "uzcard"
    HUMO = "humo"
    CARD = "card"
    CLICK = "click"
    PAYME = "payme"
    UZUM = "uzum"
    MIXED = "mixed"  # a split payment -- the parts are in SaleModel.payments


LIVE_PAYMENT_METHODS = frozenset({PaymentMethod.CASH, PaymentMethod.UZCARD, PaymentMethod.HUMO})
CARD_PAYMENT_METHODS = frozenset({PaymentMethod.UZCARD, PaymentMethod.HUMO, PaymentMethod.CARD})


class SaleChannel(DomainStrEnum):
    DASHBOARD = "dashboard"  # staff terminal in the Django dashboard
    STORE = "store"  # a partner store owner's terminal in the storefront (branch_id == Store.id)
