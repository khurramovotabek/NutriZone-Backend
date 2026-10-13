"""
Order desk: online orders against warehouse stock, cancellation / return outcomes on the order,
the premium admin workflow pages, and the customer self-service endpoints.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User as StaffUser
from django.test import Client
from django.utils import timezone
from rest_framework.test import APIClient

from apps.ordering.infrastructure import models as orm
from apps.stores.infrastructure import stock_service
from apps.stores.infrastructure.models import StockMovement, Store, StoreProductStock

pytestmark = pytest.mark.django_db


# ------------------------------------------------------------------ fixtures


@pytest.fixture
def warehouse():
    return Store.objects.create(id=uuid.uuid4(), name="Test sklad", slug=f"sklad-{uuid.uuid4().hex[:6]}", kind="warehouse")


def _variant():
    """Stock rows reference real catalogue variants (FK), so stock tests need one."""
    from apps.stores.tests.interfaces.test_my_store_products import _make_variant

    return _make_variant(barcode=f"478{uuid.uuid4().int % 10**10:010d}", status="active").id


def _stock(store, variant_id, qty):
    from django.db import transaction

    with transaction.atomic():
        stock_service.move(store, variant_id, qty, "receipt", reference="TEST-RECEIPT", mirror=False)


def _on_hand(store, variant_id):
    row = StoreProductStock.objects.filter(store=store, product_variant_id=variant_id).first()
    return (row.quantity, row.reserved_quantity) if row else (0, 0)


def _order(status="confirmed", qty=2, price="100000", customer_id=None, delivered_days_ago=None, variant_id=None):
    now = timezone.now()
    order = orm.OrderModel.objects.create(
        order_number=f"ORD-T{uuid.uuid4().hex[:6].upper()}", customer_id=customer_id, status=status, currency="UZS", placed_at=now,
        shipping_recipient_name="Ali", shipping_line1="Street 1", shipping_city="Toshkent", shipping_country_code="UZ", shipping_phone="+998900000000",
        billing_recipient_name="Ali", billing_line1="Street 1", billing_city="Toshkent", billing_country_code="UZ",
    )
    line = orm.OrderLineItemModel.objects.create(order=order, product_variant_id=variant_id or uuid.uuid4(), quantity=qty, unit_price_amount=Decimal(price))
    if delivered_days_ago is not None:
        orm.OrderStatusHistoryEntryModel.objects.create(order=order, from_status="shipped", to_status="delivered", changed_at=now - timedelta(days=delivered_days_ago))
    return order, line


@pytest.fixture
def staff_client():
    user = StaffUser.objects.create_superuser(username=f"desk_{uuid.uuid4().hex[:6]}", password="test-pass-12345", first_name="Dilnoza")
    client = Client()
    client.force_login(user)
    return client


def _act(client, model, obj_id, **data):
    return client.post(f"/django-admin/ordering/{model}/{obj_id}/act/", data)


# ------------------------------------------------------------------ warehouse stock


class TestOnlineOrderStock:
    def test_confirm_reserves_ship_deducts_from_warehouse(self, staff_client, warehouse):
        variant = _variant()
        _stock(warehouse, variant, 10)
        order, _line = _order(status="pending_payment", qty=3, variant_id=variant)

        assert _act(staff_client, "ordermodel", order.id, action="confirm").status_code == 302
        assert _on_hand(warehouse, variant) == (10, 3)  # reserved, not yet taken

        _act(staff_client, "ordermodel", order.id, action="start_processing")
        _act(staff_client, "ordermodel", order.id, action="ship", store_id=str(warehouse.id))
        order.refresh_from_db()
        assert order.status == "shipped"
        assert _on_hand(warehouse, variant) == (7, 0)
        kinds = sorted(StockMovement.objects.filter(reference=order.order_number).values_list("movement_type", flat=True))
        assert kinds == ["release", "reservation", "sale"]  # reserved on confirm, released + sold on shipping

    def test_ship_is_refused_and_rolled_back_when_stock_is_short(self, staff_client, warehouse):
        variant = _variant()
        _stock(warehouse, variant, 1)
        order, _line = _order(status="processing", qty=2, variant_id=variant)
        response = _act(staff_client, "ordermodel", order.id, action="ship", store_id=str(warehouse.id))
        assert response.status_code == 302
        order.refresh_from_db()
        assert order.status == "processing"  # the status change was rolled back with the stock error
        assert _on_hand(warehouse, variant) == (1, 0)

    def test_cancelling_before_shipping_releases_the_reservation(self, staff_client, warehouse):
        variant = _variant()
        _stock(warehouse, variant, 5)
        order, _line = _order(status="pending_payment", qty=2, variant_id=variant)
        _act(staff_client, "ordermodel", order.id, action="confirm")
        _act(staff_client, "ordermodel", order.id, action="cancel", reason="out_of_stock", note="Called the customer")
        order.refresh_from_db()
        assert order.status == "cancelled"
        assert _on_hand(warehouse, variant) == (5, 0)
        assert "Called the customer" in order.note

    def test_history_records_the_staff_member(self, staff_client):
        order, _line = _order(status="confirmed")
        _act(staff_client, "ordermodel", order.id, action="start_processing")
        entry = order.status_history.order_by("-changed_at").first()
        assert entry.to_status == "processing"
        assert "Dilnoza" in (entry.reason or "")


# ------------------------------------------------------------------ admin workflow pages


class TestOrderWorkspacePage:
    def test_workspace_shows_items_totals_and_next_step(self, staff_client):
        order, _line = _order(status="confirmed", qty=2, price="125000")
        body = staff_client.get(f"/django-admin/ordering/ordermodel/{order.id}/change/").content.decode()
        assert "250 000" in body
        assert 'value="start_processing"' in body
        assert "Cancel order" in body

    def test_raw_form_post_cannot_change_the_status(self, staff_client):
        order, _line = _order(status="confirmed")
        staff_client.post(f"/django-admin/ordering/ordermodel/{order.id}/change/", {"status": "delivered"})
        order.refresh_from_db()
        assert order.status == "confirmed"

    def test_orders_cannot_be_typed_in_by_hand(self, staff_client):
        assert staff_client.get("/django-admin/ordering/ordermodel/add/").status_code == 403

    def test_internal_note_is_saved(self, staff_client):
        order, _line = _order()
        staff_client.post(f"/django-admin/ordering/ordermodel/{order.id}/note/", {"note": "Gate code 42"})
        order.refresh_from_db()
        assert order.note == "Gate code 42"


class TestReturnWorkflow:
    def test_full_return_through_the_dashboard(self, staff_client, warehouse):
        variant = _variant()
        _stock(warehouse, variant, 4)
        order, line = _order(status="pending_payment", qty=1, price="240000", variant_id=variant)
        for step in ("confirm", "start_processing", "ship", "deliver"):
            _act(staff_client, "ordermodel", order.id, action=step)
        assert _on_hand(warehouse, variant) == (3, 0)

        response = staff_client.post("/django-admin/ordering/orderreturnmodel/add/", {
            "order_id": str(order.id), "reason": "changed_mind", f"qty_{line.id}": "1", "approve_now": "1", "note": "Unopened",
        })
        assert response.status_code == 302
        ret = orm.OrderReturnModel.objects.get(order_id=order.id)
        assert ret.status == "approved" and "Unopened" in ret.note

        _act(staff_client, "orderreturnmodel", ret.id, action="receive", restock="1")
        order.refresh_from_db()
        assert order.status == "returned"
        assert _on_hand(warehouse, variant) == (4, 0)  # back on the shelf it left from

        _act(staff_client, "orderreturnmodel", ret.id, action="refund", amount="240 000")
        ret.refresh_from_db()
        assert ret.status == "refunded" and ret.refund_amount == Decimal("240000")

    def test_cash_refund_above_what_was_paid_is_refused(self, staff_client):
        order, line = _order(status="delivered", qty=1, price="50000", delivered_days_ago=1)
        staff_client.post("/django-admin/ordering/orderreturnmodel/add/", {"order_id": str(order.id), "reason": "defective", f"qty_{line.id}": "1", "approve_now": "1"})
        ret = orm.OrderReturnModel.objects.get(order_id=order.id)
        _act(staff_client, "orderreturnmodel", ret.id, action="receive")
        _act(staff_client, "orderreturnmodel", ret.id, action="refund", amount="50001")
        ret.refresh_from_db()
        assert ret.status == "received"

    def test_reject_requires_a_reason_and_keeps_it(self, staff_client):
        order, line = _order(status="delivered", qty=1, delivered_days_ago=1)
        staff_client.post("/django-admin/ordering/orderreturnmodel/add/", {"order_id": str(order.id), "reason": "other", f"qty_{line.id}": "1"})
        ret = orm.OrderReturnModel.objects.get(order_id=order.id)
        _act(staff_client, "orderreturnmodel", ret.id, action="reject", note="")
        ret.refresh_from_db()
        assert ret.status == "requested"
        _act(staff_client, "orderreturnmodel", ret.id, action="reject", note="Seal broken")
        ret.refresh_from_db()
        assert ret.status == "rejected" and "Seal broken" in ret.note

    def test_return_window_and_override(self, staff_client):
        order, line = _order(status="delivered", qty=1, delivered_days_ago=30)
        staff_client.post("/django-admin/ordering/orderreturnmodel/add/", {"order_id": str(order.id), "reason": "other", f"qty_{line.id}": "1"})
        assert not orm.OrderReturnModel.objects.filter(order_id=order.id).exists()
        staff_client.post("/django-admin/ordering/orderreturnmodel/add/", {"order_id": str(order.id), "reason": "other", f"qty_{line.id}": "1", "override_window": "1"})
        assert orm.OrderReturnModel.objects.filter(order_id=order.id).exists()

    def test_list_and_create_pages_render(self, staff_client):
        order, _line = _order(status="delivered", delivered_days_ago=1)
        assert staff_client.get("/django-admin/ordering/orderreturnmodel/").status_code == 200
        body = staff_client.get(f"/django-admin/ordering/orderreturnmodel/add/?q={order.order_number}").content.decode()
        assert order.order_number in body


class TestCancellationWorkflow:
    def test_shipped_order_cancellation_puts_stock_back(self, staff_client, warehouse):
        variant = _variant()
        _stock(warehouse, variant, 6)
        order, _line = _order(status="pending_payment", qty=2, variant_id=variant)
        for step in ("confirm", "start_processing", "ship"):
            _act(staff_client, "ordermodel", order.id, action=step)
        assert _on_hand(warehouse, variant) == (4, 0)

        response = staff_client.post("/django-admin/ordering/ordercancellationmodel/add/", {"order_id": str(order.id), "reason": "customer_request", "scope": "all", "complete_now": "1"})
        assert response.status_code == 302
        order.refresh_from_db()
        assert order.status == "cancelled"
        assert set(order.lines.values_list("status", flat=True)) == {"cancelled"}
        assert _on_hand(warehouse, variant) == (6, 0)

    def test_partial_cancellation_keeps_the_order_going(self, staff_client):
        order, line = _order(status="confirmed", qty=1)
        other = orm.OrderLineItemModel.objects.create(order=order, product_variant_id=uuid.uuid4(), quantity=1, unit_price_amount=Decimal("5000"))
        staff_client.post("/django-admin/ordering/ordercancellationmodel/add/", {"order_id": str(order.id), "reason": "out_of_stock", "scope": "lines", f"qty_{line.id}": "1", f"qty_{other.id}": "0", "complete_now": "1"})
        order.refresh_from_db()
        line.refresh_from_db()
        other.refresh_from_db()
        assert order.status == "confirmed"
        assert (line.status, other.status) == ("cancelled", "active")

    def test_delivered_order_cannot_be_cancelled(self, staff_client):
        order, _line = _order(status="delivered", delivered_days_ago=1)
        staff_client.post("/django-admin/ordering/ordercancellationmodel/add/", {"order_id": str(order.id), "reason": "other", "scope": "all"})
        assert not orm.OrderCancellationModel.objects.filter(order_id=order.id).exists()


# ------------------------------------------------------------------ customer self-service


class _AllowAll:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return permission_code != "ordering.order.view_any"


@pytest.fixture
def customer(monkeypatch):
    from common.permissions import HasPermissionCode

    original = HasPermissionCode.resolver
    HasPermissionCode.resolver = _AllowAll()
    user_id = uuid.uuid4()
    monkeypatch.setattr("apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate", lambda self, request: (SimpleNamespace(id=user_id, is_authenticated=True, store_ids=set()), None))
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer fake")
    yield SimpleNamespace(id=user_id, client=client)
    HasPermissionCode.resolver = original


class TestCustomerSelfService:
    def test_confirmed_order_is_cancelled_instantly(self, customer):
        order, _line = _order(status="confirmed", customer_id=customer.id)
        info = customer.client.get(f"/api/v1/orders/{order.order_number}/after-sales").json()["data"]
        assert info["can_cancel"] == "now"
        resp = customer.client.post(f"/api/v1/orders/{order.order_number}/customer-cancel", {"reason": "customer_request", "comment": "Changed my mind"}, format="json")
        assert resp.status_code == 200 and resp.json()["data"]["outcome"] == "cancelled"
        order.refresh_from_db()
        assert order.status == "cancelled"

    def test_shipped_order_becomes_a_request_only_once(self, customer):
        order, _line = _order(status="shipped", customer_id=customer.id)
        first = customer.client.post(f"/api/v1/orders/{order.order_number}/customer-cancel", {}, format="json")
        assert first.json()["data"]["outcome"] == "requested"
        order.refresh_from_db()
        assert order.status == "shipped"
        second = customer.client.post(f"/api/v1/orders/{order.order_number}/customer-cancel", {}, format="json")
        assert second.status_code == 422 and second.json()["error"]["code"] == "CANCELLATION_PENDING"

    def test_return_request_within_window(self, customer):
        order, line = _order(status="delivered", qty=2, customer_id=customer.id, delivered_days_ago=3)
        resp = customer.client.post(f"/api/v1/orders/{order.order_number}/customer-return", {"reason": "defective", "comment": "Broken lid", "lines": [{"order_line_item_id": str(line.id), "quantity": 1}]}, format="json")
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["returns"][0]["status"] == "requested"
        assert data["lines"][0]["returnable"] == 1
        assert "Broken lid" in orm.OrderReturnModel.objects.get(order_id=order.id).note

    def test_return_after_window_is_refused(self, customer):
        order, line = _order(status="delivered", customer_id=customer.id, delivered_days_ago=20)
        assert customer.client.get(f"/api/v1/orders/{order.order_number}/after-sales").json()["data"]["can_return"] is False
        resp = customer.client.post(f"/api/v1/orders/{order.order_number}/customer-return", {"reason": "other", "lines": [{"order_line_item_id": str(line.id), "quantity": 1}]}, format="json")
        assert resp.status_code == 422 and resp.json()["error"]["code"] == "RETURN_WINDOW_EXPIRED"

    def test_someone_elses_order_is_off_limits(self, customer):
        order, _line = _order(status="confirmed", customer_id=uuid.uuid4())
        assert customer.client.get(f"/api/v1/orders/{order.order_number}/after-sales").status_code == 403
        assert customer.client.post(f"/api/v1/orders/{order.order_number}/customer-cancel", {}, format="json").status_code == 403
        order.refresh_from_db()
        assert order.status == "confirmed"
