"""
Moliya → analysis layer, built from the same ledger / P&L numbers the report pages show (never a second truth):

* pace()     -- this month so far vs the same days of last month (revenue, profit, money in/out) + month-end forecast
               by run-rate.
* daily()    -- the current month day by day: money in, out and the running net, with last month's running money-in
               on the same day numbers for comparison.
* runway()   -- how many months the money on the accounts lasts at the average net outflow of the last 3 full months.
* aging()    -- supplier debt by how late it is (not due / 1–30 / 31–60 / 61–90 / 90+ days), receipt by receipt.
* advice()   -- the short list of things worth acting on, each with a link to the page that fixes it.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.urls import reverse

from apps.finance.infrastructure import ledger, pnl
from apps.finance.infrastructure.models import Category, CategoryKind, PnlSection, Transaction, TxKind

ZERO = Decimal(0)


def pct_change(cur, prev):
    """+12.5 / −8.0 / None (nothing to compare with)."""
    cur, prev = Decimal(cur or 0), Decimal(prev or 0)
    if not prev:
        return None
    return round(float((cur - prev) / abs(prev) * 100), 1)


def _payroll_paid(start: date, end: date) -> Decimal:
    from apps.stores.infrastructure.models import CashierPayout

    return CashierPayout.objects.filter(paid_at__gte=ledger.day_start(start), paid_at__lt=ledger.day_start(end + timedelta(days=1))).aggregate(s=Sum("total"))["s"] or ZERO


def period(start: date, end: date) -> dict:
    """P&L of any date range with the same rules as pnl.pnl() (payroll by payout day so short ranges compare fairly)."""
    s = pnl._sales(start, end)
    cats = {c.id: c for c in Category.objects.all()}
    opex = taxes = other = ZERO
    for (kind, cid), v in ledger.manual_totals(start, end).items():
        c = cats.get(cid)
        section = c.section if c else PnlSection.OPEX
        if section == PnlSection.CAPITAL:
            continue
        if section == PnlSection.TAX and kind == CategoryKind.EXPENSE:
            taxes += v
        elif section == PnlSection.OTHER_INCOME:
            other += v if kind == CategoryKind.INCOME else -v
        elif section == PnlSection.OPEX and kind == CategoryKind.EXPENSE:
            opex += v
    payroll, writeoffs, courier = _payroll_paid(start, end), pnl._writeoffs(start, end), pnl._courier_fees(start, end)
    revenue = s["pos"] + s["online"] - s["coins"]
    gross = revenue - s["cogs"]
    expenses = opex + payroll + writeoffs + courier
    net = gross - expenses - taxes + other
    return {"revenue": revenue, "cogs": s["cogs"], "gross": gross, "expenses": expenses, "manual_opex": opex, "net": net, "coverage": s["coverage"],
            "pos": s["pos"], "online": s["online"]}


def cash(start: date, end: date) -> tuple[Decimal, Decimal]:
    """Money in, money out of the business in the range (automatic flows + manual operations; transfers cancel out)."""
    inn = out = ZERO
    for f in ledger.auto_flows(start, end):
        if f.amount > 0:
            inn += f.amount
        else:
            out -= f.amount
    for t in Transaction.objects.filter(voided_at__isnull=True, occurred_on__gte=start, occurred_on__lte=end).exclude(kind=TxKind.TRANSFER).values("kind", "amount"):
        if t["kind"] == TxKind.INCOME:
            inn += t["amount"]
        else:
            out += t["amount"]
    return inn, out


def pace(today: date) -> dict:
    m0 = today.replace(day=1)
    prev0 = pnl.months_back(m0, 2)[0]
    prev_end = min(prev0 + timedelta(days=today.day - 1), m0 - timedelta(days=1))
    cur, prev = period(m0, today), period(prev0, prev_end)
    cin, cout = cash(m0, today)
    pin, pout = cash(prev0, prev_end)
    days_in = (pnl.next_month(m0) - m0).days
    k = Decimal(days_in) / Decimal(today.day)
    return {
        "cur": cur, "prev": prev, "cash_in": cin, "cash_out": cout, "prev_in": pin, "prev_out": pout,
        "d_revenue": pct_change(cur["revenue"], prev["revenue"]), "d_net": pct_change(cur["net"], prev["net"]),
        "d_in": pct_change(cin, pin), "d_out": pct_change(cout, pout), "d_expenses": pct_change(cur["expenses"], prev["expenses"]),
        "forecast_revenue": (cur["revenue"] * k).quantize(Decimal(1)), "forecast_net": (cur["net"] * k).quantize(Decimal(1)),
        "day": today.day, "days_in": days_in, "progress": round(today.day * 100 / days_in),
        "margin": round(float(cur["net"] / cur["revenue"] * 100), 1) if cur["revenue"] else None,
        "gross_margin": round(float(cur["gross"] / cur["revenue"] * 100), 1) if cur["revenue"] else None,
        "prev_label": f"{prev0:%d.%m}–{prev_end:%d.%m}",
    }


def _daily_flows(start: date, end: date) -> tuple[dict, dict]:
    inn, out = defaultdict(lambda: ZERO), defaultdict(lambda: ZERO)
    for f in ledger.auto_flows(start, end):
        if f.amount > 0:
            inn[f.day] += f.amount
        else:
            out[f.day] -= f.amount
    for t in Transaction.objects.filter(voided_at__isnull=True, occurred_on__gte=start, occurred_on__lte=end).exclude(kind=TxKind.TRANSFER).values("kind", "amount", "occurred_on"):
        (inn if t["kind"] == TxKind.INCOME else out)[t["occurred_on"]] += t["amount"]
    return inn, out


def daily(today: date) -> dict:
    m0 = today.replace(day=1)
    prev0 = pnl.months_back(m0, 2)[0]
    inn, out = _daily_flows(m0, today)
    pin, _pout = _daily_flows(prev0, m0 - timedelta(days=1))
    labels, s_in, s_out, s_net, s_prev = [], [], [], [], []
    run = prun = ZERO
    best = None
    for k in range((pnl.next_month(m0) - m0).days):
        d = m0 + timedelta(days=k)
        pd_ = prev0 + timedelta(days=k)
        if pd_ < m0:
            prun += pin.get(pd_, ZERO)
        labels.append(f"{d:%d}")
        s_prev.append(float(prun))
        if d > today:
            continue
        run += inn.get(d, ZERO) - out.get(d, ZERO)
        s_in.append(float(inn.get(d, ZERO)))
        s_out.append(float(out.get(d, ZERO)))
        s_net.append(float(run))
        if inn.get(d) and (best is None or inn[d] > best[1]):
            best = (d, inn[d])
    cum_in = [sum(s_in[: i + 1]) for i in range(len(s_in))]
    return {"labels": labels, "in": s_in, "out": s_out, "net": s_net, "cum_in": cum_in, "prev_cum_in": s_prev,
            "best_day": {"day": best[0], "amount": best[1]} if best else None}


def runway(total_cash: Decimal, today: date) -> dict:
    """Average of the last 3 full months: money out per month, net per month, and how long today's money lasts."""
    last_full = today.replace(day=1) - timedelta(days=1)
    months = pnl.months_back(last_full, 3)
    flow = pnl.cashflow(months)
    active = [i for i in range(len(months)) if flow["total_in"][i] or flow["total_out"][i]]
    if not active:
        return {"avg_out": ZERO, "avg_net": ZERO, "months": None, "basis": 0}
    avg_out = sum((flow["total_out"][i] for i in active), ZERO) / len(active)
    avg_net = sum((flow["net"][i] for i in active), ZERO) / len(active)
    months_left = round(float(total_cash / -avg_net), 1) if avg_net < 0 and total_cash > 0 else None
    cover = round(float(total_cash / avg_out), 1) if avg_out > 0 and total_cash > 0 else None
    return {"avg_out": avg_out.quantize(Decimal(1)), "avg_net": avg_net.quantize(Decimal(1)), "months": months_left, "cover": cover, "basis": len(active)}


