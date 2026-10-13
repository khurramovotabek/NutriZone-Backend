"""Dashboard: Ombor -> Transfers page, its product search API and the create endpoint."""
from __future__ import annotations

import json
import uuid

import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.inventory.infrastructure import models as inv_orm
from apps.products.infrastructure import models as p_models

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def staff_client():
    user = User.objects.create_superuser(username=f"admin_{uuid.uuid4().hex[:6]}", password="test-pass-12345", first_name="Ali", last_name="Valiyev")
    client = Client()
    client.force_login(user)
    return client


def _store(name: str):
    from apps.identity.infrastructure import models as identity_orm
    from apps.stores.infrastructure.models import Store

    owner = identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", full_name="Owner", status="active")
    return Store.objects.create(id=uuid.uuid4(), owner=owner, name=name, slug=f"s-{uuid.uuid4().hex[:8]}", status="active", city="Toshkent", district="Olmazor")


def _variant(name: str, barcode: str | None = None):
    product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
    p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name=name, slug=f"p-{uuid.uuid4().hex[:8]}")
    return p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:8]}", barcode=barcode, status="active", is_default=True)


def _stock(variant, store, quantity):
    inventory, _ = inv_orm.InventoryModel.objects.get_or_create(product_variant_id=variant.id, defaults={"id": uuid.uuid4(), "code": f"INV-{uuid.uuid4().hex[:8]}", "status": "active"})
    inv_orm.WarehouseInventoryModel.objects.create(id=uuid.uuid4(), inventory=inventory, warehouse_id=store.id, available_quantity=quantity)


def _qty(variant, store):
    row = inv_orm.WarehouseInventoryModel.objects.filter(inventory__product_variant_id=variant.id, warehouse_id=store.id).first()
    return row.available_quantity if row else None


def _post(client, payload):
    return client.post("/django-admin/inventory/transfers/api/create", data=json.dumps(payload), content_type="application/json")


class TestTransferPage:
    def test_page_lists_branches_and_history(self, staff_client):
        yunusobod, olmazor = _store("Yunusobod"), _store("Olmazor")
        creatine = _variant("ON Creatine")
        _stock(creatine, yunusobod, 20)
        assert _post(staff_client, {"source": str(yunusobod.id), "destination": str(olmazor.id), "lines": [{"variant_id": str(creatine.id), "quantity": 12}]}).status_code == 201

        body = staff_client.get("/django-admin/inventory/transfers/").content.decode()
        assert "Yunusobod" in body and "Olmazor" in body
        assert "TR-" in body

    def test_requires_staff(self):
        assert Client().get("/django-admin/inventory/transfers/").status_code in (302, 403)
        assert Client().post("/django-admin/inventory/transfers/api/create", data="{}", content_type="application/json").status_code in (302, 403)

    def test_detail_document_shows_before_and_after(self, staff_client):
        a, b = _store("Yunusobod"), _store("Olmazor")
        v = _variant("ON Creatine")
        _stock(v, a, 20)
        data = _post(staff_client, {"source": str(a.id), "destination": str(b.id), "lines": [{"variant_id": str(v.id), "quantity": 12}]}).json()["data"]

        body = staff_client.get(data["url"]).content.decode()
        assert data["number"] in body and "ON Creatine" in body
        assert "20 → <b>8</b>" in body and "0 → <b>12</b>" in body
        assert "Ali Valiyev" in body


class TestCreateEndpoint:
    def test_twelve_creatines_move_from_yunusobod_to_olmazor(self, staff_client):
        yunusobod, olmazor = _store("Yunusobod"), _store("Olmazor")
        creatine = _variant("Optimum Nutrition Creatine")
        _stock(creatine, yunusobod, 30)

        response = _post(staff_client, {"source": str(yunusobod.id), "destination": str(olmazor.id), "note": "hafta oxiri", "lines": [{"variant_id": str(creatine.id), "quantity": 12}]})

        assert response.status_code == 201
        assert response.json()["data"]["total_units"] == 12
        assert (_qty(creatine, yunusobod), _qty(creatine, olmazor)) == (18, 12)

    def test_shortage_is_reported_per_product_and_nothing_moves(self, staff_client):
        a, b = _store("A"), _store("B")
        v = _variant("Whey Gold")
        _stock(v, a, 3)

        response = _post(staff_client, {"source": str(a.id), "destination": str(b.id), "lines": [{"variant_id": str(v.id), "quantity": 5}]})

        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "TRANSFER_SHORTAGE"
        assert error["shortages"] == [{"variant_id": str(v.id), "name": "Whey Gold", "requested": 5, "available": 3}]
        assert _qty(v, a) == 3

    def test_same_branch_and_unknown_branch_are_rejected(self, staff_client):
        a = _store("A")
        v = _variant("X")
        _stock(v, a, 3)
        same = _post(staff_client, {"source": str(a.id), "destination": str(a.id), "lines": [{"variant_id": str(v.id), "quantity": 1}]})
        assert same.status_code == 422 and same.json()["error"]["code"] == "SAME_BRANCH_TRANSFER"
        unknown = _post(staff_client, {"source": str(a.id), "destination": str(uuid.uuid4()), "lines": [{"variant_id": str(v.id), "quantity": 1}]})
        assert unknown.status_code == 422 and unknown.json()["error"]["code"] == "UNKNOWN_BRANCH"

    def test_malformed_body_is_400(self, staff_client):
        assert _post(staff_client, {"source": "nope"}).status_code == 400


class TestProductSearchApi:
    def _get(self, client, **params):
        return client.get("/django-admin/inventory/transfers/api/products", params).json()["data"]

    def test_browse_lists_only_what_the_sender_has(self, staff_client):
        a, b = _store("A"), _store("B")
        stocked, empty = _variant("Stocked Whey"), _variant("Empty Whey")
        _stock(stocked, a, 9)
        _stock(empty, a, 0)
        _stock(stocked, b, 2)

        data = self._get(staff_client, source=a.id, destination=b.id)
        assert data["mode"] == "browse"
        assert [(r["name"], r["source_available"], r["destination_available"]) for r in data["results"]] == [("Stocked Whey", 9, 2)]

    def test_exact_barcode_returns_one_variant(self, staff_client):
        a, b = _store("A"), _store("B")
        v = _variant("Barcode Creatine", barcode="5056555206218")
        _stock(v, a, 4)
        data = self._get(staff_client, q="5056555206218", source=a.id, destination=b.id)
        assert data["mode"] == "exact"
        assert data["results"][0]["variant_id"] == str(v.id)
        assert data["results"][0]["source_available"] == 4
