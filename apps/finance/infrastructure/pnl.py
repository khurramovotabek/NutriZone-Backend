"""
Profit & loss by month and cash flow by month. Revenue and cost of goods come from the same numbers as Biznes
analitikasi (business_analytics), so the two pages never disagree.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum

from apps.finance.infrastructure import ledger
from apps.finance.infrastructure.models import SOURCES, Category, CategoryKind, MoneyAccount, PnlSection, TxKind

ZERO = Decimal(0)
MONTHS = {
    "uz": ("yan", "fev", "mar", "apr", "may", "iyn", "iyl", "avg", "sen", "okt", "noy", "dek"),
    "ru": ("янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"),
    "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
}


def month_start(d: date) -> date:
    return d.replace(day=1)


def next_month(m: date) -> date:
    return (m.replace(day=28) + timedelta(days=4)).replace(day=1)


def months_back(last: date, n: int) -> list[date]:
    out = [month_start(last)]
    while len(out) < n:
        out.insert(0, month_start(out[0] - timedelta(days=1)))
    return out


def month_label(m: date) -> str:
    from django.utils.translation import get_language

    names = MONTHS.get((get_language() or "uz")[:2], MONTHS["uz"])
    return f"{names[m.month - 1]} {m.year}"


def _sales(start: date, end: date) -> dict:
    from apps.platform.infrastructure import business_analytics as ba
    from apps.stores.infrastructure.count_service import cost_info

    base = ba._base(ledger.day_start(start), ledger.day_start(end + timedelta(days=1)))
    coins = sum((r["coins_kept"] for r in base["kept"]), ZERO)
    lines = ba._sold_lines(base)
    info = cost_info([a["variant"] for a in lines.values() if a["variant"]])
    cogs, covered, total = ZERO, ZERO, ZERO
    for a in lines.values():
        total += a["revenue"]
        cost, source = info.get(a["variant"], (ZERO, None)) if a["variant"] else (ZERO, None)
        if source in ba.RELIABLE_COST and cost:
            cogs += cost * a["units"]
            covered += a["revenue"]
    # goods whose cost is unknown: costed at the known part's average cost ratio, so profit isn't inflated
    if total and covered and covered < total:
        cogs = cogs / covered * total
    return {"pos": base["pos_revenue"], "online": base["online_revenue"], "coins": coins, "cogs": cogs,
            "coverage": int(round(covered / total * 100)) if total else None}


def _writeoffs(start: date, end: date) -> Decimal:
    from apps.stores.infrastructure.models import WriteOff

    return WriteOff.objects.filter(status="approved", decided_at__gte=ledger.day_start(start), decided_at__lt=ledger.day_start(end + timedelta(days=1))).aggregate(s=Sum("total_value"))["s"] or ZERO


def _payroll(m: date) -> Decimal:
    from apps.stores.infrastructure.models import CashierPayout

    return CashierPayout.objects.filter(month=m).aggregate(s=Sum("total"))["s"] or ZERO


def _courier_fees(start: date, end: date) -> Decimal:
    from apps.ordering.infrastructure.models import DeliveryAssignment

    return DeliveryAssignment.objects.filter(
        fee__isnull=False, order__status_history__to_status="delivered",
        order__status_history__changed_at__gte=ledger.day_start(start), order__status_history__changed_at__lt=ledger.day_start(end + timedelta(days=1)),
    ).distinct().aggregate(s=Sum("fee"))["s"] or ZERO


def pnl(months: list[date]) -> dict:
    """Rows × months. Each row: key, label, kind (head/line/sub/total), values (list, one per month), total."""
    from django.utils import timezone

    today = timezone.localdate()
    cats = {c.id: c for c in Category.objects.all()}
    cols = []
    for m in months:
        end = min(next_month(m) - timedelta(days=1), today)
        s = _sales(m, end) if m <= today else {"pos": ZERO, "online": ZERO, "coins": ZERO, "cogs": ZERO, "coverage": None}
        manual = ledger.manual_totals(m, end) if m <= today else {}
        cols.append({"m": m, "s": s, "manual": manual, "writeoffs": _writeoffs(m, end) if m <= today else ZERO,
                     "payroll": _payroll(m), "courier": _courier_fees(m, end) if m <= today else ZERO})

    rows: list[dict] = []

    def row(key, label, values, kind="line", sign=1, icon="", color=""):
        values = [v * sign for v in values]
        rows.append({"key": key, "label": label, "values": values, "total": sum(values, ZERO), "kind": kind, "icon": icon, "color": color})
        return values

    pos = row("pos", "Do'kon kassalari savdosi", [c["s"]["pos"] for c in cols], icon="fa-cash-register")
    web = row("online", "Sayt va Telegram buyurtmalari", [c["s"]["online"] for c in cols], icon="fa-globe")
    coins = row("coins", "Coins bilan to'langan qism", [c["s"]["coins"] for c in cols], sign=-1, icon="fa-coins")
    revenue = row("revenue", "Sof tushum", [a + b + c for a, b, c in zip(pos, web, coins, strict=True)], kind="sub")
    cogs = row("cogs", "Sotilgan tovar tannarxi", [c["s"]["cogs"] for c in cols], sign=-1, icon="fa-boxes-stacked")
    gross = row("gross", "Yalpi foyda", [a + b for a, b in zip(revenue, cogs, strict=True)], kind="total")

    opex_total = [ZERO] * len(cols)

    def add_opex(key, label, values, icon, color=""):
        vals = row(key, label, values, sign=-1, icon=icon, color=color)
        for i, v in enumerate(vals):
            opex_total[i] += v

    rows.append({"key": "opex_head", "label": "Operatsion xarajatlar", "kind": "head"})
    add_opex("payroll", "Kassirlar ish haqi (KPI bilan)", [c["payroll"] for c in cols], "fa-user-tie")
    add_opex("writeoffs", "Hisobdan chiqarilgan tovar", [c["writeoffs"] for c in cols], "fa-trash-can")
    add_opex("courier", "Kuryer xizmati", [c["courier"] for c in cols], "fa-motorcycle")
    expense_cats = [c for c in cats.values() if c.kind == CategoryKind.EXPENSE and c.section == PnlSection.OPEX]
    for cat in sorted(expense_cats, key=lambda c: (c.sort_order, c.name)):
        vals = [c["manual"].get((TxKind.EXPENSE, cat.id), ZERO) for c in cols]
        if any(vals):
            add_opex(f"cat_{cat.id}", cat.name, vals, cat.icon, cat.color)
    row("opex", "Jami operatsion xarajatlar", opex_total, kind="sub")
    operating = row("operating", "Operatsion foyda", [a + b for a, b in zip(gross, opex_total, strict=True)], kind="total")

    other = [ZERO] * len(cols)
    for cat in cats.values():
        if cat.section == PnlSection.OTHER_INCOME:
            vals = [c["manual"].get((cat.kind, cat.id), ZERO) * (1 if cat.kind == CategoryKind.INCOME else -1) for c in cols]
            if any(vals):
                row(f"cat_{cat.id}", cat.name, vals, icon=cat.icon, color=cat.color)
                other = [a + b for a, b in zip(other, vals, strict=True)]
    taxes = [ZERO] * len(cols)
    for cat in cats.values():
        if cat.section == PnlSection.TAX:
            vals = [-c["manual"].get((CategoryKind.EXPENSE, cat.id), ZERO) for c in cols]
            if any(vals):
                row(f"cat_{cat.id}", cat.name, vals, icon=cat.icon, color=cat.color)
                taxes = [a + b for a, b in zip(taxes, vals, strict=True)]
    net = row("net", "Sof foyda", [a + b + c for a, b, c in zip(operating, other, taxes, strict=True)], kind="grand")
    margins = [round(float(n / r * 100), 1) if r else None for n, r in zip(net, revenue, strict=True)]
    gross_margins = [round(float(g / r * 100), 1) if r else None for g, r in zip(gross, revenue, strict=True)]
    return {"months": [{"m": c["m"], "label": month_label(c["m"]), "coverage": c["s"]["coverage"]} for c in cols], "rows": rows,
            "margins": margins, "gross_margins": gross_margins, "revenue": revenue, "net": net, "gross": gross, "opex": opex_total}


def cashflow(months: list[date]) -> dict:
    """Money in and out by month: automatic sources + manual operations by category (transfers between own accounts cancel out)."""
    from django.utils import timezone

    today = timezone.localdate()
    start, end = months[0], min(next_month(months[-1]) - timedelta(days=1), today)
    idx = {m: i for i, m in enumerate(months)}
    n = len(months)
    inflow: dict = defaultdict(lambda: [ZERO] * n)
    outflow: dict = defaultdict(lambda: [ZERO] * n)
    labels: dict = {}
    for f in ledger.auto_flows(start, end):
        i = idx[month_start(f.day)]
        key = f"src_{f.source}"
        labels[key] = (str(SOURCES[f.source][0]), "fa-bolt")
        if f.amount >= 0:
            inflow[key][i] += f.amount
        else:
            outflow[key][i] -= f.amount
    cats = {c.id: c for c in Category.objects.all()}
    from apps.finance.infrastructure.models import Transaction

    for t in Transaction.objects.filter(voided_at__isnull=True, occurred_on__gte=start, occurred_on__lte=end).exclude(kind=TxKind.TRANSFER).values("kind", "category_id", "occurred_on", "amount"):
        i = idx[month_start(t["occurred_on"])]
        cat = cats.get(t["category_id"])
        key = f"cat_{t['category_id']}"
        labels[key] = (cat.name if cat else "—", cat.icon if cat else "fa-tag")
        (inflow if t["kind"] == TxKind.INCOME else outflow)[key][i] += t["amount"]

    def block(d):
        out = [{"key": k, "label": labels[k][0], "icon": labels[k][1], "values": v, "total": sum(v, ZERO)} for k, v in d.items()]
        return sorted(out, key=lambda r: -r["total"])

    ins, outs = block(inflow), block(outflow)
    tin = [sum((r["values"][i] for r in ins), ZERO) for i in range(n)]
    tout = [sum((r["values"][i] for r in outs), ZERO) for i in range(n)]
    net = [a - b for a, b in zip(tin, tout, strict=True)]
    accounts = list(MoneyAccount.objects.filter(is_active=True))
    closing = []
    for m in months:
        last = min(next_month(m) - timedelta(days=1), today)
        closing.append(sum((v["balance"] for v in ledger.balances(last, accounts).values()), ZERO) if accounts and last >= start else ZERO)
    return {"months": [{"m": m, "label": month_label(m)} for m in months], "inflow": ins, "outflow": outs, "total_in": tin, "total_out": tout, "net": net, "closing": closing}