AGING = (("not_due", "Muddati kelmagan", "#0ea5e9"), ("d30", "1–30 kun", "#f59e0b"), ("d60", "31–60 kun", "#f97316"),
         ("d90", "61–90 kun", "#ef4444"), ("d90p", "90+ kun", "#991b1b"))


def aging(today: date) -> dict:
    from apps.stores.infrastructure import supplier_service
    from apps.stores.infrastructure.models import StockReceipt, Supplier

    bal = supplier_service.balances()
    ids = [rid for b in bal.values() for rid, st in b.receipt_status.items() if st["open"] > 0]
    due = dict(StockReceipt.objects.filter(id__in=ids).values_list("id", "due_date"))
    names = dict(Supplier.objects.filter(id__in=list(bal)).values_list("id", "name"))
    buckets = {k: {"key": k, "label": label, "color": color, "amount": ZERO, "count": 0} for k, label, color in AGING}
    per_supplier = []
    for sid, b in bal.items():
        row = {"id": sid, "name": names.get(sid, "—"), **{k: ZERO for k, _l, _c in AGING}, "total": ZERO, "late_days": 0}
        for rid, st in b.receipt_status.items():
            if st["open"] <= 0:
                continue
            d = due.get(rid)
            days = (today - d).days if d else 0
            key = "not_due" if days <= 0 else "d30" if days <= 30 else "d60" if days <= 60 else "d90" if days <= 90 else "d90p"
            buckets[key]["amount"] += st["open"]
            buckets[key]["count"] += 1
            row[key] += st["open"]
            row["total"] += st["open"]
            row["late_days"] = max(row["late_days"], days)
        if row["total"] > 0:
            per_supplier.append(row)
    total = sum((b["amount"] for b in buckets.values()), ZERO)
    for b in buckets.values():
        b["pct"] = round(float(b["amount"] / total * 100), 1) if total else 0
        b["w"] = f"{b['pct']:.2f}"  # CSS width (no locale comma)
    per_supplier.sort(key=lambda r: (-r["late_days"], -r["total"]))
    return {"buckets": list(buckets.values()), "total": total, "suppliers": per_supplier}


