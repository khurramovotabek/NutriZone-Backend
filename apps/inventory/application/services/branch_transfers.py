"""
TransferStockBetweenBranches -- moves AVAILABLE stock of one or more
products from one branch (Store / warehouse) to another as a single
transfer document. See apps/inventory/domain/transfers.py for the rules.

Order of work, all inside one database transaction:
  1. normalise + validate the request (distinct branches, positive
     quantities, repeated products merged);
  2. resolve each product's Inventory and its row at both branches
     (the receiving row is created empty when the branch never held
     the product);
  3. lock every touched row at once, in id order (no deadlocks between
     concurrent transfers), then check EVERY line against the locked,
     current balances -- if anything is short, raise before a single
     unit moves;
  4. move each line through the existing transfer_out()/
     receive_transfer_in() ledger pair, referenced by the document
     number, and persist the document.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from django.db import transaction
from django.utils import timezone as django_timezone

from apps.inventory.application.ports import StockTransferRepository, WarehouseInventoryRepository
from apps.inventory.application.services._shared import InventoryServiceContext
from apps.inventory.domain.events import StockTransferred
from apps.inventory.domain.transfers import (
    NOTE_MAX_LENGTH, Shortage, StockTransfer, TransferLine, TransferLineRequest, TransferShortage,
    normalise_transfer_request, transfer_number,
)
from apps.inventory.domain.value_objects import StockQuantity


class TransferStockBetweenBranches:
    def __init__(self, warehouse_repo: WarehouseInventoryRepository, transfer_repo: StockTransferRepository, ctx: InventoryServiceContext) -> None:
        self._warehouses = warehouse_repo
        self._transfers = transfer_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, source_warehouse_id: uuid.UUID, destination_warehouse_id: uuid.UUID, lines: list[TransferLineRequest], note: str = "", actor_name: str = "") -> StockTransfer:
        with self._ctx.timer("inventory_branch_transfer_duration"):
            requested = normalise_transfer_request(source_warehouse_id, destination_warehouse_id, lines)

            # 2. resolve rows at both branches
            pairs: list[tuple[TransferLineRequest, uuid.UUID, uuid.UUID]] = []
            shortages: list[Shortage] = []
            for line in requested:
                inventory_id = self._warehouses.inventory_id_for_variant(line.product_variant_id)
                source = self._warehouses.get_by_inventory_and_warehouse(inventory_id, source_warehouse_id) if inventory_id else None
                if inventory_id is None or source is None:
                    shortages.append(Shortage(product_variant_id=line.product_variant_id, requested=line.quantity, available=0))
                    continue
                destination = self._warehouses.get_or_create_for_warehouse(inventory_id, destination_warehouse_id)
                pairs.append((line, source.id, destination.id))

            # 3. lock everything, then check every line against current balances
            locked = self._warehouses.lock_many(sorted({wid for _, s, d in pairs for wid in (s, d)}))
            shortages += [
                Shortage(product_variant_id=line.product_variant_id, requested=line.quantity, available=locked[source_id].available_quantity)
                for line, source_id, _ in pairs
                if locked[source_id].available_quantity < line.quantity
            ]
            if shortages:
                # the whole transaction rolls back, including any receiving rows created above
                raise TransferShortage(shortages)

            # 4. move the stock and record the document
            sequence = self._transfers.next_sequence()
            number = transfer_number(sequence)
            now: datetime = django_timezone.now()
            doc = StockTransfer(
                id=uuid.uuid4(), number=number, source_warehouse_id=source_warehouse_id, destination_warehouse_id=destination_warehouse_id,
                note=(note or "").strip()[:NOTE_MAX_LENGTH], actor_id=self._ctx.actor_id, completed_at=now,
            )
            events = []
            for line, source_id, destination_id in pairs:
                source, destination = locked[source_id], locked[destination_id]
                qty = StockQuantity(line.quantity)
                out_tx, out_ledger = source.transfer_out(qty, number, now)
                in_tx, in_ledger = destination.receive_transfer_in(qty, number, now)
                self._warehouses.save(source)
                self._warehouses.save(destination)
                self._warehouses.persist_transaction_and_ledger(source_id, out_tx, out_ledger)
                self._warehouses.persist_transaction_and_ledger(destination_id, in_tx, in_ledger)
                doc.lines.append(TransferLine(
                    product_variant_id=line.product_variant_id, quantity=line.quantity,
                    source_warehouse_inventory_id=source_id, destination_warehouse_inventory_id=destination_id,
                    source_balance_after=source.available_quantity, destination_balance_after=destination.available_quantity,
                ))
                events.append(("StockTransferred", StockTransferred(source_warehouse_inventory_id=source_id, destination_warehouse_inventory_id=destination_id, quantity=line.quantity).to_payload()))

            self._transfers.save(doc, sequence, actor_name=actor_name)
            self._ctx.stage_events(events)
            self._ctx.audit().created(
                entity_type="StockTransfer", entity_id=str(doc.id),
                after={"number": number, "from": str(source_warehouse_id), "to": str(destination_warehouse_id), "lines": len(doc.lines), "units": doc.total_units},
            )
            self._ctx.invalidate_inventory_cache()
            self._ctx.metric("stock_branch_transfers_total")
            self._ctx.metric("stock_transferred_total", value=doc.total_units)
            return doc
