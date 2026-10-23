"""Goods receipt and transfers: expiry dates as printed on labels, and batches identified by (LOT, expiry)."""
from __future__ import annotations

import io
import uuid
from datetime import date, timedelta

import pytest
from django.utils import timezone

from apps.stores.infrastructure import stock_service, transfer_service as svc
from apps.stores.infrastructure.models import StockBatch, Store
from apps.stores.tests.interfaces.test_my_store_products import _make_owner, _make_store, _make_variant
from common.exceptions import ConflictError, ValidationFailed

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.mark.parametrize(("raw", "expected"), [
    ("2027-03-15", date(2027, 3, 15)),
    ("15.03.2027", date(2027, 3, 15)),
    ("15/03/27", date(2027, 3, 15)),
    ("03/2027", date(2027, 3, 31)),
    ("2.2028", date(2028, 2, 29)),
    ("2027-02", date(2027, 2, 28)),
    ("EXP 12/26", date(2026, 12, 31)),
    ("", None),
])
def test_parse_date_reads_label_formats(raw, expected):
    assert stock_service._parse_date(raw) == expected


@pytest.mark.parametrize("raw", ["31.02.2027", "13/2027", "soon"])
def test_parse_date_rejects_impossible_dates(raw):
    with pytest.raises(ValidationFailed):
        stock_service._parse_date(raw)


def test_receipt_rejects_typo_year():
    store = Store.objects.create(id=uuid.uuid4(), name="Sklad", kind="warehouse")
    v = _make_variant(barcode="4780000000901", status="active")
    with pytest.raises(ValidationFailed):
        stock_service.post_receipt(store, [{"variant_id": str(v.id), "quantity": 1, "expiry": "0027-05-01"}], actor="t")


def test_receipt_keeps_two_expiries_of_the_same_lotless_product_apart():
    store = Store.objects.create(id=uuid.uuid4(), name="Sklad", kind="warehouse")
    v = _make_variant(barcode="4780000000902", status="active")
    soon, later = timezone.localdate() + timedelta(days=200), timezone.localdate() + timedelta(days=500)
    r = stock_service.post_receipt(store, [
        {"variant_id": str(v.id), "quantity": 10, "expiry": soon.isoformat()},
        {"variant_id": str(v.id), "quantity": 5, "expiry": later.strftime("%m/%Y")},
        {"variant_id": str(v.id), "quantity": 2, "expiry": soon.strftime("%d.%m.%Y")},
    ], actor="t")
    assert r.total_units == 17 and r.items.count() == 2
    batches = {b.expiry_date: b.quantity for b in StockBatch.objects.filter(store=store, product_variant=v)}
    assert batches[soon] == 12
    assert sum(q for d, q in batches.items() if d != soon) == 5


def test_receipt_excel_reports_bad_expiry_per_row():
    from openpyxl import Workbook

    v = _make_variant(barcode="4780000000903", status="active")
    wb = Workbook()
    ws = wb.active
    ws.append(["Barcode", "Soni", "Yaroqlilik muddati"])
    ws.append(["4780000000903", 3, "03/2027"])
    ws.append(["4780000000903", 1, "31.02.2027"])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    lines, problems = stock_service.parse_receipt_excel(buf)
    assert [ln["expiry"] for ln in lines] == ["2027-03-31"] and lines[0]["variant_id"] == str(v.id)
    assert len(problems) == 1 and problems[0].startswith("3-qator")


def test_transfer_line_pinned_to_a_batch_cannot_exceed_that_batch():
    warehouse = Store.objects.create(id=uuid.uuid4(), name="Sklad", kind="warehouse")
    branch = _make_store(_make_owner(), name="Filial")
    v = _make_variant(barcode="4780000000904", status="active")
    soon, later = timezone.localdate() + timedelta(days=120), timezone.localdate() + timedelta(days=400)
    stock_service.post_receipt(warehouse, [
        {"variant_id": str(v.id), "quantity": 3, "batch": "L1", "expiry": soon.isoformat()},
        {"variant_id": str(v.id), "quantity": 20, "batch": "L2", "expiry": later.isoformat()},
    ], actor="t")
    t = svc.create(warehouse.id, branch.id, "t")
    with pytest.raises(ConflictError) as e:
        svc.update_draft(t.id, "t", [{"variant_id": str(v.id), "quantity": 10, "batch": "L1", "expiry": soon.isoformat()}])
    assert getattr(e.value, "code", "") == "INSUFFICIENT_BATCH_STOCK"
    # both batches on one draft, each within what it holds
    svc.update_draft(t.id, "t", [
        {"variant_id": str(v.id), "quantity": 3, "batch": "L1", "expiry": soon.isoformat()},
        {"variant_id": str(v.id), "quantity": 7, "batch": "L2", "expiry": later.isoformat()},
    ])
    assert sorted(i.expected_quantity for i in t.items.all()) == [3, 7]
