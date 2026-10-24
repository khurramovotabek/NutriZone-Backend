"""Delivery desk (Yetkazib berish markazi): the page, courier assignment, the waybill and the cash to collect."""
from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest
from django.contrib.auth.models import User as StaffUser
from django.test import Client
from django.utils import timezone

from apps.ordering.infrastructure import admin_delivery
from apps.ordering.infrastructure import models as orm

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_client():
    user = StaffUser.objects.create_superuser(username=f"dl_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
    client = Client()
    client.force_login(user)
    return client


def _order(status="confirmed", method="delivery", lat=41.31, lng=69.28):
    order = orm.OrderModel.objects.create(
        order_number=f"ORD-D{uuid.uuid4().hex[:6].upper()}", status=status, currency="UZS", placed_at=timezone.now(), fulfilment_method=method,
        shipping_recipient_name="Aziza", shipping_line1="Amir Temur 15", shipping_line2="2-podyezd", shipping_city="Toshkent", shipping_country_code="UZ",
        shipping_phone="+998900000001", shipping_latitude=lat, shipping_longitude=lng,
        billing_recipient_name="Aziza", billing_line1="Amir Temur 15", billing_city="Toshkent", billing_country_code="UZ",
    )
    orm.OrderLineItemModel.objects.create(order=order, product_variant_id=uuid.uuid4(), quantity=2, unit_price_amount=Decimal("150000"))
    return order


class TestDeskPayload:
    def test_stage_lists_only_delivery_orders_with_address_items_and_cash(self):
        mine = _order()
        _order(method="pickup")
        desk = admin_delivery.desk_payload("prepare")
        assert [c["number"] for c in desk["cards"]] == [mine.order_number]
        card = desk["cards"][0]
        assert card["address"] == "Amir Temur 15, 2-podyezd, Toshkent"
        assert card["units"] == 2 and card["raw_collect"] == Decimal("300000") and not card["is_paid"]
        assert card["next"] == "start_processing"
        assert desk["pins"][0]["n"] == mine.order_number
        assert desk["stats"]["unassigned"] == 1

    def test_online_payment_means_nothing_to_collect(self):
        from apps.payment.infrastructure.models import PaymentModel

        order = _order(status="shipped")
        PaymentModel.objects.create(order_id=order.id, customer_id=uuid.uuid4(), amount=Decimal("300000"), currency="UZS", provider="payme", status="succeeded")
        card = admin_delivery.desk_payload("road")["cards"][0]
        assert card["is_paid"] and card["raw_collect"] == 0

    def test_filters_by_courier(self):
        a, b = _order(), _order()
        courier = orm.Courier.objects.create(name="Bekzod", phone="+998901112233")
        admin_delivery.assign(a, {"courier_id": str(courier.id)}, by="staff")
        assert [c["number"] for c in admin_delivery.desk_payload("prepare", courier=str(courier.id))["cards"]] == [a.order_number]
        assert [c["number"] for c in admin_delivery.desk_payload("prepare", courier="none")["cards"]] == [b.order_number]


class TestAssign:
    def test_new_courier_is_created_and_reused(self):
        order = _order()
        row = admin_delivery.assign(order, {"new_courier": "Jasur", "new_phone": "+998901234567", "planned_date": "2026-10-25", "time_slot": "14:00–18:00", "fee": "25 000"}, by="staff")
        assert row.courier.name == "Jasur" and row.fee == Decimal("25000") and str(row.planned_date) == "2026-10-25"
        admin_delivery.assign(_order(), {"new_courier": "Jasur"}, by="staff")
        assert orm.Courier.objects.filter(name="Jasur").count() == 1

    def test_pickup_and_closed_orders_are_rejected(self):
        with pytest.raises(ValueError):
            admin_delivery.assign(_order(method="pickup"), {}, by="staff")
        with pytest.raises(ValueError):
            admin_delivery.assign(_order(status="cancelled"), {}, by="staff")

    def test_bad_date_and_fee_are_rejected(self):
        with pytest.raises(ValueError):
            admin_delivery.assign(_order(), {"planned_date": "tomorrow"}, by="staff")
        with pytest.raises(ValueError):
            admin_delivery.assign(_order(), {"fee": "-5"}, by="staff")


class TestViews:
    def test_page_assign_and_waybill(self, staff_client):
        order = _order()
        for stage in ("new", "prepare", "road", "done"):
            assert staff_client.get(f"/django-admin/ordering/ordermodel/delivery/?stage={stage}").status_code == 200
        page = staff_client.get("/django-admin/ordering/ordermodel/delivery/").content.decode()
        assert order.order_number in page and "Amir Temur 15" in page
        res = staff_client.post(f"/django-admin/ordering/ordermodel/delivery/{order.id}/assign/", json.dumps({"new_courier": "Sardor"}), content_type="application/json")
        assert res.json()["ok"] and res.json()["courier"] == "Sardor"
        sheet = staff_client.get(f"/django-admin/ordering/ordermodel/delivery/{order.id}/waybill/").content.decode()
        assert order.order_number in sheet and "Sardor" in sheet
        assert staff_client.get("/django-admin/ordering/courier/").status_code == 200

    def test_assign_needs_post(self, staff_client):
        order = _order()
        assert staff_client.get(f"/django-admin/ordering/ordermodel/delivery/{order.id}/assign/").status_code == 405