def courier_cash() -> list[dict]:
    """Cash collected by couriers for delivered orders and not handed in yet (Kuryerlar → settle)."""
    from apps.ordering.infrastructure import couriers
    from apps.ordering.infrastructure.models import Courier

    people = list(Courier.objects.all())
    st = couriers.stats(people)
    out = [{"name": str(c), "cash": st[c.id]["cash"], "orders": st[c.id]["cash_orders"], "url": reverse("admin:ordering_courier_change", args=[c.pk])}
           for c in people if st[c.id]["cash"] > 0]
    return sorted(out, key=lambda r: -r["cash"])


def top_expenses(start: date, end: date, limit: int = 6) -> list[dict]:
    """The biggest expense lines of the range: manual categories + the automatic ones (payroll, write-offs, couriers, purchases)."""
    cats = {c.id: c for c in Category.objects.all()}
    rows = []
    for (kind, cid), v in ledger.manual_totals(start, end).items():
        if kind != CategoryKind.EXPENSE or not v:
            continue
        c = cats.get(cid)
        rows.append({"label": c.name if c else "—", "icon": c.icon if c else "fa-tag", "color": c.color if c else "#64748b", "value": v})
    for label, icon, color, v in (("Kassirlar ish haqi", "fa-user-tie", "#7c3aed", _payroll_paid(start, end)),
                                  ("Hisobdan chiqarilgan tovar", "fa-trash-can", "#ef4444", pnl._writeoffs(start, end)),
                                  ("Kuryer xizmati", "fa-motorcycle", "#0ea5e9", pnl._courier_fees(start, end))):
        if v:
            rows.append({"label": label, "icon": icon, "color": color, "value": v})
    rows.sort(key=lambda r: -r["value"])
    rows = rows[:limit]
    lead = rows[0]["value"] if rows else Decimal(1)
    total = sum((r["value"] for r in rows), ZERO)
    for r in rows:
        r["pct"] = max(3, int(r["value"] * 100 / lead)) if lead else 0
        r["share"] = round(float(r["value"] / total * 100)) if total else 0
    return rows


