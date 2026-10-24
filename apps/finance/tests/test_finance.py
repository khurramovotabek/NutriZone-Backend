"""Moliya: account balances from automatic flows + manual operations, routing rules, P&L, cash flow and the pages."""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User as StaffUser
from django.core.exceptions import ValidationError
from django.test import Client
from django.utils import timezone

from apps.finance.infrastructure import ledger, pnl
from apps.finance.infrastructure.models import Category, MoneyAccount, Transaction

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_client():
    user = StaffUser.objects.create_superuser(username=f"fin_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def accounts():
    MoneyAccount.objects.all().delete()
    start = timezone.localdate() - timedelta(days=40)
    cash = MoneyAccount.objects.create(name="Kassa", kind="cash", opening_balance=Decimal("1000000"), opening_date=start, sources=["pos_cash", "web_cod", "supplier_cash", "payroll"])
    bank = MoneyAccount.objects.create(name="Bank", kind="bank", opening_balance=Decimal("0"), opening_date=start, sources=["pos_card", "pos_qr", "web_online", "supplier_bank"])
    return cash, bank


def _sale(amount, method="cash", when=None, branch=None):
    from apps.pos.infrastructure.models import SaleLineItemModel, SaleModel

    sale = SaleModel.objects.create(branch_id=branch or uuid.uuid4(), cashier_id=uuid.uuid4(), status="completed", channel="store", completed_at=when or timezone.now(),
                                    payment_method=method, payments=[{"method": method, "amount": str(amount)}])
    SaleLineItemModel.objects.create(sale=sale, product_id=uuid.uuid4(), quantity=1, unit_price_amount=amount, unit_price_currency="UZS")
    return sale


def _tx(kind, amount, account, category=None, to_account=None, day=None):
    n = Transaction.objects.count() + 1
    return Transaction.objects.create(number=f"FO-T{n:05d}", kind=kind, amount=Decimal(amount), account=account, to_account=to_account, category=category,
                                      occurred_on=day or timezone.localdate())


class TestBalances:
    def test_till_money_lands_in_the_account_of_its_payment_method(self, accounts):
        cash, bank = accounts
        _sale(Decimal("200000"), "cash")
        _sale(Decimal("300000"), "uzcard")
        bal = ledger.balances()
        assert bal[cash.id]["balance"] == Decimal("1200000")
        assert bal[bank.id]["balance"] == Decimal("300000")
        assert bal[bank.id]["in_month"] == Decimal("300000")

    def test_manual_expense_income_and_transfer(self, accounts):
        cash, bank = accounts
        rent = Category.objects.get(name="Ijara")
        other = Category.objects.get(name="Boshqa daromad")
        _tx("expense", "400000", cash, rent)
        _tx("income", "50000", bank, other)
        _tx("transfer", "100000", cash, to_account=bank)
        bal = ledger.balances()
        assert bal[cash.id]["balance"] == Decimal("500000")
        assert bal[bank.id]["balance"] == Decimal("150000")

    def test_voided_operation_and_money_before_the_opening_date_do_not_count(self, accounts):
        cash, _bank = accounts
        t = _tx("expense", "400000", cash, Category.objects.get(name="Ijara"))
        t.voided_at = timezone.now()
        t.save()
        _sale(Decimal("70000"), "cash", when=timezone.now() - timedelta(days=60))
        assert ledger.balances()[cash.id]["balance"] == Decimal("1000000")

    def test_supplier_payment_and_payroll_are_outflows(self, accounts):
        from apps.stores.infrastructure.models import Supplier, SupplierPayment

        cash, bank = accounts
        sup = Supplier.objects.create(name=f"Sup {uuid.uuid4().hex[:4]}")
        SupplierPayment.objects.create(supplier=sup, amount=Decimal("250000"), paid_on=timezone.localdate(), method="bank")
        SupplierPayment.objects.create(supplier=sup, amount=Decimal("10000"), paid_on=timezone.localdate(), method="cash")
        bal = ledger.balances()
        assert bal[bank.id]["balance"] == Decimal("-250000")
        assert bal[cash.id]["balance"] == Decimal("990000")

    def test_branch_account_takes_its_own_till(self, accounts):
        from apps.stores.infrastructure.models import Store

        cash, _bank = accounts
        store = Store.objects.create(name="Chilonzor", slug=f"ch-{uuid.uuid4().hex[:5]}")
        branch_cash = MoneyAccount.objects.create(name="Chilonzor kassa", kind="cash", store=store, opening_date=cash.opening_date, sources=["pos_cash"])
        _sale(Decimal("80000"), "cash", branch=store.id)
        _sale(Decimal("20000"), "cash")
        bal = ledger.balances()
        assert bal[branch_cash.id]["balance"] == Decimal("80000")
        assert bal[cash.id]["balance"] == Decimal("1020000")

    def test_statement_running_balance(self, accounts):
        cash, _bank = accounts
        _sale(Decimal("200000"), "cash")
        _tx("expense", "50000", cash, Category.objects.get(name="Ijara"))
        st = ledger.statement(cash, cash.opening_date, timezone.localdate())
        assert st["opening"] == Decimal("1000000") and st["closing"] == Decimal("1150000")
        assert st["in"] == Decimal("200000") and st["out"] == Decimal("50000")

    def test_unrouted_money_is_reported(self, accounts):
        cash, bank = accounts
        bank.sources = ["pos_card"]
        bank.save()
        _sale(Decimal("90000"), "click")
        _routed, orphans = ledger.route(ledger.auto_flows(timezone.localdate(), timezone.localdate()), MoneyAccount.objects.filter(is_active=True))
        assert [(o.source, o.amount) for o in orphans] == [("pos_qr", Decimal("90000"))]


class TestRules:
    def test_a_source_goes_to_one_account_only(self, accounts):
        dup = MoneyAccount(name="Ikkinchi kassa", kind="cash", opening_date=timezone.localdate(), sources=["pos_cash"])
        with pytest.raises(ValidationError):
            dup.full_clean()

    def test_transfer_needs_another_account_and_expense_needs_a_category(self, accounts):
        cash, _bank = accounts
        with pytest.raises(ValidationError):
            Transaction(number="X", kind="transfer", amount=1, account=cash, to_account=cash, occurred_on=timezone.localdate()).full_clean()
        with pytest.raises(ValidationError):
            Transaction(number="Y", kind="expense", amount=1, account=cash, occurred_on=timezone.localdate()).full_clean()
        with pytest.raises(ValidationError):
            Transaction(number="Z", kind="expense", amount=1, account=cash, category=Category.objects.get(name="Boshqa daromad"), occurred_on=timezone.localdate()).full_clean()


class TestReports:
    def test_pnl_revenue_minus_expenses(self, accounts):
        cash, _bank = accounts
        _sale(Decimal("1000000"), "cash")
        _tx("expense", "300000", cash, Category.objects.get(name="Ijara"))
        _tx("expense", "50000", cash, Category.objects.get(name="Soliqlar"))
        _tx("expense", "999999", cash, Category.objects.get(name="Egasiga to'lov (dividend)"))  # capital: not a cost
        r = pnl.pnl(pnl.months_back(timezone.localdate(), 1))
        rows = {x["key"]: x for x in r["rows"] if "values" in x}
        assert rows["revenue"]["values"][0] == Decimal("1000000")
        assert rows["opex"]["values"][0] == Decimal("-300000")
        # no cost known for the sold item -> cogs 0, so net = revenue − rent − tax
        assert rows["net"]["values"][0] == Decimal("650000")

    def test_cashflow_ignores_transfers(self, accounts):
        cash, bank = accounts
        _sale(Decimal("100000"), "cash")
        _tx("transfer", "40000", cash, to_account=bank)
        _tx("expense", "30000", cash, Category.objects.get(name="Ijara"))
        r = pnl.cashflow(pnl.months_back(timezone.localdate(), 1))
        assert r["total_in"][0] == Decimal("100000") and r["total_out"][0] == Decimal("30000")
        assert r["closing"][0] == Decimal("1070000")


class TestPages:
    def test_every_page_renders(self, staff_client, accounts):
        cash, _bank = accounts
        _sale(Decimal("100000"), "cash")
        _tx("expense", "30000", cash, Category.objects.get(name="Ijara"))
        for url in ("/django-admin/finance/overview/", "/django-admin/finance/pnl/?months=12", "/django-admin/finance/cashflow/?months=3",
                    "/django-admin/finance/budget/", "/django-admin/finance/debts/", f"/django-admin/finance/account/{cash.id}/",
                    "/django-admin/finance/transaction/", "/django-admin/finance/transaction/add/?kind=transfer", "/django-admin/finance/moneyaccount/",
                    "/django-admin/finance/category/", f"/django-admin/finance/moneyaccount/{cash.id}/change/"):
            res = staff_client.get(url)
            assert res.status_code == 200, url
        for url in ("/django-admin/finance/pnl/?export=xlsx", "/django-admin/finance/cashflow/?export=xlsx", f"/django-admin/finance/account/{cash.id}/?export=xlsx"):
            res = staff_client.get(url)
            assert res.status_code == 200 and "spreadsheet" in res["Content-Type"], url

    def test_add_operation_numbers_it_and_void_keeps_it(self, staff_client, accounts):
        cash, _bank = accounts
        rent = Category.objects.get(name="Ijara")
        res = staff_client.post("/django-admin/finance/transaction/add/", {"kind": "expense", "occurred_on": timezone.localdate().isoformat(), "amount": "120000",
                                                                            "account": str(cash.id), "category": str(rent.id), "counterparty": "Uy egasi"})
        assert res.status_code == 302, res.content[:500]
        t = Transaction.objects.get()
        assert t.number == "FO-000001" and t.created_by
        staff_client.post(f"/django-admin/finance/operation/{t.id}/void/", {"reason": "xato"})
        t.refresh_from_db()
        assert t.voided_at and t.void_reason == "xato"
        assert ledger.balances()[cash.id]["balance"] == Decimal("1000000")

    def test_future_date_is_rejected(self, staff_client, accounts):
        cash, _bank = accounts
        res = staff_client.post("/django-admin/finance/transaction/add/", {"kind": "expense", "occurred_on": (timezone.localdate() + timedelta(days=3)).isoformat(),
                                                                            "amount": "1", "account": str(cash.id), "category": str(Category.objects.get(name="Ijara").id)})
        assert res.status_code == 200 and not Transaction.objects.exists()

    def test_budget_save_and_copy(self, staff_client, accounts):
        from apps.finance.infrastructure.models import BudgetLine

        rent = Category.objects.get(name="Ijara")
        m = timezone.localdate().replace(day=1)
        staff_client.post("/django-admin/finance/budget/", {"month": f"{m:%Y-%m}", f"plan_{rent.id}": "5 000 000"})
        assert BudgetLine.objects.get(month=m, category=rent).amount == Decimal("5000000")
        nxt = pnl.next_month(m)
        staff_client.post("/django-admin/finance/budget/", {"month": f"{nxt:%Y-%m}", "copy_prev": "1"})
        assert BudgetLine.objects.filter(month=nxt, category=rent).exists()
