"""
Suppliers and what we owe them (accounts payable).

* A goods receipt (Kirim) at cost is a purchase from its supplier: it raises the debt and falls due
  `payment_terms_days` after the receipt date (StockReceipt.due_date).
* A SupplierPayment lowers the debt. Payments settle the oldest receipts first (FIFO), which gives every
  receipt a status -- paid / partly paid / unpaid / overdue -- and the overdue amount per supplier.
* The statement (solishtirma dalolatnoma / akt sverka) is the chronological list of receipts and payments
  with a running balance.
Receipts without a cost (value 0) don't create debt -- the cost has to be entered at receiving.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Max, Sum
from django.utils import timezone

from apps.stores.infrastructure.models import PaymentMethod, StockReceipt, Supplier, SupplierPayment
from common.exceptions import ValidationFailed

ZERO = Decimal(0)


def resolve(name: str) -> Supplier | None:
    """The supplier typed on a goods receipt: an existing one (case-insensitive) or a new record."""
    name = " ".join((name or "").split())[:160]
    if not name:
        return None
    found = Supplier.objects.filter(name__iexact=name).first()
    return found or Supplier.objects.create(name=name)


def due_date(supplier: Supplier | None, received: date) -> date:
    return received + timedelta(days=supplier.payment_terms_days if supplier else 0)


def add_payment(supplier: Supplier, actor: str, amount, paid_on=None, method: str = PaymentMethod.BANK, reference: str = "", note: str = "") -> SupplierPayment:
    try:
        amount = Decimal(str(amount).replace(" ", "").replace(",", "."))
    except Exception as exc:  # noqa: BLE001 - decimal.InvalidOperation and friends
        raise ValidationFailed("Enter the amount as a number.") from exc
    if amount <= 0 or amount > Decimal("999999999999"):
        raise ValidationFailed("The amount must be positive.")
    if method not in PaymentMethod.values:
        raise ValidationFailed("Unknown payment method.")
    if isinstance(paid_on, str) and paid_on:
        try:
            paid_on = date.fromisoformat(paid_on[:10])
        except ValueError as exc:
            raise ValidationFailed("Invalid date.") from exc
    paid_on = paid_on or timezone.localdate()
    if paid_on > timezone.localdate():
        raise ValidationFailed("A payment can't be in the future.")
    with transaction.atomic():
        return SupplierPayment.objects.create(supplier=supplier, amount=amount, paid_on=paid_on, method=method, reference=(reference or "")[:60],
                                              note=(note or "")[:255], created_by=actor[:150])


@dataclass
class Balance:
    purchased: Decimal = ZERO
    paid: Decimal = ZERO
    overdue: Decimal = ZERO
    receipts: int = 0
    last_receipt: object = None
    oldest_overdue: date | None = None
    receipt_status: dict = field(default_factory=dict)  # receipt id -> {"paid", "open", "status"}

    @property
    def debt(self) -> Decimal:
        return self.purchased - self.paid


def _settle(receipts: list, paid_total: Decimal, today: date) -> tuple[Decimal, date | None, dict]:
    """Applies the paid total to receipts oldest first; returns (overdue amount, oldest overdue due date, status per receipt)."""
    left, overdue, oldest, status = paid_total, ZERO, None, {}
    for r in receipts:
        value = r["total_value"] or ZERO
        covered = min(value, max(left, ZERO))
        left -= covered
        open_ = value - covered
        if value == 0:
            state = "nocost"
        elif open_ == 0:
            state = "paid"
        elif r["due_date"] and r["due_date"] < today:
            state = "overdue"
            overdue += open_
            oldest = oldest or r["due_date"]
        else:
            state = "partial" if covered else "open"
        status[r["id"]] = {"paid": covered, "open": open_, "status": state}
    return overdue, oldest, status


def balances(supplier_ids=None) -> dict:
    """supplier id -> Balance (all suppliers, or the given ones)."""
    today = timezone.localdate()
    receipts = StockReceipt.objects.filter(supplier_ref__isnull=False)
    payments = SupplierPayment.objects.all()
    if supplier_ids is not None:
        receipts = receipts.filter(supplier_ref_id__in=list(supplier_ids))
        payments = payments.filter(supplier_id__in=list(supplier_ids))
    paid = dict(payments.values_list("supplier_id").annotate(s=Sum("amount")))
    by_supplier: dict = {}
    for r in receipts.order_by("created_at").values("id", "supplier_ref_id", "total_value", "due_date", "created_at"):
        by_supplier.setdefault(r["supplier_ref_id"], []).append(r)
    out = {}
    for sid in set(by_supplier) | set(paid):
        rows = by_supplier.get(sid, [])
        b = Balance(purchased=sum((r["total_value"] or ZERO for r in rows), ZERO), paid=paid.get(sid) or ZERO, receipts=len(rows),
                    last_receipt=rows[-1]["created_at"] if rows else None)
        b.overdue, b.oldest_overdue, b.receipt_status = _settle(rows, b.paid, today)
        out[sid] = b
    return out


def balance(supplier: Supplier) -> Balance:
    return balances([supplier.id]).get(supplier.id) or Balance()


def statement(supplier: Supplier, start: date | None = None, end: date | None = None) -> dict:
    """Chronological receipts (debit: we owe more) and payments (credit) with the running balance; opening balance before `start`."""
    rows = []
    for r in StockReceipt.objects.filter(supplier_ref=supplier).select_related("store"):
        rows.append({"date": timezone.localtime(r.created_at).date(), "at": r.created_at, "kind": "receipt", "doc": r.number, "obj": r,
                     "text": f"{r.store.name}" + (f" · № {r.invoice_number}" if r.invoice_number else ""), "debit": r.total_value or ZERO, "credit": ZERO})
    for p in SupplierPayment.objects.filter(supplier=supplier):
        rows.append({"date": p.paid_on, "at": p.created_at, "kind": "payment", "doc": p.reference or "—", "obj": p,
                     "text": p.get_method_display() + (f" · {p.note}" if p.note else ""), "debit": ZERO, "credit": p.amount})
    rows.sort(key=lambda x: (x["date"], x["at"]))
    opening = sum((x["debit"] - x["credit"] for x in rows if start and x["date"] < start), ZERO)
    shown = [x for x in rows if (not start or x["date"] >= start) and (not end or x["date"] <= end)]
    running = opening
    for x in shown:
        running += x["debit"] - x["credit"]
        x["balance"] = running
    return {"opening": opening, "rows": shown, "debit": sum((x["debit"] for x in shown), ZERO), "credit": sum((x["credit"] for x in shown), ZERO), "closing": running}


def top_products(supplier: Supplier, limit: int = 12) -> list[dict]:
    """What we buy from this supplier: units, spend, last and previous unit cost (price trend)."""
    from apps.stores.infrastructure.models import StockReceiptItem

    items = StockReceiptItem.objects.filter(receipt__supplier_ref=supplier)
    agg = list(items.values("product_variant_id").annotate(units=Sum("quantity"), receipts=Count("receipt", distinct=True), last=Max("receipt__created_at")).order_by("-units")[:limit])
    costs: dict = {}
    for row in items.filter(product_variant_id__in=[a["product_variant_id"] for a in agg], unit_cost__isnull=False).order_by("product_variant_id", "-receipt__created_at").values("product_variant_id", "unit_cost", "quantity", "receipt_id"):
        costs.setdefault(row["product_variant_id"], []).append(row)
    for a in agg:
        hist = costs.get(a["product_variant_id"], [])
        a["last_cost"] = hist[0]["unit_cost"] if hist else None
        # the price trend compares with an EARLIER receipt (lines of the same receipt aren't a price change)
        a["prev_cost"] = next((h["unit_cost"] for h in hist if h["receipt_id"] != hist[0]["receipt_id"]), None) if hist else None
        a["spend"] = sum((h["unit_cost"] * h["quantity"] for h in hist), ZERO)
    return agg
