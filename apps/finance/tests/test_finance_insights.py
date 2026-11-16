"""Moliya analysis: month pace vs last month, forecast, runway, debt aging, advice, and the Excel workbooks."""
from __future__ import annotations

import io
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User as StaffUser
from django.test import Client
from django.utils import timezone

from apps.finance.infrastructure import insights
from apps.finance.infrastructure.models import Category, MoneyAccount, Transaction

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_client():
    user = StaffUser.objects.create_superuser(username=f"fi_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def cash():
    MoneyAccount.objects.all().delete()
    return MoneyAccount.objects.create(name="Kassa", kind="cash", opening_balance=Decimal("500000"), opening_date=timezone.localdate() - timedelta(days=70), sources=[])


def _expense(account, amount, day, name="Ijara"):
    cat, _ = Category.objects.get_or_create(name=name, defaults={"kind": "expense", "section": "opex"})
    return Transaction.objects.create(number=f"FO-{uuid.uuid4().hex[:6]}", kind="expense", occurred_on=day, amount=Decimal(amount), account=account, category=cat)


def test_pct_change():
    assert insights.pct_change(150, 100) == 50.0
    assert insights.pct_change(50, 100) == -50.0
    assert insights.pct_change(10, 0) is None


def test_pace_compares_same_days_and_forecasts(cash):
    today = timezone.localdate()
    _expense(cash, 300000, today)
    p = insights.pace(today)
    assert p["cur"]["manual_opex"] == Decimal("300000")
    assert p["cur"]["net"] == Decimal("-300000")
    assert p["cash_out"] == Decimal("300000")
    days_in = p["days_in"]
    assert p["forecast_net"] == (Decimal("-300000") * days_in / today.day).quantize(Decimal(1))


def test_daily_running_net(cash):
    today = timezone.localdate()
    _expense(cash, 1000, today)
    d = insights.daily(today)
    assert len(d["labels"]) >= 28
    assert d["net"][-1] == -1000.0


def test_top_expenses_ranked(cash):
    today = timezone.localdate()
    _expense(cash, 100, today, "Kichik")
    _expense(cash, 900, today, "Katta")
    top = insights.top_expenses(today.replace(day=1), today)
    assert [t["label"] for t in top][:2] == ["Katta", "Kichik"]
    assert top[0]["pct"] == 100


def test_advice_flags_negative_and_quiet_month(cash):
    today = timezone.localdate()
    p = insights.pace(today)
    run = {"months": None, "basis": 0}
    out = insights.advice(p=p, run=run, orphans=["pos_cash"], negative=[{"a": cash, "balance": "−5", "url": "/x"}], over_budget=[], debts={"overdue_raw": 0},
                          couriers=[], coins=Decimal(0), total_cash=Decimal(0), manual_count=0, today=today.replace(day=20))
    levels = [a["level"] for a in out]
    assert levels[0] == "bad"
    assert any("manfiy" in a["text"] for a in out)
    assert any("xarajat kiritilmagan" in a["text"] for a in out)


def test_aging_buckets_empty():
    a = insights.aging(timezone.localdate())
    assert [b["key"] for b in a["buckets"]] == ["not_due", "d30", "d60", "d90", "d90p"]
    assert all("w" in b for b in a["buckets"])


@pytest.mark.parametrize("url", ["/django-admin/finance/overview/", "/django-admin/finance/pnl/?months=12", "/django-admin/finance/cashflow/?months=3",
                                 "/django-admin/finance/budget/", "/django-admin/finance/debts/", "/django-admin/finance/category/",
                                 "/django-admin/finance/moneyaccount/", "/django-admin/finance/transaction/"])
def test_pages_render(staff_client, cash, url):
    _expense(cash, 1000, timezone.localdate())
    assert staff_client.get(url).status_code == 200


def test_full_report_workbook(staff_client, cash):
    import openpyxl

    _expense(cash, 2500, timezone.localdate())
    r = staff_client.get("/django-admin/finance/report/?months=3")
    assert r.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Xulosa", "Foyda va zarar", "Pul oqimi", "Hisoblar", "Qarzlar", "Budjet", "Operatsiyalar"]
    ops = wb["Operatsiyalar"]
    assert any(row[11] == 2500 for row in ops.iter_rows(values_only=True))


@pytest.mark.parametrize("url", ["/django-admin/finance/pnl/?export=xlsx", "/django-admin/finance/cashflow/?export=xlsx",
                                 "/django-admin/finance/budget/?export=xlsx", "/django-admin/finance/debts/?export=xlsx",
                                 "/django-admin/finance/category/export.xlsx", "/django-admin/finance/moneyaccount/export.xlsx"])
def test_page_exports(staff_client, cash, url):
    r = staff_client.get(url)
    assert r.status_code == 200
    assert r["Content-Type"].startswith("application/vnd.openxmlformats")
