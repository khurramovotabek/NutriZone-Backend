"""Warehouse (sklad) → branch inventory: goods receipt, the transfer state machine, stock accounting and the ledger."""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.stores.infrastructure import stock_service, transfer_service as svc
from apps.stores.infrastructure.models import StockMovement, StockTransfer, Store, StoreProductStock
from apps.stores.tests.interfaces.test_my_store_products import _make_owner, _make_store, _make_variant
from common.exceptions import ConflictError

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _code(exc) -> str:
    return getattr(exc.value, "code", "")


def _qty(store, variant) -> tuple[int, int]:
    row = StoreProductStock.objects.filter(store=store, product_variant=variant).values_list("quantity", "reserved_quantity").first()
    return row or (0, 0)


@pytest.fixture
def world():
    warehouse = Store.objects.create(id=uuid.uuid4(), name="Asosiy sklad", kind="warehouse")
    branch = _make_store(_make_owner(), name="Filial B")
    creatine = _make_variant(barcode="4780000000555", status="active")
    receipt = stock_service.post_receipt(warehouse, [{"variant_id": str(creatine.id), "quantity": 50, "unit_cost": "150000"}], actor="Operator", supplier="Supplier LLC")
    StoreProductStock.objects.create(store=branch, product_variant=creatine, quantity=0)
    stock_service.move(branch, creatine.id, 10, "adjustment", reference="OPENING", actor="test")
    return {"A": warehouse, "B": branch, "v": creatine, "receipt": receipt}


def _transfer(world, qty=15, **line):
    t = svc.create(world["A"].id, world["B"].id, "Operator")
    svc.update_draft(t.id, "Operator", [{"variant_id": str(world["v"].id), "quantity": qty, **line}])
    return StockTransfer.objects.get(pk=t.pk)


def _item(t):
    return t.items.get()


def test_goods_receipt_posts_stock_and_ledger(world):
    r = world["receipt"]
    assert r.number.startswith("KR-") and r.total_units == 50 and int(r.total_value) == 7_500_000
    assert _qty(world["A"], world["v"]) == (50, 0)
    m = StockMovement.objects.get(store=world["A"], movement_type="receipt")
    assert m.quantity == 50 and m.balance_after == 50 and m.reference == r.number and m.actor == "Operator"


def test_full_transfer_moves_stock_through_reserved_and_in_transit(world):
    t = _transfer(world)
    assert t.number.startswith("TR-") and t.status == "draft"
    svc.mark_ready(t.id, "Operator")
    assert _qty(world["A"], world["v"]) == (50, 15)  # reserved: on hand, not sellable
    t = svc.dispatch(t.id, "Manager", picked={str(_item(t).id): 15})
    assert t.status == "in_transit" and _qty(world["A"], world["v"]) == (35, 0)  # 15 are in transit
    assert _qty(world["B"], world["v"]) == (10, 0)
    t = svc.confirm_receipt(t.id, "Receiver", counts={str(_item(t).id): 15})
    assert t.status == "received" and _qty(world["B"], world["v"]) == (25, 0)
    t = svc.complete(t.id, "Manager")
    assert t.status == "completed"
    kinds = list(StockMovement.objects.filter(document_id=t.id).order_by("created_at").values_list("movement_type", "quantity"))
    assert kinds == [("reservation", 15), ("release", -15), ("transfer_out", -15), ("transfer_in", 15)]
    assert t.events.filter(action__startswith="status:").count() == 4


def test_shortage_needs_a_reason_and_approval(world):
    t = _transfer(world)
    svc.mark_ready(t.id, "Op")
    item = _item(t)
    svc.dispatch(t.id, "Mgr", picked={str(item.id): 15})
    with pytest.raises(ConflictError) as e:
        svc.confirm_receipt(t.id, "Rcv", counts={str(item.id): 13})
    assert _code(e) == "DISCREPANCY_REASON_REQUIRED"
    t = svc.confirm_receipt(t.id, "Rcv", counts={str(item.id): 13}, reasons={str(item.id): {"reason": "damaged", "note": "2 ta ezilgan"}})
    assert t.status == "partial" and t.discrepancy_open and _qty(world["B"], world["v"]) == (23, 0)
    with pytest.raises(ConflictError) as e:
        svc.complete(t.id, "Mgr")
    assert _code(e) == "INVALID_TRANSITION"  # can't complete with an unresolved discrepancy
    t = svc.approve_discrepancies(t.id, "Mgr", {str(item.id): "write_off"})
    assert t.status == "received" and not t.discrepancy_open
    assert _qty(world["A"], world["v"]) == (35, 0)
    item.refresh_from_db()
    assert item.difference == -2 and item.resolution == "write_off" and item.discrepancy_reason == "damaged"


