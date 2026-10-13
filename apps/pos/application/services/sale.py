"""
POS Application Services -- all 6 orchestrate the single certified
`Sale` aggregate.

**A single file, not split across multiple modules** -- unlike
Analytics (2 aggregates -> 2 service files), POS has exactly one
aggregate; splitting would add ceremony with no corresponding
boundary to justify it.

**`@transaction.atomic` wraps save()+stage_events() in every method
below** -- a real, live-verified bug found and fixed: this file's own
prior header claimed no atomic boundary was needed because
`DjangoSaleRepository.save()` is "already atomic". That premise is
correct but the conclusion doesn't follow -- `save()`'s own internal
atomic block closes before `stage_events()` runs, so `stage_event()`'s
own assertion (an active atomic block must already be open, per MIC
§7) fails every time. Confirmed live: a real `OpenSale.execute()` call
crashed with a 422 before this fix, succeeded after. The same
topology bug already found and fixed in Chat's `SendMessage`.

**`add_line_item`/`remove_line_item`/`complete`/`void` each return a
single Domain event directly (not a tuple)** -- re-verified from live
source in this phase's own Step 1, distinct from `Sale.open()`'s own
factory shape (`(Sale, SaleOpened)`), and each service below handles
the correct shape explicitly.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from django.db import transaction

from apps.pos.application.ports import SaleRepository
from apps.pos.application.services._shared import PosServiceContext
from apps.pos.domain.aggregates import Sale
from apps.pos.domain.value_objects import Quantity
from common.exceptions import ResourceNotFound
from shared.value_objects.money import DEFAULT_CURRENCY, Money


def _now() -> datetime:
    return datetime.now(timezone.utc)


class OpenSale:
    """Maps to `Sale.open(sale_id, branch_id, cashier_id, at, customer_id)`, the certified Domain factory -- never manually instantiates `Sale`."""

    def __init__(self, repository: SaleRepository, ctx: PosServiceContext) -> None:
        self._repository = repository
        self._ctx = ctx

    def execute(self, branch_id: uuid.UUID, cashier_id: uuid.UUID, customer_id: uuid.UUID | None = None) -> Sale:
        sale_id = uuid.uuid4()
        sale, event = Sale.open(sale_id, branch_id, cashier_id, _now(), customer_id)
        with transaction.atomic():
            saved = self._repository.save(sale)
            self._ctx.stage_events([(event.__class__.__name__, event.to_payload())])
        self._ctx.metric("pos_sales_opened_total")
        return saved


class LoadSale:
    def __init__(self, repository: SaleRepository) -> None:
        self._repository = repository

    def execute(self, sale_id: uuid.UUID) -> Sale:
        sale = self._repository.get_by_id(sale_id)
        if sale is None:
            raise ResourceNotFound(f"Sale '{sale_id}' not found.")
        return sale


class AddLineItem:
    """Maps to `Sale.add_line_item(product_id, quantity, unit_price)`. Constructs `Quantity`/`Money` at the Application/Domain boundary from raw primitives -- never bypasses them, never duplicates their validation."""

    def __init__(self, repository: SaleRepository, ctx: PosServiceContext) -> None:
        self._repository = repository
        self._ctx = ctx

    def execute(self, sale_id: uuid.UUID, product_id: uuid.UUID, quantity: int, unit_price_amount: Decimal, unit_price_currency: str = DEFAULT_CURRENCY) -> Sale:
        sale = self._repository.get_by_id(sale_id)
        if sale is None:
            raise ResourceNotFound(f"Sale '{sale_id}' not found.")

        event = sale.add_line_item(product_id, Quantity(quantity), Money(unit_price_amount, unit_price_currency))
        with transaction.atomic():
            saved = self._repository.save(sale)
            self._ctx.stage_events([(event.__class__.__name__, event.to_payload())])
        return saved


class SetSaleCustomer:
    """Maps to `Sale.set_customer(customer_id)` -- see that method's own docstring for why this exists: the premium checkout screen selects/creates the real buyer only after the cart is already built, well after `Sale.open()` already ran without one."""

    def __init__(self, repository: SaleRepository, ctx: PosServiceContext) -> None:
        self._repository = repository
        self._ctx = ctx

    def execute(self, sale_id: uuid.UUID, customer_id: uuid.UUID) -> Sale:
        sale = self._repository.get_by_id(sale_id)
        if sale is None:
            raise ResourceNotFound(f"Sale '{sale_id}' not found.")

        event = sale.set_customer(customer_id)
        with transaction.atomic():
            saved = self._repository.save(sale)
            self._ctx.stage_events([(event.__class__.__name__, event.to_payload())])
        return saved


