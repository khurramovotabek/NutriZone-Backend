"""
Money accounts: balances and statements = opening balance + automatic flows (computed live from sales, online
payments, supplier payments and payroll -- see SOURCES) + manual operations (Transaction). Dates are Tashkent days.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models import Q, Sum

from apps.finance.infrastructure.models import POS_SOURCES, SOURCES, MoneyAccount, Transaction, TxKind

TZ = ZoneInfo("Asia/Tashkent")
ZERO = Decimal(0)
POS_METHOD_SOURCE = {"cash": "pos_cash", "uzcard": "pos_card", "humo": "pos_card", "card": "pos_card", "click": "pos_qr", "payme": "pos_qr", "uzum": "pos_qr"}
SUPPLIER_METHOD_SOURCE = {"cash": "supplier_cash", "bank": "supplier_bank", "card": "supplier_card"}


def day_start(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=TZ)


def local_day(dt: datetime) -> date:
    return dt.astimezone(TZ).date()


@dataclass
class Flow:
    """One day's automatic money of one source (and, for tills, one branch). `amount` is signed: + in, − out."""

    day: date
    source: str
    amount: Decimal
    store_id: object = None
    count: int = 0
    refs: list = field(default_factory=list)

    @property
    def label(self) -> str:
        return str(SOURCES[self.source][0])


def _add(bucket: dict, day: date, source: str, amount: Decimal, store_id=None, ref: str = ""):
    if not amount:
        return
    key = (day, source, store_id if source in POS_SOURCES else None)
    f = bucket.get(key)
    if f is None:
        f = bucket[key] = Flow(day=day, source=source, amount=ZERO, store_id=key[2])
    f.amount += amount
    f.count += 1
    if ref and len(f.refs) < 5:
        f.refs.append(ref)


def auto_flows(start: date, end: date) -> list[Flow]:
    """Automatic flows for the days start..end (inclusive)."""
    from apps.ordering.infrastructure.models import OrderLineItemModel, OrderModel, OrderStatusHistoryEntryModel
    from apps.payment.infrastructure.models import PaymentModel
    from apps.pos.infrastructure import sales_reports as rep
    from apps.pos.infrastructure.models import SaleRefundModel
    from apps.stores.infrastructure.models import CashierPayout, SupplierPayment

    lo, hi = day_start(start), day_start(end + timedelta(days=1))
    bucket: dict = {}

    # store tills: the money taken (net of coins), and the money handed back on returns when it happened
    for r in rep.rows(rep.closed_sales().filter(completed_at__gte=lo, completed_at__lt=hi)):
        for method, value in r["split_sold"].items():
            src = POS_METHOD_SOURCE.get(method)
            if src:
                _add(bucket, local_day(r["when"]), src, Decimal(value), r["branch_id"], r.get("receipt_number") or "")
    for ref in SaleRefundModel.objects.filter(created_at__gte=lo, created_at__lt=hi).select_related("sale").only("split", "created_at", "number", "sale__branch_id"):
        for method, value in (ref.split or {}).items():
            src = POS_METHOD_SOURCE.get(method)
            if src:
                _add(bucket, local_day(ref.created_at), src, -Decimal(str(value)), ref.sale.branch_id, ref.number)

    # website: captured provider payments, and cash collected on delivery / at pickup
    paid_orders = set()
    for p in PaymentModel.objects.filter(status="succeeded").exclude(provider="cash").filter(
            Q(paid_at__gte=lo, paid_at__lt=hi) | Q(paid_at__isnull=True, created_at__gte=lo, created_at__lt=hi)).values("amount", "paid_at", "created_at", "order_number"):
        _add(bucket, local_day(p["paid_at"] or p["created_at"]), "web_online", p["amount"], ref=p["order_number"])
    delivered = {}
    for h in OrderStatusHistoryEntryModel.objects.filter(to_status="delivered", changed_at__gte=lo, changed_at__lt=hi).values("order_id", "changed_at"):
        delivered.setdefault(h["order_id"], h["changed_at"])
    if delivered:
        paid_orders = set(PaymentModel.objects.filter(order_id__in=list(delivered), status__in=("succeeded", "refunded")).exclude(provider="cash").values_list("order_id", flat=True))
        cod = [oid for oid in delivered if oid not in paid_orders]
        totals = defaultdict(lambda: ZERO)
        for l in OrderLineItemModel.objects.filter(order_id__in=cod, status="active").values("order_id", "unit_price_amount", "quantity", "discount_amount", "tax_amount"):
            totals[l["order_id"]] += l["unit_price_amount"] * l["quantity"] - l["discount_amount"] + l["tax_amount"]
        numbers = dict(OrderModel.objects.filter(id__in=cod).values_list("id", "order_number"))
        for oid in cod:
            _add(bucket, local_day(delivered[oid]), "web_cod", totals[oid], ref=numbers.get(oid, ""))

    # purchases and payroll
    for sp in SupplierPayment.objects.filter(paid_on__gte=start, paid_on__lte=end).select_related("supplier").only("amount", "paid_on", "method", "supplier__name"):
        src = SUPPLIER_METHOD_SOURCE.get(sp.method)
        if src:
            _add(bucket, sp.paid_on, src, -sp.amount, ref=sp.supplier.name)
    for po in CashierPayout.objects.filter(paid_at__gte=lo, paid_at__lt=hi).select_related("user").only("total", "paid_at", "user__full_name"):
        _add(bucket, local_day(po.paid_at), "payroll", -po.total, ref=po.user.full_name or "")
    return sorted(bucket.values(), key=lambda f: (f.day, f.source))


