"""Unpaid-order reminders / auto-cancel, cash switch, late-payment guard, daily reconciliation, dashboard and bot."""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth.models import User as StaffUser
from django.test import Client
from django.utils import timezone

from apps.notifications.infrastructure.models import NotificationModel
from apps.ordering.infrastructure.models import OrderModel
from apps.payment.infrastructure import automation, reconcile, service
from apps.payment.infrastructure.models import PaymentModel, PaymentReconciliationIssue, PaymentSettings
from apps.payment.infrastructure.providers import payme
from apps.payment.tests.test_online_acquiring import _configure, _customer, _order, _payme, providers  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def telegram():
    gateway = mock.Mock()
    with mock.patch("apps.notifications.infrastructure.composition.build_telegram_gateway", return_value=gateway):
        yield gateway


def _attempt(order, minutes_ago: int, provider="payme", **fields) -> PaymentModel:
    p = PaymentModel.objects.create(order_id=order.id, customer_id=order.customer_id, amount=service.payable(order), currency="UZS",
                                    provider=provider, method=provider, order_number=order.order_number, **fields)
    PaymentModel.objects.filter(pk=p.pk).update(created_at=timezone.now() - timedelta(minutes=minutes_ago), updated_at=timezone.now() - timedelta(minutes=minutes_ago))
    p.refresh_from_db()
    return p


def _customer_tg():
    u = _customer()
    u.telegram_user_id = 700000000 + uuid.uuid4().int % 1000000
    u.save(update_fields=["telegram_user_id"])
    return u


# ---------------------------------------------------------------- reminders / cash / auto-cancel


def test_reminder_after_30_minutes_with_pay_buttons_once(providers, telegram, django_capture_on_commit_callbacks):
    u = _customer_tg()
    fresh, due = _order(u), _order(u)
    _attempt(fresh, 10)
    _attempt(due, 40)
    with django_capture_on_commit_callbacks(execute=True):
        assert automation.send_reminders() == 1
    assert NotificationModel.objects.filter(recipient_id=u.id, kind="payment_reminder").count() == 1
    chat, text, keyboard = telegram.send_message_with_keyboard.call_args.args
    assert chat == str(u.telegram_user_id) and due.order_number in text
    assert keyboard[0][0]["url"].startswith("https://checkout.test.paycom.uz/")
    assert keyboard[1][0]["callback_data"] == f"pay:cash:{due.order_number}"
    assert automation.send_reminders() == 0  # once per order


def test_cash_choice_leaves_the_flow_and_is_never_cancelled(providers, telegram):
    u = _customer()
    o = _order(u)
    _attempt(o, 60 * 30)
    assert automation.choose_cash(u.id, o.order_number) == "ok"
    assert list(automation.awaiting_orders()) == []
    assert automation.cancel_expired() == 0
    o.refresh_from_db()
    assert o.status == "pending_payment"
    assert automation.choose_cash(_customer().id, o.order_number) == "not_found"


def test_auto_cancel_after_24h_but_not_cod_or_in_flight(providers, telegram, django_capture_on_commit_callbacks):
    u = _customer()
    expired, cod, busy = _order(u), _order(u), _order(u)
    _attempt(expired, 25 * 60)
    _attempt(busy, 25 * 60, provider_state=1, status="pending", provider_reference="payme:busy")
    PaymentModel.objects.filter(provider_reference="payme:busy").update(updated_at=timezone.now() - timedelta(hours=1))
    with django_capture_on_commit_callbacks(execute=True):
        assert automation.cancel_expired() == 1
    for o, status in ((expired, "cancelled"), (cod, "pending_payment"), (busy, "pending_payment")):
        o.refresh_from_db()
        assert o.status == status, o.order_number
    assert PaymentModel.objects.get(order_id=expired.id).status == "cancelled"
    assert NotificationModel.objects.filter(recipient_id=u.id, kind="order_payment_expired").count() == 1


def test_settings_switch_off_automation(providers, telegram):
    PaymentSettings.objects.update_or_create(pk=1, defaults={"reminder_enabled": False, "auto_cancel_enabled": False})
    o = _order(_customer_tg())
    _attempt(o, 26 * 60)
    assert automation.send_reminders() == 0 and automation.cancel_expired() == 0


def test_late_payme_payment_on_a_cancelled_order_is_refused(client, providers):
    o = _order(_customer())
    _payme(client, "CreateTransaction", {"id": "late-1", "time": 1, "amount": 15000000, "account": {"order_id": o.order_number}})
    OrderModel.objects.filter(pk=o.pk).update(status="cancelled")
    assert _payme(client, "PerformTransaction", {"id": "late-1"})["error"]["code"] == payme.ERR_CANT_PERFORM


# ---------------------------------------------------------------- reconciliation


