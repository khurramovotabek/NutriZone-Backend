"""
Branch-to-branch stock transfer ("filialdan filialga ko'chirish").

A transfer is one document -- a sending branch, a receiving branch and
one or more product lines -- that moves AVAILABLE stock between two
WarehouseInventory rows of the same product. It is all-or-nothing: if
any line lacks stock at the sender, nothing moves.

This module holds only the rules that need no database: the document's
own invariants and how raw lines are normalised. Moving the units uses
the existing WarehouseInventory.transfer_out()/receive_transfer_in()
pair, so the ledger rules ("only AVAILABLE stock may transfer") stay in
one place.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from apps.inventory.domain.exceptions import InsufficientStock, InvalidMovement

MAX_UNITS_PER_LINE = 100_000
MAX_LINES_PER_TRANSFER = 200
NOTE_MAX_LENGTH = 500


class SameBranchTransfer(InvalidMovement):
    code = "SAME_BRANCH_TRANSFER"


class EmptyTransfer(InvalidMovement):
    code = "EMPTY_TRANSFER"


class InvalidTransferQuantity(InvalidMovement):
    code = "INVALID_TRANSFER_QUANTITY"


@dataclass(frozen=True, slots=True)
class Shortage:
    product_variant_id: uuid.UUID
    requested: int
    available: int


class TransferShortage(InsufficientStock):
    """Raised before anything moves, listing EVERY line the sending branch cannot cover -- so staff fix the whole document at once."""

    code = "TRANSFER_SHORTAGE"

    def __init__(self, shortages: list[Shortage]) -> None:
        self.shortages = shortages
        super().__init__(f"Not enough stock at the sending branch for {len(shortages)} product(s).")


@dataclass(frozen=True, slots=True)
class TransferLineRequest:
    product_variant_id: uuid.UUID
    quantity: int


@dataclass(slots=True)
class TransferLine:
    product_variant_id: uuid.UUID
    quantity: int
    source_warehouse_inventory_id: uuid.UUID
    destination_warehouse_inventory_id: uuid.UUID
    source_balance_after: int
    destination_balance_after: int


@dataclass(slots=True)
class StockTransfer:
    id: uuid.UUID
    number: str
    source_warehouse_id: uuid.UUID
    destination_warehouse_id: uuid.UUID
    note: str
    actor_id: uuid.UUID | None
    completed_at: datetime
    lines: list[TransferLine] = field(default_factory=list)

    @property
    def total_units(self) -> int:
        return sum(line.quantity for line in self.lines)


def transfer_number(sequence: int) -> str:
    """Human document number, e.g. TR-000042 -- what staff read out and search by."""
    return f"TR-{sequence:06d}"


def normalise_transfer_request(source_warehouse_id: uuid.UUID, destination_warehouse_id: uuid.UUID, lines: list[TransferLineRequest]) -> list[TransferLineRequest]:
    """
    Validates the document and merges repeated products into one line
    (picking the same product twice means "send the sum"), keeping the
    order in which products were first picked.
    """
    if source_warehouse_id == destination_warehouse_id:
        raise SameBranchTransfer("The sending and receiving branch must be different.")
    if not lines:
        raise EmptyTransfer("Add at least one product to the transfer.")

    merged: dict[uuid.UUID, int] = {}
    for line in lines:
        if isinstance(line.quantity, bool) or not isinstance(line.quantity, int) or line.quantity <= 0:
            raise InvalidTransferQuantity("Each quantity must be a whole number greater than zero.")
        merged[line.product_variant_id] = merged.get(line.product_variant_id, 0) + line.quantity

    if len(merged) > MAX_LINES_PER_TRANSFER:
        raise InvalidTransferQuantity(f"A transfer can hold at most {MAX_LINES_PER_TRANSFER} products.")
    if any(qty > MAX_UNITS_PER_LINE for qty in merged.values()):
        raise InvalidTransferQuantity(f"A single line can move at most {MAX_UNITS_PER_LINE} units.")
    return [TransferLineRequest(product_variant_id=pid, quantity=qty) for pid, qty in merged.items()]
