"""
POS repository.

Concrete implementation of `SaleRepository` -- maps ORM rows to
domain dataclasses only, never leaks ORM objects outside this module.

**`created_at` is explicitly included in `save()`'s defaults dict** --
applying the specific, named lesson this build's own discipline
requires after the real defect found in Notifications' Phase 4 and
re-verified for Analytics' own repositories in its Phase 2 (Section
9.1 of this phase's own brief names this exact check explicitly).

**No standalone `SaleLineItemRepository` exists** -- `SaleLineItem`
remains an owned entity, persisted only as part of its parent `Sale`'s
own `save()`/reconstruction, matching the certified aggregate
boundary exactly.
"""
from __future__ import annotations

import uuid

from django.db import IntegrityError, transaction

from apps.pos.domain.aggregates import Sale
from apps.pos.domain.entities import SaleLineItem
from apps.pos.domain.enums import SaleStatus
from apps.pos.domain.value_objects import Quantity
from apps.pos.infrastructure import models as orm
from common.exceptions import ConflictError
from shared.value_objects.money import Money


class DjangoSaleRepository:
    def get_by_id(self, sale_id: uuid.UUID) -> Sale | None:
        row = orm.SaleModel.objects.filter(id=sale_id).prefetch_related("line_items").first()
        return self._to_domain(row) if row else None

    @transaction.atomic
    def save(self, sale: Sale) -> Sale:
        """Atomic -- the sale root and its owned line items must not partially persist."""
        try:
            row, _ = orm.SaleModel.objects.update_or_create(
                id=sale.id,
                defaults={
                    "branch_id": sale.branch_id, "cashier_id": sale.cashier_id, "customer_id": sale.customer_id,
                    "status": sale.status.value, "completed_at": sale.completed_at, "voided_at": sale.voided_at, "refunded_at": sale.refunded_at,
                    "created_at": sale.created_at,
                },
            )
        except IntegrityError as exc:
            raise ConflictError("A sale with conflicting unique fields already exists.") from exc

        existing_rows = {li.id: li for li in row.line_items.all()}
        current_line_item_ids = set(sale.line_items.keys())

        for line_item in sale.line_items.values():
            existing = existing_rows.get(line_item.id)
            if existing is None:
                orm.SaleLineItemModel.objects.create(id=line_item.id, sale=row, product_id=line_item.product_id, quantity=line_item.quantity.value, unit_price_amount=line_item.unit_price.amount, unit_price_currency=line_item.unit_price.currency)
                continue
            # An existing line's quantity/price can change (Sale.update_line_item_quantity);
            # persisting only new and removed lines silently kept the original
            # quantity in the database, so a completed sale was reloaded -- and
            # charged, receipted, announced and destocked -- at quantity 1.
            if (existing.quantity, existing.unit_price_amount, existing.unit_price_currency) != (line_item.quantity.value, line_item.unit_price.amount, line_item.unit_price.currency):
                existing.quantity = line_item.quantity.value
                existing.unit_price_amount = line_item.unit_price.amount
                existing.unit_price_currency = line_item.unit_price.currency
                existing.save(update_fields=["quantity", "unit_price_amount", "unit_price_currency"])

        existing_line_item_ids = set(existing_rows)

        removed_ids = existing_line_item_ids - current_line_item_ids
        if removed_ids:
            orm.SaleLineItemModel.objects.filter(id__in=removed_ids).delete()

        return sale

    def _to_domain(self, row: orm.SaleModel) -> Sale:
        line_items = {}
        for li in row.line_items.all():
            entry = SaleLineItem(id=li.id, product_id=li.product_id, quantity=Quantity(li.quantity), unit_price=Money(li.unit_price_amount, li.unit_price_currency))
            line_items[entry.id] = entry

        return Sale(
            id=row.id, branch_id=row.branch_id, cashier_id=row.cashier_id, customer_id=row.customer_id,
            status=SaleStatus(row.status), line_items=line_items, created_at=row.created_at,
            completed_at=row.completed_at, voided_at=row.voided_at, refunded_at=row.refunded_at,
        )