def test_excess_deducted_from_source(world):
    t = _transfer(world)
    svc.mark_ready(t.id, "Op")
    item = _item(t)
    svc.dispatch(t.id, "Mgr", picked={str(item.id): 15})
    t = svc.confirm_receipt(t.id, "Rcv", counts={str(item.id): 17}, reasons={str(item.id): {"reason": "counting_error"}})
    assert t.discrepancy_open and _qty(world["B"], world["v"]) == (27, 0)
    svc.approve_discrepancies(t.id, "Mgr", {str(item.id): "deduct_source"})
    assert _qty(world["A"], world["v"]) == (33, 0)


def test_partial_receipt_then_final(world):
    t = _transfer(world, qty=10)
    svc.mark_ready(t.id, "Op")
    item = _item(t)
    svc.dispatch(t.id, "Mgr", picked={str(item.id): 10})
    svc.save_receiving(t.id, "Rcv", {str(item.id): 4})
    svc.save_receiving(t.id, "Rcv", {str(item.id): 4})  # same count twice: idempotent
    assert _qty(world["B"], world["v"]) == (10, 0)  # counted, not posted yet
    t = svc.confirm_receipt(t.id, "Rcv", counts={str(item.id): 6}, final=False)
    assert t.status == "partial" and _qty(world["B"], world["v"]) == (16, 0)
    with pytest.raises(ConflictError) as e:
        svc.save_receiving(t.id, "Rcv", {str(item.id): 5})
    assert _code(e) == "BELOW_POSTED"
    t = svc.confirm_receipt(t.id, "Rcv", counts={str(item.id): 10})
    assert t.status == "received" and _qty(world["B"], world["v"]) == (20, 0)


def test_validation_rules(world):
    with pytest.raises(ConflictError) as e:
        svc.create(world["A"].id, world["A"].id, "Op")
    assert _code(e) == "SAME_LOCATION"
    t = svc.create(world["A"].id, world["B"].id, "Op")
    with pytest.raises(ConflictError) as e:
        svc.update_draft(t.id, "Op", [{"variant_id": str(world["v"].id), "quantity": 51}])
    assert _code(e) == "INSUFFICIENT_STOCK"
    with pytest.raises(ConflictError) as e:
        svc.mark_ready(t.id, "Op")
    assert _code(e) == "EMPTY_TRANSFER"
    with pytest.raises(ConflictError) as e:
        svc.dispatch(t.id, "Op")
    assert _code(e) == "NOT_READY"
    with pytest.raises(ConflictError) as e:
        svc.complete(t.id, "Op")
    assert _code(e) == "INVALID_TRANSITION"


def test_pick_mismatch_needs_confirmation_and_only_picked_units_leave(world):
    t = _transfer(world, qty=10)
    svc.mark_ready(t.id, "Op")
    item = _item(t)
    with pytest.raises(ConflictError) as e:
        svc.dispatch(t.id, "Mgr", picked={str(item.id): 9})
    assert _code(e) == "PICK_MISMATCH"
    with pytest.raises(ConflictError) as e:
        svc.save_pick(t.id, "Mgr", {str(item.id): 11})
    assert _code(e) == "PICK_ABOVE_PLANNED"
    svc.dispatch(t.id, "Mgr", picked={str(item.id): 9}, confirm_mismatch=True)
    assert _qty(world["A"], world["v"]) == (41, 0)


def test_cancel_releases_reservation_and_blocks_receiving(world):
    t = _transfer(world, qty=20)
    svc.mark_ready(t.id, "Op")
    assert _qty(world["A"], world["v"]) == (50, 20)
    svc.cancel(t.id, "Mgr", "Boshqa filialga kerak")
    assert _qty(world["A"], world["v"]) == (50, 0)
    with pytest.raises(ConflictError) as e:
        svc.save_receiving(t.id, "Rcv", {})
    assert _code(e) == "NOT_RECEIVABLE"


