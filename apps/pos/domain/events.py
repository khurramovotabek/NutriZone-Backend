"""
POS domain events.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class SaleOpened:
    sale_id: uuid.UUID
    branch_id: uuid.UUID
    cashier_id: uuid.UUID

    def to_payload(self) -> dict:
        return {**asdict(self), "sale_id": str(self.sale_id), "branch_id": str(self.branch_id), "cashier_id": str(self.cashier_id)}


@dataclass(frozen=True, slots=True)
class SaleLineItemAdded:
    sale_id: uuid.UUID
    line_item_id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    unit_price: Decimal

    def to_payload(self) -> dict:
        return {**asdict(self), "sale_id": str(self.sale_id), "line_item_id": str(self.line_item_id), "product_id": str(self.product_id), "unit_price": str(self.unit_price)}


@dataclass(frozen=True, slots=True)
class SaleLineItemRemoved:
    sale_id: uuid.UUID
    line_item_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"sale_id": str(self.sale_id), "line_item_id": str(self.line_item_id)}


@dataclass(frozen=True, slots=True)
class SaleLineItemQuantityUpdated:
    sale_id: uuid.UUID
    line_item_id: uuid.UUID
    new_quantity: int

    def to_payload(self) -> dict:
        return {"sale_id": str(self.sale_id), "line_item_id": str(self.line_item_id), "new_quantity": self.new_quantity}


@dataclass(frozen=True, slots=True)
class SaleCustomerSet:
    sale_id: uuid.UUID
    customer_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"sale_id": str(self.sale_id), "customer_id": str(self.customer_id)}


@dataclass(frozen=True, slots=True)
class SaleCompleted:
    sale_id: uuid.UUID
    total_amount: Decimal
    currency: str

    def to_payload(self) -> dict:
        return {**asdict(self), "sale_id": str(self.sale_id), "total_amount": str(self.total_amount)}


@dataclass(frozen=True, slots=True)
class SaleRefunded:
    sale_id: uuid.UUID
    total_amount: Decimal
    currency: str

    def to_payload(self) -> dict:
        return {**asdict(self), "sale_id": str(self.sale_id), "total_amount": str(self.total_amount)}


@dataclass(frozen=True, slots=True)
class SaleVoided:
    sale_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"sale_id": str(self.sale_id)}
