"""Cashier payroll: base salary + KPI % of the cashier's own net sales per month; pay freezes it; admin page + Excel."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth.models import User as StaffUser
from django.test import Client

from apps.notifications.infrastructure.models import NotificationModel
from apps.stores.infrastructure import payroll, pos_cashiers
from apps.stores.infrastructure.models import CashierPayout, StoreCashier
from apps.stores.tests.interfaces.test_my_store_products import _make_owner
from apps.stores.tests.interfaces.test_pos_cashiers_and_reports import POS, _as, _sell, kassa  # noqa: F401  (fixture)

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff():
    c = Client()
    c.force_login(StaffUser.objects.create_superuser(username=f"py_{uuid.uuid4().hex[:6]}", password="x-pass-12345", first_name="Bosh", last_name="Hisobchi"))
    return c


def test_month_helpers():
    from datetime import date

    assert payroll.month_start("2026-10") == date(2026, 10, 1)
    assert payroll.next_month(date(2026, 12, 1)) == date(2027, 1, 1) and payroll.prev_month(date(2026, 1, 1)) == date(2025, 12, 1)
    assert payroll.kpi(Decimal("150000"), Decimal("3")) == Decimal("4500")


def test_kpi_follows_own_net_sales_and_paying_freezes_it(monkeypatch, kassa, staff, django_capture_on_commit_callbacks):  # noqa: F811
    store, v, aziza, bekzod = kassa["store"], kassa["v"], kassa["aziza"], kassa["bekzod"]
    c = _as(monkeypatch, aziza)
    c.post(f"{POS}session/open", {"pin": "2707"}, format="json")
    _sell(c, v, 2, 100000)  # 100 000 by Aziza
    token = c.post(f"{POS}cashier", {"cashier_id": str(bekzod.id), "pin": "2707"}, format="json").json()["data"]["token"]
    _sell(_as(monkeypatch, aziza, token), v, 1, 50000)  # 50 000 by Bekzod

    rep = payroll.month_report(payroll.month_start())
    by = {r["user"].id: r for r in rep["rows"]}
    assert by[aziza.id]["revenue"] == Decimal("100000") and by[aziza.id]["kpi"] == Decimal("3000") and by[aziza.id]["total"] == Decimal("3003000")
    assert by[bekzod.id]["kpi"] == Decimal("1500") and store.owner_id not in by  # owners aren't on the payroll

    earn = _as(monkeypatch, aziza).get(f"{POS}config").json()["data"]["earnings"]
    assert earn["kpi"] == "3000" and earn["total"] == "3003000.00" and earn["paid"] is None

    link = StoreCashier.objects.get(user=aziza)
    staff.post(f"/django-admin/stores/storecashier/payroll/terms/{link.id}/", {"base_salary": "4 000 000", "kpi_percent": "5"})
    link.refresh_from_db()
    assert link.base_salary == Decimal("4000000") and link.kpi_percent == Decimal("5.00")
    assert staff.post(f"/django-admin/stores/storecashier/payroll/terms/{link.id}/", {"base_salary": "1", "kpi_percent": "80"}).status_code == 302
    link.refresh_from_db()
    assert link.kpi_percent == Decimal("5.00")  # 80% refused

    month = payroll.month_start()
    with django_capture_on_commit_callbacks(execute=True):
        staff.post(f"/django-admin/stores/storecashier/payroll/pay/{link.id}/", {"month": f"{month:%Y-%m}", "adjustment": "-20000"})  # no reason -> refused
        assert not CashierPayout.objects.exists()
        staff.post(f"/django-admin/stores/storecashier/payroll/pay/{link.id}/", {"month": f"{month:%Y-%m}", "adjustment": "200000", "note": "Bayram bonusi"})
    p = CashierPayout.objects.get(user=aziza)
    assert (p.revenue, p.kpi_amount, p.base_salary, p.total, p.paid_by) == (Decimal("100000.00"), Decimal("5000.00"), Decimal("4000000.00"), Decimal("4205000.00"), "Bosh Hisobchi")
    assert NotificationModel.objects.filter(recipient_id=aziza.id, kind="salary_paid").exists()
    with pytest.raises(Exception):
        payroll.pay(link, month)  # paid once
    link.kpi_percent = Decimal("10")
    link.save()
    frozen = {r["user"].id: r for r in payroll.month_report(month)["rows"]}[aziza.id]
    assert frozen["payout"] and frozen["total"] == Decimal("4205000.00")  # a changed rate never rewrites a paid month

    page = staff.get(f"/django-admin/stores/storecashier/payroll/?month={month:%Y-%m}").content.decode()
    assert "Aziza Karimova" in page and "Bekzod Aliyev" in page and "4 205 000" in page
    xlsx = staff.get(f"/django-admin/stores/storecashier/payroll/excel/?month={month:%Y-%m}")
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"
    staff.post(f"/django-admin/stores/storecashier/payroll/undo/{p.id}/", {"month": f"{month:%Y-%m}"})
    assert not CashierPayout.objects.exists()


def test_cashier_earnings_hidden_from_owner_and_future_month_refused(monkeypatch, kassa):  # noqa: F811
    assert _as(monkeypatch, kassa["owner"]).get(f"{POS}config").json()["data"]["earnings"] is None
    link = StoreCashier.objects.get(user=kassa["aziza"])
    with pytest.raises(Exception):
        payroll.pay(link, payroll.next_month(payroll.month_start()))
    assert pos_cashiers.store_for_user(_make_owner().id) == (None, None)
