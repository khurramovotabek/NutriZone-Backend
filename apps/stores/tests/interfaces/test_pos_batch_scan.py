"""
Batch scanning at the till: a batch barcode puts that exact batch on the sale line, completing the sale takes those
units off that batch (not the FEFO one), an expired batch can't be sold, and lowering the quantity trims the batches.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import transaction
from django.utils import timezone

from apps.products.infrastructure import barcodes
from apps.stores.infrastructure import stock_service
from apps.stores.infrastructure.models import StockBatch, StoreProductStock
from apps.stores.tests.interfaces.test_store_pos import _open, shop  # noqa: F401 -- fixture

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _batches(store, variant):
    return {b.batch_number: b.quantity for b in StockBatch.objects.filter(store=store, product_variant=variant) if b.quantity}


@pytest.fixture
def batched(shop):  # noqa: F811
    store, whey = shop["store"], shop["whey"]
    today = timezone.localdate()
    StoreProductStock.objects.filter(store=store, product_variant=whey).update(quantity=0)
    with transaction.atomic():
        stock_service.move(store, whey.id, 3, "receipt", batch_number="SOON", expiry_date=today + timedelta(days=20), mirror=False)
        stock_service.move(store, whey.id, 3, "receipt", batch_number="LATE", expiry_date=today + timedelta(days=300), mirror=False)
    barcodes.attach(whey, "4780000099901", batch="LATE", expires_at=today + timedelta(days=300))
    barcodes.attach(whey, "4780000099918", batch="OLD", expires_at=today - timedelta(days=2))
    return shop


def test_scanned_batch_is_the_one_sold(batched):
    c, store, whey = batched["client"], batched["store"], batched["whey"]
    hit = c.get("/api/v1/my-store/pos/catalog?q=4780000099901").json()["data"]["exact_match"]
    assert hit["batch"]["number"] == "LATE" and hit["batch"]["expired"] is False
    sale = _open(c)
    body = c.post(f"/api/v1/my-store/pos/sales/{sale['id']}/items", {"variant_id": str(whey.id), "quantity": 1, "code": "4780000099901"}, format="json").json()["data"]
    assert body["items"][0]["batches"] == [{"batch": "LATE", "expiry": (timezone.localdate() + timedelta(days=300)).isoformat(), "qty": 1}]
    c.post(f"/api/v1/my-store/pos/sales/{sale['id']}/items", {"variant_id": str(whey.id), "quantity": 1}, format="json")  # main barcode: no batch
    r = c.post(f"/api/v1/my-store/pos/sales/{sale['id']}/complete", {"payment_method": "cash", "amount_tendered": "500000"}, format="json")
    assert r.status_code == 200, r.json()
    assert _batches(store, whey) == {"SOON": 2, "LATE": 2}  # 1 from the scanned LATE batch, 1 by FEFO from SOON


def test_expired_batch_is_refused(batched):
    c, whey = batched["client"], batched["whey"]
    sale = _open(c)
    r = c.post(f"/api/v1/my-store/pos/sales/{sale['id']}/items", {"variant_id": str(whey.id), "quantity": 1, "code": "4780000099918"}, format="json")
    assert r.status_code == 409 and r.json()["error"]["code"] == "EXPIRED_BATCH"


def test_lowering_quantity_trims_batches(batched):
    c, whey = batched["client"], batched["whey"]
    sale = _open(c)
    for _ in range(2):
        body = c.post(f"/api/v1/my-store/pos/sales/{sale['id']}/items", {"variant_id": str(whey.id), "quantity": 1, "code": "4780000099901"}, format="json").json()["data"]
    line = body["items"][0]
    assert line["batches"][0]["qty"] == 2
    body = c.patch(f"/api/v1/my-store/pos/sales/{sale['id']}/items/{line['id']}", {"quantity": 1}, format="json").json()["data"]
    assert body["items"][0]["batches"][0]["qty"] == 1
