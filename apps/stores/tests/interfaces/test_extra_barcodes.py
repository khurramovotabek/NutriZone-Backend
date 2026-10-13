"""One product, several barcodes (each batch may carry its own): lookups everywhere, uniqueness, Kirim attach flow."""
from __future__ import annotations

import datetime
import json
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.products.infrastructure import barcodes
from apps.products.infrastructure.models import ProductVariantBarcode
from apps.products.infrastructure.repositories import DjangoProductRepository, DjangoVariantRepository
from apps.stores.infrastructure import pos_service, stock_service
from apps.stores.infrastructure.models import Store, StoreProductStock
from apps.stores.tests.interfaces.test_my_store_products import _make_owner, _make_store, _make_variant

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def admin_client():
    user = get_user_model().objects.create_superuser(username=f"root{uuid.uuid4().hex[:6]}", password="x", email="r@example.com")
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def whey():
    v = _make_variant(barcode="4780000000555", status="active")
    ProductVariantBarcode.objects.create(variant=v, barcode="4780000000999", batch="LOT-2026-03", expires_at=datetime.date(2027, 3, 1))
    return v


def test_main_extra_and_sku_all_resolve_to_the_same_variant(whey):
    assert barcodes.resolve("4780000000555").variant == whey
    m = barcodes.resolve("4780000000999")
    assert m.variant == whey and m.is_extra and m.batch == "LOT-2026-03" and m.expires_at == datetime.date(2027, 3, 1)
    assert barcodes.resolve(whey.sku.lower()).variant == whey
    assert barcodes.resolve("4780000000999.0").variant == whey  # Excel float artefact
    assert stock_service.find_variant("4780000000999") == whey
    assert DjangoVariantRepository().get_by_barcode("4780000000999") == (whey.product_id, whey.id)


def test_a_2d_marking_code_resolves_by_its_gtin(whey):
    # "Asl belgisi" DataMatrix: 01 + GTIN-14 + 21 + per-unit serial (+ GS-separated crypto tail)
    assert barcodes.resolve("0104780000000555215abcXYZ\x1d93dGVz").variant == whey
    assert barcodes.resolve("]d20104780000000999215serial").variant == whey  # an extra barcode's GTIN too
    ProductVariantBarcode.objects.filter(barcode="4780000000999").update(is_active=False)
    assert barcodes.resolve("4780000000999") is None  # a switched-off batch code no longer resolves


def test_a_barcode_can_belong_to_only_one_product(whey):
    other = _make_variant(barcode="4780000000111", status="active")
    for taken in ("4780000000555", "4780000000999"):
        with pytest.raises(ValueError):
            barcodes.attach(other, taken)
    assert DjangoProductRepository().barcode_exists("4780000000999")  # a new main barcode can't reuse a batch code
    row = barcodes.attach(other, "4780000000222", batch="B2")
    assert row.variant == other and barcodes.resolve("4780000000222").variant == other


def test_kirim_lookup_returns_the_batch_and_attach_links_an_unknown_code(admin_client, whey):
    warehouse = Store.objects.create(id=uuid.uuid4(), name="Sklad", kind="warehouse")
    r = admin_client.get("/django-admin/stores/stocktransfer/api/lookup/", {"code": "4780000000999", "location": str(warehouse.id)}).json()["data"]
    assert r["variant_id"] == str(whey.id) and r["batch"] == "LOT-2026-03" and r["expiry"] == "2027-03-01" and r["is_extra_barcode"]

    assert admin_client.get("/django-admin/stores/stocktransfer/api/lookup/", {"code": "4780000000777"}).status_code == 404
    resp = admin_client.post("/django-admin/stores/stocktransfer/api/attach-barcode/", data=json.dumps({"code": "4780000000777", "variant_id": str(whey.id), "batch": "LOT-NEW"}), content_type="application/json")
    assert resp.status_code == 200, resp.content
    again = admin_client.get("/django-admin/stores/stocktransfer/api/lookup/", {"code": "4780000000777"}).json()["data"]
    assert again["variant_id"] == str(whey.id) and again["batch"] == "LOT-NEW"
    dup = admin_client.post("/django-admin/stores/stocktransfer/api/attach-barcode/", data=json.dumps({"code": "4780000000777", "variant_id": str(whey.id)}), content_type="application/json")
    assert dup.status_code == 409


def test_store_pos_finds_a_product_by_its_batch_barcode(whey):
    store = _make_store(_make_owner(), name="Filial")
    StoreProductStock.objects.create(store=store, product_variant=whey, quantity=5)
    result = pos_service.catalog(store, "uz", q="4780000000999")
    assert result["exact_match"] and result["exact_match"]["variant_id"] == str(whey.id)
