"""Qo'lda +/− jurnali: admin stock edits need a reason, land in the journal, and ledger rows can't be changed or deleted."""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import User
from django.db import connection, transaction
from django.test import Client

from apps.products.tests.stock_helpers import location, put_stock
from apps.stores.infrastructure import stock_service
from apps.stores.infrastructure.models import StockAdjustment, StockMovement

pytestmark = pytest.mark.django_db


def _variant(name="Olimp Complex Whey 700 g"):
    from apps.products.infrastructure import models as p

    product = p.Product.objects.create(id=uuid.uuid4(), status="published")
    p.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="uz", name=name, slug=f"x-{uuid.uuid4().hex[:6]}")
    return p.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:6]}", is_default=True)


@pytest.fixture
def staff_client():
    user = User.objects.create_superuser(username=f"aj_{uuid.uuid4().hex[:6]}", password="test-pass-12345", first_name="Otabek")
    client = Client()
    client.force_login(user)
    return client


def test_minus_one_shows_in_the_journal_with_before_after_and_reason(staff_client):
    store = location("Olmazor")
    v = _variant()
    put_stock(v.id, 5, store=store)
    with transaction.atomic():
        stock_service.move(store, v.id, -1, "adjustment", reference="ADMIN", actor="Otabek", note="Admin: shikastlangan quti")
    row = StockAdjustment.objects.filter(movement_type="adjustment", reference="ADMIN").get()
    assert row.quantity == -1 and row.balance_before == 5 and row.balance_after == 4
    page = staff_client.get("/django-admin/stores/stockadjustment/").content.decode()
    assert "Olmazor" in page and "Olimp Complex Whey 700 g" in page and "shikastlangan quti" in page and "−1" in page
    assert staff_client.get("/django-admin/stores/stockadjustment/?dir=minus&src=admin").status_code == 200
    x = staff_client.get("/django-admin/stores/stockadjustment/export.xlsx")
    assert x.status_code == 200 and "spreadsheet" in x["Content-Type"]


def test_ledger_rows_cannot_be_changed_or_deleted():
    store = location("Chilonzor")
    v = _variant("Creatine")
    with transaction.atomic():
        stock_service.move(store, v.id, 3, "receipt", reference="KR-T", actor="t")
    m = StockMovement.objects.filter(product_variant_id=v.id).first()
    with pytest.raises(PermissionError):
        m.note = "edited"
        m.save()
    with pytest.raises(PermissionError):
        m.delete()


def test_database_refuses_update_and_delete():
    store = location("Yunusobod")
    v = _variant("BCAA")
    with transaction.atomic():
        stock_service.move(store, v.id, 2, "receipt", reference="KR-T", actor="t")
    m = StockMovement.objects.filter(product_variant_id=v.id).first()
    with connection.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_trigger WHERE tgname = 'nz_stock_ledger_append_only'")
        if cur.fetchone() is None:
            pytest.skip("test database built without migrations")
    for sql in ("UPDATE stores_stock_movements SET quantity = 99 WHERE id = %s", "DELETE FROM stores_stock_movements WHERE id = %s"):
        with pytest.raises(Exception), transaction.atomic(), connection.cursor() as cur:
            cur.execute(sql, [m.id])


def test_store_inline_change_needs_a_reason(staff_client):
    from apps.stores.infrastructure.admin import StockInlineForm
    from apps.stores.infrastructure.models import StoreProductStock

    store = location("Sergeli")
    v = _variant("Omega 3")
    put_stock(v.id, 4, store=store)
    entry = StoreProductStock.objects.get(store=store, product_variant_id=v.id)
    form = StockInlineForm(data={"product_variant": str(v.id), "quantity": "3", "reason": ""}, instance=entry)
    assert not form.is_valid() and "reason" in form.errors
    form = StockInlineForm(data={"product_variant": str(v.id), "quantity": "3", "reason": "sanoqda kam"}, instance=entry)
    assert form.is_valid(), form.errors