class RemoveLineItem:
    """Maps to `Sale.remove_line_item(line_item_id)` -- the sole legitimate removal path, per this phase's own explicit Section 8. Never calls a repository-level delete method directly."""

    def __init__(self, repository: SaleRepository, ctx: PosServiceContext) -> None:
        self._repository = repository
        self._ctx = ctx

    def execute(self, sale_id: uuid.UUID, line_item_id: uuid.UUID) -> Sale:
        sale = self._repository.get_by_id(sale_id)
        if sale is None:
            raise ResourceNotFound(f"Sale '{sale_id}' not found.")

        event = sale.remove_line_item(line_item_id)
        with transaction.atomic():
            saved = self._repository.save(sale)
            self._ctx.stage_events([(event.__class__.__name__, event.to_payload())])
        return saved


class UpdateLineItemQuantity:
    """Maps to `Sale.update_line_item_quantity(line_item_id, new_quantity)` -- real, closed gap: previously the cashier's +/- taps on a cart line had no atomic backend operation to call (only remove + re-add, two separate calls, and re-add always minted a fresh line item id)."""

    def __init__(self, repository: SaleRepository, ctx: PosServiceContext) -> None:
        self._repository = repository
        self._ctx = ctx

    def execute(self, sale_id: uuid.UUID, line_item_id: uuid.UUID, new_quantity: int) -> Sale:
        sale = self._repository.get_by_id(sale_id)
        if sale is None:
            raise ResourceNotFound(f"Sale '{sale_id}' not found.")

        event = sale.update_line_item_quantity(line_item_id, Quantity(new_quantity))
        with transaction.atomic():
            saved = self._repository.save(sale)
            self._ctx.stage_events([(event.__class__.__name__, event.to_payload())])
        return saved


class CompleteSale:
    """Maps to `Sale.complete(at)`. Never validates line-item count, quantity, or price here -- `EmptySale`/`InvalidSaleTransition` remain entirely Domain-owned and propagate unchanged."""

    def __init__(self, repository: SaleRepository, ctx: PosServiceContext) -> None:
        self._repository = repository
        self._ctx = ctx

    def execute(self, sale_id: uuid.UUID) -> Sale:
        sale = self._repository.get_by_id(sale_id)
        if sale is None:
            raise ResourceNotFound(f"Sale '{sale_id}' not found.")

        event = sale.complete(_now())
        with transaction.atomic():
            saved = self._repository.save(sale)
            self._ctx.stage_events([(event.__class__.__name__, event.to_payload())])
        self._ctx.metric("pos_sales_completed_total")
        return saved


class RefundSale:
    """Maps to `Sale.refund(at)`. Orchestrates only the Domain transition; restocking is the caller's infrastructure concern, exactly as stock decrement is on completion."""

    def __init__(self, repository: SaleRepository, ctx: PosServiceContext) -> None:
        self._repository = repository
        self._ctx = ctx

    def execute(self, sale_id: uuid.UUID) -> Sale:
        sale = self._repository.get_by_id(sale_id)
        if sale is None:
            raise ResourceNotFound(f"Sale '{sale_id}' not found.")

        event = sale.refund(_now())
        with transaction.atomic():
            saved = self._repository.save(sale)
            self._ctx.stage_events([(event.__class__.__name__, event.to_payload())])
        self._ctx.metric("pos_sales_refunded_total")
        return saved


class VoidSale:
    """Maps to `Sale.void(at)`. Orchestrates only the certified Domain void transition -- never attempts to reverse Ordering/Wallet/Loyalty/payment state, per this phase's own explicit Section 9 boundary."""

    def __init__(self, repository: SaleRepository, ctx: PosServiceContext) -> None:
        self._repository = repository
        self._ctx = ctx

    def execute(self, sale_id: uuid.UUID) -> Sale:
        sale = self._repository.get_by_id(sale_id)
        if sale is None:
            raise ResourceNotFound(f"Sale '{sale_id}' not found.")

        event = sale.void(_now())
        with transaction.atomic():
            saved = self._repository.save(sale)
            self._ctx.stage_events([(event.__class__.__name__, event.to_payload())])
        return saved