def _paid(order, **kw) -> PaymentModel:
    return PaymentModel.objects.create(order_id=order.id, customer_id=order.customer_id, amount=kw.pop("amount", service.payable(order)), currency="UZS",
                                       provider="payme", method="payme", order_number=order.order_number, status="succeeded", paid_at=timezone.now(), **kw)


def test_reconciliation_finds_and_auto_closes_discrepancies(providers):
    u = _customer()
    not_confirmed, closed, double, ok = _order(u), _order(u, status="cancelled"), _order(u, status="confirmed"), _order(u, status="confirmed")
    _paid(not_confirmed)
    _paid(closed)
    _paid(double)
    _paid(double, provider_reference="payme:second")
    _paid(ok, amount=Decimal("1"))
    stuck = _attempt(_order(u), 20 * 60, provider_state=1, status="pending", provider_reference="payme:stuck")
    summary = reconcile.run(external=False)
    kinds = set(PaymentReconciliationIssue.objects.filter(status="open").values_list("kind", flat=True))
    assert {"paid_not_confirmed", "paid_order_closed", "double_payment", "amount_mismatch", "missing_order_ref", "stuck_at_provider"} <= kinds
    assert summary["open"] >= 6
    # the stuck transaction gets settled -> next run closes that issue by itself
    PaymentModel.objects.filter(pk=stuck.pk).update(status="cancelled", provider_state=-1)
    reconcile.run(external=False)
    assert PaymentReconciliationIssue.objects.get(kind="stuck_at_provider").status == "resolved"


def test_click_external_check_flags_payment_only_click_knows(providers):
    from apps.payment.infrastructure.models import PaymentProviderConfig

    PaymentProviderConfig.objects.filter(provider="click").update(is_test_mode=False, settings_public={"service_id": "111", "merchant_id": "222", "merchant_user_id": "33"})
    o = _order(_customer())
    PaymentModel.objects.create(order_id=o.id, customer_id=o.customer_id, amount=service.payable(o), currency="UZS", provider="click", method="click",
                                order_number=o.order_number, status="pending", provider_reference="click:ext-1")
    answers = iter([{"error_code": 0, "payment_id": 555}, {"error_code": 0, "payment_status": 2}])
    with mock.patch.object(reconcile, "click_get", side_effect=lambda state, path: next(answers)):
        summary = reconcile.run()
    assert summary["external"] == 1
    assert PaymentReconciliationIssue.objects.filter(kind="provider_paid_only", status="open").exists()


# ---------------------------------------------------------------- dashboard


@pytest.fixture
def boss():
    c = Client()
    c.force_login(StaffUser.objects.create_superuser(username=f"rec_{uuid.uuid4().hex[:6]}", password="x-pass-12345"))
    return c


def test_dashboard_reconciliation_and_automation(boss, providers):
    o = _order(_customer())
    _paid(o)
    assert boss.post("/django-admin/payment/paymentreconciliationissue/run/").status_code == 302
    page = boss.get("/django-admin/payment/paymentreconciliationissue/").content.decode()
    assert o.order_number in page
    assert "Solishtirishda" in boss.get("/django-admin/payment/paymentproviderconfig/").content.decode()  # critical banner
    issue = PaymentReconciliationIssue.objects.filter(kind="paid_not_confirmed").first()
    boss.post(f"/django-admin/payment/paymentreconciliationissue/{issue.pk}/close/", {"to": "resolved", "note": "tasdiqlandi"})
    issue.refresh_from_db()
    assert issue.status == "resolved" and issue.resolution_note == "tasdiqlandi"
    assert boss.get("/django-admin/payment/paymentreconciliationissue/?all=1").status_code == 200
    boss.post("/django-admin/payment/paymentproviderconfig/automation/", {"reminder_enabled": "on", "reminder_after_minutes": "45", "auto_cancel_after_hours": "12"})
    cfg = PaymentSettings.load()
    assert cfg.reminder_after_minutes == 45 and cfg.auto_cancel_after_hours == 12 and not cfg.auto_cancel_enabled


# ---------------------------------------------------------------- bot


def test_bot_offers_online_methods_and_switches_to_cash(providers, telegram):
    from apps.telegram_bot.interfaces import callback_router

    with mock.patch.object(callback_router, "_send") as send:
        callback_router._send_checkout_summary(1, "uz", {"total": "150000", "currency": "UZS"})
    keyboard = send.call_args.args[2]
    callbacks = [row[0]["callback_data"] for row in keyboard]
    assert "checkout:pay:payme" in callbacks and "checkout:pay:click" in callbacks and "checkout:confirm" in callbacks

    u = _customer()
    o = _order(u)
    _attempt(o, 5)
    with mock.patch.object(callback_router, "_send") as send:
        callback_router._handle_pay(u, 1, "cash", o.order_number, "uz")
    assert o.order_number in send.call_args.args[1]
    assert PaymentModel.objects.get(order_id=o.id).status == "cancelled"
