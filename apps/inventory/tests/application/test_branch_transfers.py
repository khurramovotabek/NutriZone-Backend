"""
Branch-to-branch stock transfers: TransferStockBetweenBranches against the
real database (row locks, ledger, document numbering) plus the pure
request-normalisation rules.
"""
from __future__ import annotations

import uuid

import pytest

from apps.inventory.domain.transfers import (
    EmptyTransfer, InvalidTransferQuantity, SameBranchTransfer, TransferLineRequest, TransferShortage,
    normalise_transfer_request, transfer_number,
)
from apps.inventory.infrastructure import models as orm
from apps.inventory.infrastructure.composition import build_transfer_between_branches

SOURCE = uuid.uuid4()
DEST = uuid.uuid4()


def _stocked_variant(source_qty: int, dest_qty: int | None = None) -> uuid.UUID:
    """A product variant with `source_qty` available at SOURCE (and optionally a row at DEST)."""
    variant_id = uuid.uuid4()
    inventory = orm.InventoryModel.objects.create(id=uuid.uuid4(), code=f"INV-{uuid.uuid4().hex[:8].upper()}", product_variant_id=variant_id, status="active")
    orm.WarehouseInventoryModel.objects.create(id=uuid.uuid4(), inventory=inventory, warehouse_id=SOURCE, available_quantity=source_qty)
    if dest_qty is not None:
        orm.WarehouseInventoryModel.objects.create(id=uuid.uuid4(), inventory=inventory, warehouse_id=DEST, available_quantity=dest_qty)
    return variant_id


def _available(variant_id: uuid.UUID, warehouse_id: uuid.UUID) -> int | None:
    row = orm.WarehouseInventoryModel.objects.filter(inventory__product_variant_id=variant_id, warehouse_id=warehouse_id).first()
    return row.available_quantity if row else None


def _transfer(lines, note=""):
    return build_transfer_between_branches(uuid.uuid4()).execute(source_warehouse_id=SOURCE, destination_warehouse_id=DEST, lines=lines, note=note, actor_name="Kassir")


class TestNormaliseRequest:
    def test_repeated_products_are_merged_in_first_pick_order(self):
        a, b = uuid.uuid4(), uuid.uuid4()
        lines = normalise_transfer_request(SOURCE, DEST, [TransferLineRequest(a, 2), TransferLineRequest(b, 1), TransferLineRequest(a, 3)])
        assert lines == [TransferLineRequest(a, 5), TransferLineRequest(b, 1)]

    def test_same_branch_is_rejected(self):
        with pytest.raises(SameBranchTransfer):
            normalise_transfer_request(SOURCE, SOURCE, [TransferLineRequest(uuid.uuid4(), 1)])

    def test_empty_document_is_rejected(self):
        with pytest.raises(EmptyTransfer):
            normalise_transfer_request(SOURCE, DEST, [])

    @pytest.mark.parametrize("qty", [0, -3, True, 2.5, 100_001])
    def test_bad_quantities_are_rejected(self, qty):
        with pytest.raises(InvalidTransferQuantity):
            normalise_transfer_request(SOURCE, DEST, [TransferLineRequest(uuid.uuid4(), qty)])

    def test_number_format(self):
        assert transfer_number(42) == "TR-000042"


@pytest.mark.django_db
@pytest.mark.integration
class TestTransferStockBetweenBranches:
    def test_moves_stock_and_creates_the_receiving_row(self):
        variant = _stocked_variant(source_qty=95)

        doc = _transfer([TransferLineRequest(variant, 12)], note="  restock  ")

        assert _available(variant, SOURCE) == 83
        assert _available(variant, DEST) == 12
        assert doc.total_units == 12
        assert doc.note == "restock"
        row = orm.StockTransferModel.objects.get(id=doc.id)
        assert row.number == doc.number and row.total_units == 12 and row.actor_name == "Kassir"
        line = row.lines.get()
        assert (line.quantity, line.source_balance_after, line.destination_balance_after) == (12, 83, 12)

    def test_every_move_is_in_the_ledger_under_the_document_number(self):
        variant = _stocked_variant(source_qty=10, dest_qty=4)

        doc = _transfer([TransferLineRequest(variant, 6)])

        entries = sorted(orm.InventoryLedgerModel.objects.filter(reference=doc.number).values_list("quantity_delta", "balance_after"))
        assert entries == [(-6, 4), (6, 10)]
        assert orm.InventoryOutboxEvent.objects.filter(event_type="StockTransferred").count() == 1

    def test_whole_stock_can_be_moved(self):
        variant = _stocked_variant(source_qty=7)
        _transfer([TransferLineRequest(variant, 7)])
        assert _available(variant, SOURCE) == 0
        assert _available(variant, DEST) == 7

    def test_a_short_line_moves_nothing_and_lists_every_shortage(self):
        ok = _stocked_variant(source_qty=50)
        short = _stocked_variant(source_qty=3)
        missing = uuid.uuid4()  # never stocked anywhere

        with pytest.raises(TransferShortage) as exc:
            _transfer([TransferLineRequest(ok, 10), TransferLineRequest(short, 5), TransferLineRequest(missing, 1)])

        by_variant = {s.product_variant_id: (s.requested, s.available) for s in exc.value.shortages}
        assert by_variant == {short: (5, 3), missing: (1, 0)}
        assert _available(ok, SOURCE) == 50  # all-or-nothing
        assert _available(short, SOURCE) == 3
        assert not orm.StockTransferModel.objects.exists()

    def test_shortage_is_checked_against_current_stock(self):
        short = _stocked_variant(source_qty=3)
        with pytest.raises(TransferShortage) as exc:
            _transfer([TransferLineRequest(short, 5)])
        assert [(s.requested, s.available) for s in exc.value.shortages] == [(5, 3)]
        assert _available(short, DEST) is None  # the receiving row created during the attempt was rolled back

    def test_document_numbers_increase(self):
        variant = _stocked_variant(source_qty=10)
        first = _transfer([TransferLineRequest(variant, 1)])
        second = _transfer([TransferLineRequest(variant, 1)])
        assert int(second.number.split("-")[1]) == int(first.number.split("-")[1]) + 1

    def test_several_products_in_one_document(self):
        a = _stocked_variant(source_qty=20)
        b = _stocked_variant(source_qty=5, dest_qty=1)
        doc = _transfer([TransferLineRequest(a, 12), TransferLineRequest(b, 5)])
        assert doc.total_units == 17 and len(doc.lines) == 2
        assert (_available(a, DEST), _available(b, DEST)) == (12, 6)
