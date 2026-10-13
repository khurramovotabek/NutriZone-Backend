"""
After-sales alerts: customer notifications for return / cancellation decisions, Telegram Orders Channel posts for
customer requests (+ the channel's approve buttons), and the dispatcher board endpoints.
"""
from __future__ import annotations

import json
import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import pytest
from django.contrib.auth.models import User as StaffUser
from django.test import Client
from django.utils import timezone

from apps.identity.infrastructure.models import User
from apps.notifications.infrastructure.models import NotificationModel
from apps.ordering.infrastructure import models as orm

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _no_telegram():
    sent = []
    with mock.patch("apps.notifications.infrastructure.tasks.deliver_telegram_notification.delay", side_effect=lambda nid: sent.append(nid)), \
         mock.patch("apps.loyalty.infrastructure.tasks.send_loyalty_notification.delay"):
        yield sent


@pytest.fixture
def staff_client():
    user = StaffUser.objects.create_superuser(username=f"alerts_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
    client = Client()
    client.force_login(user)
    return client


def _customer():
    return User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", status="active", full_name="Aziza Karimova")


def _order(customer, status="delivered", qty=1, lines=1, delivered_days_ago=1):
    now = timezone.now()
    order = orm.OrderModel.objects.create(
        order_number=f"ORD-A{uuid.uuid4().hex[:6].upper()}", customer_id=customer.id if customer else None, status=status, currency="UZS", placed_at=now,
        shipping_recipient_name="Aziza", shipping_line1="Street 1", shipping_city="Toshkent", shipping_country_code="UZ", shipping_phone="+998900000001",
        billing_recipient_name="Aziza", billing_line1="Street 1", billing_city="Toshkent", billing_country_code="UZ",
    )
    made = [orm.OrderLineItemModel.objects.create(order=order, product_variant_id=uuid.uuid4(), quantity=qty, unit_price_amount=Decimal("100000")) for _ in range(lines)]
    if status in ("delivered", "completed"):
        orm.OrderStatusHistoryEntryModel.objects.create(order=order, from_status="shipped", to_status="delivered", changed_at=now - timedelta(days=delivered_days_ago))
    return order, made


def _mark(customer):
    """Notifications that already exist (welcome, the order's own creation status) -- only what comes after counts."""
    return set(NotificationModel.objects.filter(recipient_id=customer.id).values_list("id", flat=True))


def _kinds(customer, before):
    return list(NotificationModel.objects.filter(recipient_id=customer.id).exclude(id__in=before).order_by("created_at").values_list("kind", flat=True))


def _act(client, model, pk, **data):
    return client.post(f"/django-admin/ordering/{model}/{pk}/act/", data)


# ------------------------------------------------------------------ customer notifications


class TestCustomerNotifications:
    def test_return_decisions_reach_the_customer_with_the_reason(self, staff_client):
        customer = _customer()
        order, (line,) = _order(customer)
        before = _mark(customer)
        staff_client.post("/django-admin/ordering/orderreturnmodel/add/", {"order_id": str(order.id), "reason": "defective", f"qty_{line.id}": "1"})
        ret = orm.OrderReturnModel.objects.get(order_id=order.id)
        _act(staff_client, "orderreturnmodel", ret.id, action="reject", note="Seal was broken by the customer")
        assert _kinds(customer, before) == ["return_requested", "return_rejected"]
        rejected = NotificationModel.objects.get(recipient_id=customer.id, kind="return_rejected")
        assert "Seal was broken by the customer" in rejected.i18n["uz"]["body"]
        ret.refresh_from_db()
        assert ret.rejection_reason == "Seal was broken by the customer"

    def test_full_return_path_without_duplicates(self, staff_client, _no_telegram):
        customer = _customer()
        order, (line,) = _order(customer)
        before = _mark(customer)
        staff_client.post("/django-admin/ordering/orderreturnmodel/add/", {"order_id": str(order.id), "reason": "changed_mind", f"qty_{line.id}": "1", "approve_now": "1"})
        ret = orm.OrderReturnModel.objects.get(order_id=order.id)
        _act(staff_client, "orderreturnmodel", ret.id, action="receive")
        _act(staff_client, "orderreturnmodel", ret.id, action="refund", amount="100000")
        # requested+approved in one commit -> only "approved"; the whole order came back -> "order returned" instead of "item received"
        assert _kinds(customer, before) == ["return_approved", "order_returned", "return_refunded"]
        refunded = NotificationModel.objects.get(recipient_id=customer.id, kind="return_refunded")
        assert "100 000" in refunded.i18n["uz"]["body"]
        assert str(refunded.id) in _no_telegram  # decisions also go to Telegram

    def test_partial_cancellation_tells_the_customer_the_rest_still_ships(self, staff_client):
        customer = _customer()
        order, (first, second) = _order(customer, status="confirmed", lines=2)
        before = _mark(customer)
        staff_client.post("/django-admin/ordering/ordercancellationmodel/add/", {"order_id": str(order.id), "reason": "out_of_stock", "scope": "lines", f"qty_{first.id}": "1", f"qty_{second.id}": "0", "complete_now": "1"})
        assert _kinds(customer, before) == ["cancellation_completed"]

    def test_full_cancellation_is_announced_once_as_order_cancelled(self, staff_client):
        customer = _customer()
        order, _lines = _order(customer, status="shipped")
        before = _mark(customer)
        staff_client.post("/django-admin/ordering/ordercancellationmodel/add/", {"order_id": str(order.id), "reason": "customer_request", "scope": "all", "complete_now": "1"})
        assert _kinds(customer, before) == ["order_cancelled"]

    def test_guest_orders_get_no_notifications(self, staff_client):
        order, (line,) = _order(None)
        staff_client.post("/django-admin/ordering/orderreturnmodel/add/", {"order_id": str(order.id), "reason": "other", f"qty_{line.id}": "1", "approve_now": "1"})
        assert NotificationModel.objects.count() == 0


# ------------------------------------------------------------------ Telegram Orders Channel


class _FakeGateway:
    def __init__(self):
        self.sent, self.edited = [], []

    def send_message_with_keyboard(self, chat_id, text, keyboard):
        self.sent.append((chat_id, text, keyboard))
        return len(self.sent)

    def edit_message_text(self, chat_id, message_id, text, inline_keyboard=None):
        self.edited.append(text)


def _sync(settings, gateway):
    from apps.notifications.infrastructure import composition as notifications_composition
    from apps.telegram_bot.infrastructure.after_sales_channel_subscriber import sync_after_sales_channel

    settings.TELEGRAM_ORDERS_CHAT_ID = "-100777"
    settings.PUBLIC_BASE_URL = "https://admin.example.test"
    with mock.patch.object(notifications_composition, "build_orders_telegram_gateway", return_value=gateway):
        return sync_after_sales_channel()


def _as_customer(customer):
    from apps.ordering.infrastructure import after_sales

    return after_sales


class TestOrdersChannel:
    def _start_cursor(self, settings):
        from apps.telegram_bot.infrastructure.models import TelegramOrdersChannelCursor

        TelegramOrdersChannelCursor.objects.filter(id=3).delete()
        _sync(settings, _FakeGateway())  # creates the cursor at "now" (no history replay)

    def test_customer_return_request_is_posted_with_an_approve_button(self, settings):
        from apps.ordering.infrastructure import after_sales

        self._start_cursor(settings)
        customer = _customer()
        order, (line,) = _order(customer, qty=2)
        after_sales.request_return(order, customer.id, "defective", [{"order_line_item_id": str(line.id), "quantity": 1}], "Lid is cracked")
        gateway = _FakeGateway()
        assert _sync(settings, gateway)["posted"] == 1
        (_chat, text, keyboard), = gateway.sent
        assert "QAYTARISH SO'ROVI" in text and order.order_number in text and "Lid is cracked" in text and "Nuqsonli" in text
        ret = orm.OrderReturnModel.objects.get(order_id=order.id)
        assert keyboard[0][0]["callback_data"] == f"manager:ret_ok:{ret.id}"
        assert keyboard[0][1]["url"].endswith(f"/orderreturnmodel/{ret.id}/change/")
        assert _sync(settings, _FakeGateway())["posted"] == 0  # exactly once

    def test_customer_self_cancellation_and_request_are_posted_but_staff_actions_are_not(self, settings, staff_client):
        from apps.ordering.infrastructure import after_sales

        self._start_cursor(settings)
        customer = _customer()
        confirmed, _ = _order(customer, status="confirmed")
        shipped, _ = _order(customer, status="shipped")
        after_sales.cancel(confirmed, customer.id, "customer_request", "Found it cheaper")
        after_sales.cancel(shipped, customer.id, "customer_request", "")
        staff_order, _ = _order(customer, status="confirmed")
        _act(staff_client, "ordermodel", staff_order.id, action="cancel", reason="out_of_stock")  # staff: not announced
        gateway = _FakeGateway()
        _sync(settings, gateway)
        texts = [t for _c, t, _k in gateway.sent]
        assert len(texts) == 2
        assert any("MIJOZ BUYURTMANI BEKOR QILDI" in t and confirmed.order_number in t for t in texts)
        assert any("BEKOR QILISH SO'ROVI" in t and shipped.order_number in t for t in texts)

    def test_channel_buttons_approve_return_and_complete_cancellation(self, settings):
        from apps.notifications.infrastructure import composition as notifications_composition
        from apps.ordering.infrastructure import after_sales
        from apps.telegram_bot.infrastructure.models import TelegramAfterSalesChannelMessage, TelegramStaffMember
        from apps.telegram_bot.interfaces.callback_router import _handle_manager_action

        self._start_cursor(settings)
        TelegramStaffMember.objects.create(telegram_user_id=55501, full_name="Dispatcher Dilnoza", is_active=True)
        customer = _customer()
        delivered, (line,) = _order(customer)
        shipped, _ = _order(customer, status="shipped")
        after_sales.request_return(delivered, customer.id, "other", [{"order_line_item_id": str(line.id), "quantity": 1}])
        after_sales.cancel(shipped, customer.id, "customer_request")
        _sync(settings, _FakeGateway())
        ret = orm.OrderReturnModel.objects.get(order_id=delivered.id)
        can = orm.OrderCancellationModel.objects.get(order_id=shipped.id)

        gateway = _FakeGateway()
        with mock.patch.object(notifications_composition, "build_orders_telegram_gateway", return_value=gateway):
            _handle_manager_action(99999, 1, 1, "ret_ok", str(ret.id))  # not staff: ignored
            ret.refresh_from_db()
            assert ret.status == "requested"
            _handle_manager_action(55501, 1, 1, "ret_ok", str(ret.id))
            _handle_manager_action(55501, 1, 1, "can_ok", str(can.id))
            _handle_manager_action(55501, 1, 1, "can_ok", str(can.id))  # second press: no-op
        ret.refresh_from_db()
        shipped.refresh_from_db()
        assert ret.status == "approved"
        assert shipped.status == "cancelled"
        assert len(gateway.edited) == 2 and "Dispatcher Dilnoza" in gateway.edited[0]
        assert TelegramAfterSalesChannelMessage.objects.filter(resolved_at__isnull=False).count() == 2
        entry = shipped.status_history.order_by("-changed_at").first()
        assert "Dispatcher Dilnoza (Telegram)" in entry.reason


# ------------------------------------------------------------------ dispatcher board


class TestDispatcherBoard:
    def test_board_page_and_data(self, staff_client):
        customer = _customer()
        order, _ = _order(customer, status="confirmed")
        assert staff_client.get("/django-admin/ordering/ordermodel/board/").status_code == 200
        data = staff_client.get("/django-admin/ordering/ordermodel/board/data/").json()
        confirmed = next(c for c in data["columns"] if c["key"] == "confirmed")
        card = next(c for c in confirmed["cards"] if c["number"] == order.order_number)
        assert card["customer"] == "Aziza Karimova" and card["total"] == "100 000" and card["sla"] in ("ok", "warn", "late")
        assert confirmed["next"] == "start_processing"

    def test_move_one_step_forward_only(self, staff_client):
        order, _ = _order(_customer(), status="confirmed")
        move = f"/django-admin/ordering/ordermodel/board/{order.id}/move/"
        skip = staff_client.post(move, json.dumps({"action": "deliver"}), content_type="application/json")
        assert skip.status_code == 409
        ok = staff_client.post(move, json.dumps({"action": "start_processing"}), content_type="application/json")
        assert ok.status_code == 200 and ok.json()["status"] == "processing"

    def test_ship_options_and_move_requires_permission(self, staff_client):
        order, _ = _order(_customer(), status="processing")
        assert staff_client.get(f"/django-admin/ordering/ordermodel/board/{order.id}/ship-options/").json()["ok"] is True
        anonymous = Client().post(f"/django-admin/ordering/ordermodel/board/{order.id}/move/", "{}", content_type="application/json")
        assert anonymous.status_code == 302  # admin login redirect