def test_reserved_units_cannot_be_sold_or_double_transferred(world):
    first = _transfer(world, qty=40)
    svc.mark_ready(first.id, "Op")
    second = svc.create(world["A"].id, world["B"].id, "Op")
    with pytest.raises(ConflictError) as e:
        svc.update_draft(second.id, "Op", [{"variant_id": str(world["v"].id), "quantity": 11}])
    assert _code(e) == "INSUFFICIENT_STOCK"  # only 10 of 50 are free
    with pytest.raises(ConflictError):
        stock_service.move(world["A"], world["v"].id, -11, "sale")


def test_expired_batch_cannot_be_sent(world):
    t = _transfer(world, qty=5, batch="LOT-OLD", expiry=(timezone.localdate() - timedelta(days=1)).isoformat())
    svc.mark_ready(t.id, "Op")
    with pytest.raises(ConflictError) as e:
        svc.dispatch(t.id, "Mgr", picked={str(_item(t).id): 5})
    assert _code(e) == "EXPIRED_BATCH"


def test_batch_travels_with_the_goods(world):
    t = _transfer(world, qty=5, batch="LOT-2026-08-123", expiry="2028-08-31")
    svc.mark_ready(t.id, "Op")
    svc.dispatch(t.id, "Mgr", picked={str(_item(t).id): 5})
    svc.confirm_receipt(t.id, "Rcv", counts={str(_item(t).id): 5})
    m = StockMovement.objects.get(document_id=t.id, movement_type="transfer_in")
    assert m.batch_number == "LOT-2026-08-123" and str(m.expiry_date) == "2028-08-31"


def test_warehouse_cannot_open_a_till(world):
    from apps.stores.infrastructure import pos_service

    with pytest.raises(ConflictError) as e:
        pos_service.open_session(world["A"], _make_owner().id, 0)
    assert _code(e) == "WAREHOUSE_CANNOT_SELL"


def test_excel_template_round_trip(world):
    """The downloadable template lists the catalogue; filled-in quantities import back as receipt lines."""
    import io

    from apps.stores.infrastructure.warehouse_admin import catalogue_workbook

    wb = catalogue_workbook()
    ws = wb["Kirim"]
    for row in ws.iter_rows(min_row=2):
        if row[0].value == "4780000000555":
            row[4].value = 240
            row[6].value = "LOT-7"
    ws.append(["0000000000000", "Unknown", "", "", 5])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    lines, problems = stock_service.parse_receipt_excel(buf)
    assert lines == [{"variant_id": str(world["v"].id), "quantity": 240, "unit_cost": None, "batch": "LOT-7", "expiry": None}]
    assert len(problems) == 1 and "0000000000000" in problems[0]
    receipt = stock_service.post_receipt(world["A"], lines, actor="Excel")
    assert receipt.total_units == 240 and _qty(world["A"], world["v"]) == (290, 0)


def test_role_permissions_guard_every_action(world):
    import uuid as _uuid

    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group
    from django.test import Client

    t = _transfer(world, qty=5)
    svc.mark_ready(t.id, "Op")
    User = get_user_model()
    receiver = User.objects.create(username=f"rcv_{_uuid.uuid4().hex[:6]}", is_staff=True)
    receiver.groups.add(Group.objects.get(name="Filial qabul qiluvchi"))
    c = Client()
    c.force_login(receiver)
    url = f"/django-admin/stores/stocktransfer/{t.id}/do/dispatch/"
    r = c.post(url, data="{}", content_type="application/json")
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"  # a receiver can't dispatch
    manager = User.objects.create(username=f"mgr_{_uuid.uuid4().hex[:6]}", is_staff=True)
    manager.groups.add(Group.objects.get(name="Sklad menejeri"))
    c.force_login(manager)
    item = str(_item(t).id)
    r = c.post(url, data=f'{{"picked": {{"{item}": 5}}}}', content_type="application/json")
    assert r.status_code == 200 and r.json()["data"]["status"] == "in_transit"
    r = c.post(f"/django-admin/stores/stocktransfer/{t.id}/do/receive_final/", data=f'{{"counts": {{"{item}": 5}}}}', content_type="application/json")
    assert r.status_code == 403  # a warehouse manager doesn't receive at the branch
    c.force_login(receiver)
    r = c.post(f"/django-admin/stores/stocktransfer/{t.id}/do/receive_final/", data=f'{{"counts": {{"{item}": 5}}}}', content_type="application/json")
    assert r.status_code == 200 and r.json()["data"]["status"] == "received"
    assert c.get(f"/django-admin/stores/stocktransfer/{t.id}/document/").status_code == 200