def advice(*, p: dict, run: dict, orphans: list, negative: list, over_budget: list, debts: dict, couriers: list, coins: Decimal, total_cash: Decimal,
           manual_count: int, today: date) -> list[dict]:
    """What is worth acting on now -- most urgent first. level: bad / warn / info / ok."""
    from apps.finance.infrastructure.views import money

    out = []

    def add(level, icon, text, url="", link=""):
        out.append({"level": level, "icon": icon, "text": text, "url": url, "link": link})

    for c in negative:
        add("bad", "fa-circle-exclamation", f"«{c['a'].name}» qoldig'i manfiy: {c['balance']} so'm — boshlang'ich qoldiq yoki operatsiyalarda xato bor.", c["url"], "Ko'chirma")
    if orphans:
        add("bad", "fa-link-slash", f"{len(orphans)} ta avtomatik manba hech bir hisobga bog'lanmagan — qoldiqlar to'liq emas.",
            reverse("admin:finance_moneyaccount_changelist"), "Hisoblar")
    if debts.get("overdue_raw"):
        add("bad", "fa-hourglass-end", f"Yetkazib beruvchilarga {debts['overdue']} so'm qarzning to'lov muddati o'tgan.", reverse("admin:nz_finance_debts"), "Qarzlar")
    if p["cur"]["net"] < 0 and p["cur"]["revenue"]:
        add("bad", "fa-arrow-trend-down", f"Bu oy hozircha zarar: {money(p['cur']['net'])} so'm. Xarajatlar tarkibini tekshiring.", reverse("admin:nz_finance_pnl"), "Foyda va zarar")
    if run.get("months") is not None and run["months"] < 3:
        add("bad" if run["months"] < 1.5 else "warn", "fa-gauge-simple-high",
            f"Oxirgi oylardagi o'rtacha sof chiqim bilan hisobdagi pul taxminan {run['months']} oyga yetadi.", reverse("admin:nz_finance_cashflow"), "Pul oqimi")
    for b in over_budget[:3]:
        add("warn", "fa-fire", f"«{b['c'].name}» budjetdan oshdi: {b['actual_fmt']} / {b['plan_fmt']} so'm ({b['pct']}%).", reverse("admin:nz_finance_budget"), "Budjet")
    if p["d_revenue"] is not None and p["d_revenue"] <= -15:
        add("warn", "fa-chart-line", f"Tushum o'tgan oyning shu kunlariga nisbatan {abs(p['d_revenue'])}% kam.", reverse("admin:nz_finance_pnl"), "Foyda va zarar")
    if p["d_expenses"] is not None and p["d_expenses"] >= 25:
        add("warn", "fa-arrow-up-right-dots", f"Xarajatlar o'tgan oyning shu kunlariga nisbatan {p['d_expenses']}% ko'p.", reverse("admin:finance_transaction_changelist"), "Operatsiyalar")
    cov = p["cur"]["coverage"]
    if cov is not None and cov < 90:
        add("warn", "fa-tags", f"Bu oy sotilgan tovarlarning faqat {cov}% tannarxi ma'lum — foyda taxminiy. Kirim hujjatlarida narxlarni to'ldiring.",
            "/django-admin/stores/stockreceipt/", "Kirimlar")
    cash_held = sum((c["cash"] for c in couriers), ZERO)
    if cash_held:
        add("warn", "fa-motorcycle", f"Kuryerlar qo'lida {money(cash_held)} so'm naqd turibdi — kassaga topshirilmagan.", reverse("admin:ordering_courier_changelist"), "Kuryerlar")
    if today.day >= 10 and not manual_count:
        add("info", "fa-receipt", "Bu oy qo'lda birorta xarajat kiritilmagan (ijara, kommunal, reklama…) — sof foyda haqiqatdan yuqori ko'rinadi.",
            reverse("admin:finance_transaction_add") + "?kind=expense", "Xarajat kiritish")
    if coins and total_cash and coins > total_cash * Decimal("0.2"):
        add("info", "fa-coins", f"Mijozlar hamyonidagi coinlar ({money(coins)}) hisobdagi pulning 20% dan ko'p — bu kelajakdagi chegirma majburiyati.",
            "/django-admin/loyalty/wallet/", "Hamyonlar")
    if p["d_revenue"] is not None and p["d_revenue"] >= 15:
        add("ok", "fa-rocket", f"Tushum o'tgan oyning shu kunlariga nisbatan {p['d_revenue']}% ko'p.", reverse("admin:nz_finance_pnl"), "Foyda va zarar")
    if not out:
        add("ok", "fa-circle-check", "Hammasi joyida: manfiy hisob, muddati o'tgan qarz va budjetdan oshish yo'q.")
    order = {"bad": 0, "warn": 1, "info": 2, "ok": 3}
    return sorted(out, key=lambda a: order[a["level"]])