def _takes(account: MoneyAccount, flow: Flow) -> bool:
    if flow.source not in (account.sources or []):
        return False
    if flow.source in POS_SOURCES and account.store_id:
        return flow.store_id == account.store_id
    return True


def route(flows: list[Flow], accounts) -> tuple[dict, list[Flow]]:
    """{account id: [flows]} and the flows no active account takes (money the dashboard can't place)."""
    accounts = list(accounts)
    out: dict = defaultdict(list)
    orphans = []
    for f in flows:
        target = next((a for a in accounts if a.store_id and _takes(a, f)), None) or next((a for a in accounts if _takes(a, f)), None)
        if target is None:
            orphans.append(f)
        else:
            out[target.id].append(f)
    return out, orphans


def _manual(account_ids, start: date, end: date):
    return Transaction.objects.filter(voided_at__isnull=True, occurred_on__gte=start, occurred_on__lte=end).filter(
        Q(account_id__in=account_ids) | Q(to_account_id__in=account_ids))


def manual_effect(tx: Transaction, account_id) -> Decimal:
    if tx.kind == TxKind.INCOME:
        return tx.amount if tx.account_id == account_id else ZERO
    if tx.kind == TxKind.EXPENSE:
        return -tx.amount if tx.account_id == account_id else ZERO
    if tx.account_id == account_id:
        return -tx.amount
    return tx.amount if tx.to_account_id == account_id else ZERO


def balances(as_of: date | None = None, accounts=None) -> dict:
    """{account id: {"balance", "in_month", "out_month"}} at the end of `as_of` (today by default)."""
    from django.utils import timezone

    as_of = as_of or timezone.localdate()
    accounts = list(accounts if accounts is not None else MoneyAccount.objects.filter(is_active=True))
    if not accounts:
        return {}
    first = min(a.opening_date for a in accounts)
    month0 = as_of.replace(day=1)
    routed, _orph = route(auto_flows(first, as_of), [a for a in MoneyAccount.objects.filter(is_active=True)])
    out = {}
    txs = list(_manual([a.id for a in accounts], first, as_of))
    for a in accounts:
        bal, inn, outt = a.opening_balance, ZERO, ZERO
        for f in routed.get(a.id, []):
            if f.day < a.opening_date:
                continue
            bal += f.amount
            if f.day >= month0:
                inn, outt = (inn + f.amount, outt) if f.amount > 0 else (inn, outt - f.amount)
        for t in txs:
            if t.occurred_on < a.opening_date:
                continue
            eff = manual_effect(t, a.id)
            bal += eff
            if t.occurred_on >= month0 and eff:
                inn, outt = (inn + eff, outt) if eff > 0 else (inn, outt - eff)
        out[a.id] = {"balance": bal, "in_month": inn, "out_month": outt}
    return out


def statement(account: MoneyAccount, start: date, end: date) -> dict:
    """Opening balance at `start`, every movement (automatic ones one row per day and source), closing balance."""
    start = max(start, account.opening_date)
    before = balances(start - timedelta(days=1), [account])[account.id]["balance"] if start > account.opening_date else account.opening_balance
    routed, _o = route(auto_flows(start, end), MoneyAccount.objects.filter(is_active=True))
    rows = []
    for f in routed.get(account.id, []):
        rows.append({"day": f.day, "auto": True, "title": f.label, "detail": ", ".join(r for r in f.refs if r) + (f" (+{f.count - len(f.refs)})" if f.count > len(f.refs) else ""),
                     "amount": f.amount, "count": f.count})
    for t in _manual([account.id], start, end).select_related("category", "account", "to_account"):
        eff = manual_effect(t, account.id)
        if t.kind == TxKind.TRANSFER:
            title = f"O'tkazma → {t.to_account}" if eff < 0 else f"O'tkazma ← {t.account}"
        else:
            title = t.category.name if t.category else t.get_kind_display()
        rows.append({"day": t.occurred_on, "auto": False, "title": title, "detail": " · ".join(p for p in (t.counterparty, t.note) if p), "amount": eff, "tx": t})
    rows.sort(key=lambda r: (r["day"], 0 if r["auto"] else 1))
    run = before
    for r in rows:
        run += r["amount"]
        r["balance"] = run
    inn = sum((r["amount"] for r in rows if r["amount"] > 0), ZERO)
    out = -sum((r["amount"] for r in rows if r["amount"] < 0), ZERO)
    return {"opening": before, "closing": run, "in": inn, "out": out, "rows": list(reversed(rows)), "start": start, "end": end}


def manual_totals(start: date, end: date) -> dict:
    """{(kind, category id): amount} of manual income/expenses in the period (transfers move money, they aren't income)."""
    rows = (Transaction.objects.filter(voided_at__isnull=True, occurred_on__gte=start, occurred_on__lte=end).exclude(kind=TxKind.TRANSFER)
            .values("kind", "category_id").annotate(s=Sum("amount")))
    return {(r["kind"], r["category_id"]): r["s"] or ZERO for r in rows}
