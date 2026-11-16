"""Moliya pages: overview, P&L, cash flow, budget, debts, account statement (+ Excel). URLs: install() below."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Sum
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone

from apps.finance.infrastructure import ledger, pnl
from apps.finance.infrastructure.models import (
    SOURCES, BudgetLine, Category, CategoryKind, MoneyAccount, PnlSection, Transaction, TxKind,
)

ZERO = Decimal(0)
TABS = (
    ("overview", "Moliya paneli", "fa-gauge-high", "admin:nz_finance"),
    ("transactions", "Operatsiyalar", "fa-right-left", "admin:finance_transaction_changelist"),
    ("accounts", "Hisoblar", "fa-wallet", "admin:finance_moneyaccount_changelist"),
    ("pnl", "Foyda va zarar", "fa-scale-balanced", "admin:nz_finance_pnl"),
    ("cashflow", "Pul oqimi", "fa-water", "admin:nz_finance_cashflow"),
    ("budget", "Budjet", "fa-bullseye", "admin:nz_finance_budget"),
    ("debts", "Qarzlar", "fa-file-invoice-dollar", "admin:nz_finance_debts"),
    ("categories", "Moddalar", "fa-tags", "admin:finance_category_changelist"),
)


def money(v) -> str:
    if v is None:
        return "—"
    v = Decimal(v).quantize(Decimal(1))
    s = f"{abs(v):,.0f}".replace(",", " ")
    return f"−{s}" if v < 0 else s


def tr(text: str) -> str:
    """A dashboard phrase in the staff member's language, for text that never passes through the HTML translator (chart JSON)."""
    from django.utils.translation import get_language

    from apps.platform.infrastructure.admin_i18n import translate_text

    lang = (get_language() or "uz")[:2]
    if lang == "uz" or not text:
        return text
    return translate_text(text, lang) or text


UNITS = {"uz": ("ming", "mln", "mlrd"), "ru": ("тыс", "млн", "млрд"), "en": ("K", "M", "B")}


def chart_units() -> dict:
    from django.utils.translation import get_language

    k, m, b = UNITS.get((get_language() or "uz")[:2], UNITS["uz"])
    return {"k": k, "m": m, "b": b}


def tabs(active: str) -> list[dict]:
    return [{"key": k, "label": label, "icon": icon, "url": reverse(name), "on": k == active} for k, label, icon, name in TABS]


def _check(request, perm: str = "finance.view_transaction"):
    if not request.user.is_active or not request.user.is_staff or not request.user.has_perm(perm):
        raise PermissionDenied


def _ctx(request, active: str, title: str, **extra) -> dict:
    return {**admin.site.each_context(request), "title": title, "nz_tabs": tabs(active), "nz_active": active,
            "can_add": request.user.has_perm("finance.add_transaction"), **extra}


def _months_param(request, default: int = 6) -> tuple[int, list[date]]:
    try:
        n = int(request.GET.get("months") or default)
    except ValueError:
        n = default
    n = n if n in (3, 6, 12) else default
    return n, pnl.months_back(timezone.localdate(), n)


# ---------------------------------------------------------------- overview


def overview_view(request):
    _check(request)
    today = timezone.localdate()
    m0 = today.replace(day=1)
    accounts = list(MoneyAccount.objects.filter(is_active=True).select_related("store"))
    bal = ledger.balances(today, accounts)
    total = sum((b["balance"] for b in bal.values()), ZERO)
    cards = [{"a": a, "balance": money(bal[a.id]["balance"]), "neg": bal[a.id]["balance"] < 0, "in": money(bal[a.id]["in_month"]), "out": money(bal[a.id]["out_month"]),
              "url": reverse("admin:nz_finance_statement", args=[a.id])} for a in accounts]
    six = pnl.months_back(today, 6)
    report = pnl.pnl(six)
    cur = len(six) - 1
    flow = pnl.cashflow(six)
    # money the system took/paid but no account is set up to receive -- shown so balances can be trusted
    first = min((a.opening_date for a in accounts), default=m0)
    _routed, orphans = ledger.route(ledger.auto_flows(max(first, m0), today), MoneyAccount.objects.filter(is_active=True))
    orphan_by_source: dict = {}
    for f in orphans:
        orphan_by_source[f.source] = orphan_by_source.get(f.source, ZERO) + f.amount
    expense_rows = [r for r in report["rows"] if r["kind"] == "line" and r["key"] not in ("pos", "online", "coins", "cogs") and r["values"][cur]]
    structure = sorted(({"label": r["label"], "value": float(-r["values"][cur]), "color": r["color"]} for r in expense_rows if r["values"][cur] < 0), key=lambda x: -x["value"])
    debts = _debt_summary()
    budget = _budget_rows(m0)
    over = [b for b in budget if b["plan"] and b["actual"] > b["plan_raw"]]
    recent = Transaction.objects.select_related("account", "to_account", "category").order_by("-occurred_on", "-created_at")[:8]
    month_in = flow["total_in"][cur]
    month_out = flow["total_out"][cur]
    from apps.finance.infrastructure import insights

    p = insights.pace(today)
    run = insights.runway(total, today)
    day = insights.daily(today)
    couriers = insights.courier_cash()
    negative = [c for c in cards if c["neg"]]
    manual_count = Transaction.objects.filter(voided_at__isnull=True, occurred_on__gte=m0, kind=TxKind.EXPENSE).count()
    advice = insights.advice(p=p, run=run, orphans=list(orphan_by_source), negative=negative, over_budget=over, debts=debts, couriers=couriers,
                             coins=debts["coins_raw"], total_cash=total, manual_count=manual_count, today=today)
    aging = insights.aging(today)
    top = insights.top_expenses(m0, today)
    for t in top:
        t["value_fmt"] = money(t["value"])
    for b in aging["buckets"]:
        b["amount_fmt"] = money(b["amount"])
    share_total = sum((max(bal[a.id]["balance"], ZERO) for a in accounts), ZERO)
    for c in cards:
        raw = bal[c["a"].id]["balance"]
        c["share"] = round(float(raw / share_total * 100)) if share_total and raw > 0 else 0
    context = _ctx(
        request, "overview", "Moliya paneli",
        total=money(total), cards=cards, month_in=money(month_in), month_out=money(month_out), month_net=money(month_in - month_out),
        profit=money(report["net"][cur]), profit_neg=report["net"][cur] < 0, margin=report["margins"][cur], gross_margin=report["gross_margins"][cur],
        revenue=money(report["revenue"][cur]), coverage=report["months"][cur]["coverage"],
        chart={"labels": [m["label"] for m in flow["months"]], "in": [float(v) for v in flow["total_in"]], "out": [float(v) for v in flow["total_out"]],
               "profit": [float(v) for v in report["net"]], "structure": [{**x, "label": tr(x["label"])} for x in structure],
               "t": {"in": tr("Kirim"), "out": tr("Chiqim"), "profit": tr("Sof foyda"), "som": tr("so'm"), **chart_units()}},
        orphans=[{"label": str(SOURCES[s][0]), "amount": money(v)} for s, v in orphan_by_source.items() if v],
        debts=debts, over_budget=over, recent=recent, month_label=pnl.month_label(m0), today=today,
        negative=negative, no_accounts=not accounts,
        add_url=reverse("admin:finance_transaction_add"),
        p=p, pf={"revenue": money(p["cur"]["revenue"]), "net": money(p["cur"]["net"]), "net_neg": p["cur"]["net"] < 0, "in": money(p["cash_in"]), "out": money(p["cash_out"]),
                 "gross": money(p["cur"]["gross"]), "expenses": money(p["cur"]["expenses"]), "f_revenue": money(p["forecast_revenue"]), "f_net": money(p["forecast_net"]),
                 "f_net_neg": p["forecast_net"] < 0, "prev_revenue": money(p["prev"]["revenue"]), "prev_net": money(p["prev"]["net"])},
        run=run, run_fmt={"avg_out": money(run["avg_out"]), "avg_net": money(run["avg_net"]), "neg": run["avg_net"] < 0},
        advice=advice, aging=aging, aging_total=money(aging["total"]), top=top, couriers=[{**c, "cash_fmt": money(c["cash"])} for c in couriers],
        best_day={"day": day["best_day"]["day"], "amount": money(day["best_day"]["amount"])} if day["best_day"] else None,
        daily={"labels": day["labels"], "in": day["in"], "out": day["out"], "net": day["net"], "cum": day["cum_in"], "prev": day["prev_cum_in"],
               "t": {"in": tr("Kirim"), "out": tr("Chiqim"), "net": tr("Yig'ilgan sof pul"), "cum": tr("Bu oy kirim (yig'ma)"), "prev": tr("O'tgan oy kirim (yig'ma)"),
                     "som": tr("so'm"), **chart_units()}},
    )
    return TemplateResponse(request, "admin/finance/overview.html", context)


def report_view(request):
    """Moliya → «To'liq hisobot»: one Excel workbook with every finance sheet."""
    _check(request)
    from apps.finance.infrastructure import finance_excel, insights
    from apps.platform.infrastructure.excel_export import response

    n, _months = _months_param(request, 6)
    today = timezone.localdate()
    m0 = today.replace(day=1)
    accounts = list(MoneyAccount.objects.filter(is_active=True))
    bal = ledger.balances(today, accounts)
    total = sum((b["balance"] for b in bal.values()), ZERO)
    p, run, debts = insights.pace(today), insights.runway(total, today), _debt_summary()
    budget = _budget_rows(m0)
    over = [b for b in budget if b["plan"] and b["actual"] > b["plan_raw"]]
    aging = insights.aging(today)
    advice = insights.advice(p=p, run=run, orphans=[], negative=[{"a": a, "balance": money(bal[a.id]["balance"]), "url": ""} for a in accounts if bal[a.id]["balance"] < 0],
                             over_budget=over, debts=debts, couriers=insights.courier_cash(), coins=debts["coins_raw"], total_cash=total,
                             manual_count=Transaction.objects.filter(voided_at__isnull=True, occurred_on__gte=m0, kind=TxKind.EXPENSE).count(), today=today)

    def d(v):
        return "—" if v is None else f"{v:+.1f}%"

    rows = [
        ("Hisoblardagi jami pul", total, f"{len(accounts)} ta faol hisob"),
        (f"Tushum ({pnl.month_label(m0)}, {today.day}-kungacha)", p["cur"]["revenue"], f"o'tgan oyning shu kunlariga nisbatan {d(p['d_revenue'])}"),
        ("Yalpi foyda", p["cur"]["gross"], f"yalpi marja {p['gross_margin']}%" if p["gross_margin"] is not None else ""),
        ("Operatsion xarajatlar", p["cur"]["expenses"], f"o'tgan oyga nisbatan {d(p['d_expenses'])}"),
        ("Sof foyda", p["cur"]["net"], f"rentabellik {p['margin']}% · o'tgan oyga nisbatan {d(p['d_net'])}" if p["margin"] is not None else ""),
        ("Oy oxiriga prognoz: tushum", p["forecast_revenue"], f"joriy sur'at bilan ({p['day']}/{p['days_in']} kun)"),
        ("Oy oxiriga prognoz: sof foyda", p["forecast_net"], ""),
        ("Bu oy pul kirimi", p["cash_in"], f"o'tgan oyga nisbatan {d(p['d_in'])}"),
        ("Bu oy pul chiqimi", p["cash_out"], f"o'tgan oyga nisbatan {d(p['d_out'])}"),
        ("O'rtacha oylik chiqim (3 oy)", run["avg_out"], ""),
        ("O'rtacha oylik sof pul oqimi (3 oy)", run["avg_net"], f"pul taxminan {run['months']} oyga yetadi" if run.get("months") else ""),
        ("Yetkazib beruvchilarga qarz", debts["payable_raw"], f"muddati o'tgan: {debts['overdue']}"),
        ("Mijozlar coinlari", debts["coins_raw"], "kelajakdagi chegirma majburiyati"),
    ]
    summary = {"period": f"{today:%d.%m.%Y} holatiga · {n} oy", "rows": rows, "advice": advice}
    return response(finance_excel.full_report(n, summary, debts, aging, budget), "moliya-hisoboti")


# ---------------------------------------------------------------- P&L and cash flow


def _fmt_rows(rows):
    for r in rows:
        if "values" in r:
            r["cells"] = [{"v": money(v), "neg": v < 0} for v in r["values"]]
            r["total_fmt"] = money(r["total"])
            r["total_neg"] = r["total"] < 0
    return rows


def pnl_view(request):
    _check(request)
    n, months = _months_param(request)
    report = pnl.pnl(months)
    if request.GET.get("export") == "xlsx":
        from apps.finance.infrastructure import finance_excel
        from apps.platform.infrastructure.excel_export import response

        return response(finance_excel.pnl_book(report), "foyda-va-zarar")
    _fmt_rows(report["rows"])
    rev_total = sum(report["revenue"], ZERO)
    for r in report["rows"]:
        if "values" in r:
            r["share"] = round(float(r["total"] / rev_total * 100), 1) if rev_total else None
    totals = {k: sum(report[k], ZERO) for k in ("revenue", "gross", "net", "opex")}
    cogs_total = next((r["total"] for r in report["rows"] if r["key"] == "cogs"), ZERO)
    other_total = totals["net"] - totals["gross"] - totals["opex"]  # taxes and other income
    lead = max(totals["revenue"], Decimal(1))
    fall = []
    level = ZERO
    for label, value, kind in (("Sof tushum", totals["revenue"], "start"), ("Tovar tannarxi", cogs_total, "step"), ("Operatsion xarajatlar", totals["opex"], "step"),
                               ("Soliq va boshqa", other_total, "step"), ("Sof foyda", totals["net"], "end")):
        if kind == "start":
            lo, hi, level = ZERO, value, value
        elif kind == "step":
            lo, hi = sorted((level, level + value))
            level += value
        else:
            lo, hi = sorted((ZERO, value))
        fall.append({"label": label, "value": money(value), "neg": value < 0, "kind": kind,
                     "left": f"{max(0.0, float(lo / lead * 100)):.2f}", "width": f"{max(0.8, float((hi - lo) / lead * 100)):.2f}"})
    active = [i for i, v in enumerate(report["revenue"]) if v]
    best = max(active, key=lambda i: report["net"][i]) if active else None
    return TemplateResponse(request, "admin/finance/pnl.html", _ctx(
        request, "pnl", "Foyda va zarar", r=report, n=n, fall=fall,
        k={"revenue": money(totals["revenue"]), "gross": money(totals["gross"]), "opex": money(-totals["opex"]), "net": money(totals["net"]), "net_neg": totals["net"] < 0,
           "gross_margin": round(float(totals["gross"] / totals["revenue"] * 100), 1) if totals["revenue"] else None,
           "opex_share": round(float(-totals["opex"] / totals["revenue"] * 100), 1) if totals["revenue"] else None,
           "best": report["months"][best]["label"] if best is not None else "—", "best_net": money(report["net"][best]) if best is not None else "",
           "avg": money(totals["revenue"] / len(active)) if active else "0"},
        total_margin=round(float(sum(report["net"], ZERO) / sum(report["revenue"], ZERO) * 100), 1) if sum(report["revenue"], ZERO) else None,
        chart={"labels": [m["label"] for m in report["months"]], "revenue": [float(v) for v in report["revenue"]], "gross": [float(v) for v in report["gross"]],
               "net": [float(v) for v in report["net"]],
               "t": {"revenue": tr("Sof tushum"), "gross": tr("Yalpi foyda"), "net": tr("Sof foyda"), "som": tr("so'm"), **chart_units()}},
    ))


def cashflow_view(request):
    _check(request)
    n, months = _months_param(request)
    report = pnl.cashflow(months)
    if request.GET.get("export") == "xlsx":
        from apps.finance.infrastructure import finance_excel
        from apps.platform.infrastructure.excel_export import response

        return response(finance_excel.cashflow_book(report), "pul-oqimi")
    chart = {"labels": [m["label"] for m in report["months"]], "in": [float(v) for v in report["total_in"]], "out": [float(v) for v in report["total_out"]],
             "closing": [float(v) for v in report["closing"]],
             "t": {"in": tr("Kirim"), "out": tr("Chiqim"), "closing": tr("Oy oxirida hisoblarda"), "som": tr("so'm"), **chart_units()}}
    active = [i for i in range(len(months)) if report["total_in"][i] or report["total_out"][i]]
    avg_in = sum((report["total_in"][i] for i in active), ZERO) / len(active) if active else ZERO
    avg_out = sum((report["total_out"][i] for i in active), ZERO) / len(active) if active else ZERO
    top_in = report["inflow"][0] if report["inflow"] else None
    top_out = report["outflow"][0] if report["outflow"] else None
    sum_in = sum(report["total_in"], ZERO)
    sum_out = sum(report["total_out"], ZERO)
    for r in report["inflow"]:
        r["share"] = round(float(r["total"] / sum_in * 100), 1) if sum_in else 0
    for r in report["outflow"]:
        r["share"] = round(float(r["total"] / sum_out * 100), 1) if sum_out else 0
    extra = {"chart": chart, "avg_in": money(avg_in), "avg_out": money(avg_out), "avg_net": money(avg_in - avg_out), "avg_neg": avg_in < avg_out,
             "top_in": top_in, "top_out": top_out, "top_in_fmt": money(top_in["total"]) if top_in else "", "top_out_fmt": money(top_out["total"]) if top_out else "",
             "closing_now": money(report["closing"][-1]) if report["closing"] else "0"}
    _fmt_rows(report["inflow"])
    _fmt_rows(report["outflow"])
    for key in ("total_in", "total_out", "net", "closing"):
        report[f"{key}_fmt"] = [{"v": money(v), "neg": v < 0} for v in report[key]]
    report["sum_in"], report["sum_out"] = money(sum(report["total_in"], ZERO)), money(sum(report["total_out"], ZERO))
    report["sum_net"] = money(sum(report["net"], ZERO))
    return TemplateResponse(request, "admin/finance/cashflow.html", _ctx(request, "cashflow", "Pul oqimi", r=report, n=n, **extra))


# ---------------------------------------------------------------- budget


def _budget_rows(month: date) -> list[dict]:
    end = min(pnl.next_month(month) - timedelta(days=1), timezone.localdate())
    actual = ledger.manual_totals(month, end) if month <= timezone.localdate() else {}
    plans = {b.category_id: b.amount for b in BudgetLine.objects.filter(month=month)}
    # the average of the 3 months before -- a sensible plan when none is set
    m3 = pnl.months_back(month, 4)[0]
    avgs = {cid: v / 3 for (kind, cid), v in ledger.manual_totals(m3, month - timedelta(days=1)).items() if kind == TxKind.EXPENSE}
    out = []
    for c in Category.objects.filter(kind=CategoryKind.EXPENSE, is_active=True).exclude(section=PnlSection.CAPITAL):
        a = actual.get((TxKind.EXPENSE, c.id), ZERO)
        p = plans.get(c.id)
        pct = int(round(a / p * 100)) if p else None
        today = timezone.localdate()
        days_in = (pnl.next_month(month) - month).days
        if month.year == today.year and month.month == today.month:
            forecast = (a / today.day * days_in).quantize(Decimal(1)) if a else ZERO
        else:
            forecast = a
        avg3 = avgs.get(c.id, ZERO)
        out.append({"c": c, "actual": a, "actual_fmt": money(a), "plan_raw": p, "forecast": forecast, "forecast_fmt": money(forecast) if forecast else "—",
                    "forecast_over": bool(p and forecast > p), "avg3": avg3, "avg3_fmt": money(avg3) if avg3 else "", "plan": f"{p:.0f}" if p is not None else "", "plan_fmt": money(p) if p is not None else "—",
                    "pct": pct, "bar": min(pct or 0, 100), "state": "over" if pct and pct > 100 else "warn" if pct and pct >= 85 else "ok", "left": money(p - a) if p is not None else ""})
    return out


def budget_view(request):
    _check(request)
    today = timezone.localdate()
    try:
        month = date.fromisoformat((request.GET.get("month") or request.POST.get("month") or "") + "-01")
    except ValueError:
        month = today.replace(day=1)
    if request.method == "POST":
        _check(request, "finance.add_budgetline")
        if request.POST.get("copy_prev"):
            prev = pnl.months_back(month, 2)[0]
            n = 0
            for b in BudgetLine.objects.filter(month=prev):
                _o, created = BudgetLine.objects.get_or_create(month=month, category_id=b.category_id, defaults={"amount": b.amount})
                n += created
            messages.success(request, f"O'tgan oydan {n} ta reja ko'chirildi.")
        else:
            saved = 0
            for c in Category.objects.filter(kind=CategoryKind.EXPENSE):
                raw = (request.POST.get(f"plan_{c.id}") or "").replace(" ", "").strip()
                if raw == "":
                    BudgetLine.objects.filter(month=month, category=c).delete()
                    continue
                try:
                    amount = Decimal(raw)
                except InvalidOperation:
                    messages.error(request, f"{c.name}: summa noto'g'ri.")
                    continue
                if amount < 0:
                    messages.error(request, f"{c.name}: summa manfiy bo'lmaydi.")
                    continue
                BudgetLine.objects.update_or_create(month=month, category=c, defaults={"amount": amount})
                saved += 1
            messages.success(request, f"Budjet saqlandi ({saved} ta modda).")
        return HttpResponseRedirect(f"{reverse('admin:nz_finance_budget')}?month={month:%Y-%m}")
    rows = _budget_rows(month)
    if request.GET.get("export") == "xlsx":
        from apps.finance.infrastructure import finance_excel
        from apps.platform.infrastructure.excel_export import response

        return response(finance_excel.budget_book(rows, month), f"budjet-{month:%Y-%m}")
    plan_total = sum((r["plan_raw"] or ZERO for r in rows), ZERO)
    actual_total = sum((r["actual"] for r in rows), ZERO)
    forecast_total = sum((r["forecast"] for r in rows), ZERO)
    states = {"over": 0, "warn": 0, "ok": 0, "none": 0}
    for r in rows:
        states["none" if r["pct"] is None else r["state"]] += 1
    chart_rows = sorted((r for r in rows if r["plan_raw"] or r["actual"]), key=lambda r: -(r["plan_raw"] or r["actual"]))[:10]
    chart = {"labels": [tr(r["c"].name) for r in chart_rows], "plan": [float(r["plan_raw"] or 0) for r in chart_rows], "actual": [float(r["actual"]) for r in chart_rows],
             "t": {"plan": tr("Reja"), "actual": tr("Haqiqiy"), "som": tr("so'm"), **chart_units()}}
    prev, nxt = pnl.months_back(month, 2)[0], pnl.next_month(month)
    return TemplateResponse(request, "admin/finance/budget.html", _ctx(
        request, "budget", "Budjet", rows=rows, month=month, month_label=pnl.month_label(month), prev=prev, next=nxt,
        plan_total=money(plan_total), actual_total=money(actual_total), left_total=money(plan_total - actual_total),
        pct_total=int(round(actual_total / plan_total * 100)) if plan_total else None,
        can_edit=request.user.has_perm("finance.add_budgetline"),
        forecast_total=money(forecast_total), forecast_over=bool(plan_total and forecast_total > plan_total), states=states, chart=chart,
        is_current=month == today.replace(day=1), month_progress=round(today.day * 100 / (pnl.next_month(month) - month).days) if month == today.replace(day=1) else None,
    ))


# ---------------------------------------------------------------- debts


def _debt_summary() -> dict:
    from apps.loyalty.infrastructure.models import Wallet
    from apps.ordering.infrastructure.models import OrderLineItemModel, OrderModel
    from apps.payment.infrastructure.models import PaymentModel
    from apps.stores.infrastructure import supplier_service
    from apps.stores.infrastructure.models import Supplier

    bal = supplier_service.balances()
    names = dict(Supplier.objects.filter(id__in=list(bal)).values_list("id", "name"))
    suppliers = []
    for sid, b in bal.items():
        due = b.purchased - b.paid
        if due > 0 or b.overdue > 0:
            suppliers.append({"id": sid, "name": names.get(sid, "—"), "due": due, "due_fmt": money(due), "overdue": b.overdue, "overdue_fmt": money(b.overdue),
                              "oldest": b.oldest_overdue, "url": reverse("admin:stores_supplier_change", args=[sid])})
    suppliers.sort(key=lambda s: (-s["overdue"], -s["due"]))
    road = list(OrderModel.objects.filter(status="shipped", is_archived=False).values_list("id", flat=True))
    paid = set(PaymentModel.objects.filter(order_id__in=road, status="succeeded").exclude(provider="cash").values_list("order_id", flat=True))
    cod = [o for o in road if o not in paid]
    courier = ZERO
    for l in OrderLineItemModel.objects.filter(order_id__in=cod, status="active").values("unit_price_amount", "quantity", "discount_amount", "tax_amount"):
        courier += l["unit_price_amount"] * l["quantity"] - l["discount_amount"] + l["tax_amount"]
    coins = Wallet.objects.aggregate(s=Sum("balance"))["s"] or 0
    payable = sum((s["due"] for s in suppliers), ZERO)
    overdue = sum((s["overdue"] for s in suppliers), ZERO)
    return {"suppliers": suppliers, "payable": money(payable), "payable_raw": payable, "overdue": money(overdue), "overdue_raw": overdue,
            "courier": money(courier), "courier_raw": courier, "courier_orders": len(cod), "coins": money(coins), "coins_raw": Decimal(coins)}


def debts_view(request):
    _check(request)
    from apps.finance.infrastructure import insights

    d = _debt_summary()
    aging = insights.aging(timezone.localdate())
    if request.GET.get("export") == "xlsx":
        from apps.finance.infrastructure import finance_excel
        from apps.platform.infrastructure.excel_export import response

        return response(finance_excel.debts_book(d, aging), "qarzlar")
    for b in aging["buckets"]:
        b["amount_fmt"] = money(b["amount"])
    for s in aging["suppliers"]:
        s["cells"] = [money(s[k]) if s[k] else "—" for k in ("not_due", "d30", "d60", "d90", "d90p")]
        s["total_fmt"] = money(s["total"])
    couriers = [{**c, "cash_fmt": money(c["cash"])} for c in insights.courier_cash()]
    held = sum((c["cash"] for c in insights.courier_cash()), ZERO) if couriers else ZERO
    return TemplateResponse(request, "admin/finance/debts.html", _ctx(request, "debts", "Qarzlar", d=d, aging=aging, aging_total=money(aging["total"]),
                                                                     couriers=couriers, held=money(held)))


# ---------------------------------------------------------------- account statement


def statement_view(request, pk):
    _check(request)
    account = get_object_or_404(MoneyAccount, pk=pk)
    today = timezone.localdate()
    try:
        start = date.fromisoformat(request.GET.get("from") or "")
    except ValueError:
        start = today.replace(day=1)
    try:
        end = date.fromisoformat(request.GET.get("to") or "")
    except ValueError:
        end = today
    end = min(end, today)
    start = min(start, end)
    st = ledger.statement(account, start, end)
    m0 = today.replace(day=1)
    prev0 = pnl.months_back(m0, 2)[0]
    presets = [("Bu oy", m0, today), ("O'tgan oy", prev0, m0 - timedelta(days=1)), ("30 kun", today - timedelta(days=29), today),
               ("90 kun", today - timedelta(days=89), today), ("Yil boshidan", today.replace(month=1, day=1), today)]
    presets = [{"label": label, "from": a, "to": b, "on": a == start and b == end} for label, a, b in presets]
    # running balance at the end of each day (the rows come newest first)
    by_day: dict = {}
    for r in reversed(st["rows"]):
        by_day[r["day"]] = r["balance"]
    curve_labels, curve, last = [], [], st["opening"]
    d0 = st["start"]
    while d0 <= st["end"] and len(curve) < 400:
        last = by_day.get(d0, last)
        curve_labels.append(f"{d0:%d.%m}")
        curve.append(float(last))
        d0 += timedelta(days=1)
    autos = sum(1 for r in st["rows"] if r["auto"])
    if request.GET.get("export") == "xlsx":
        from apps.platform.infrastructure.excel_export import Col, response, workbook

        cols = [Col("Sana", "day", 12), Col("Operatsiya", "title", 34), Col("Tafsilot", "detail", 40), Col("Summa", "amount", 16, money=True), Col("Qoldiq", "balance", 16)]
        rows = [type("R", (), r) for r in reversed(st["rows"])]
        return response(workbook(f"{account.name} — ko'chirma".replace(":", " ")[:31], cols, rows, f"{st['start']:%d.%m.%Y} — {st['end']:%d.%m.%Y}"), "hisob-kochirma")
    for r in st["rows"]:
        r["amount_fmt"], r["balance_fmt"] = money(r["amount"]), money(r["balance"])
    return TemplateResponse(request, "admin/finance/statement.html", _ctx(
        request, "accounts", account.name, a=account, st=st, opening=money(st["opening"]), closing=money(st["closing"]), inn=money(st["in"]), out=money(st["out"]),
        start=start, end=end, presets=presets, autos=autos, manual=len(st["rows"]) - autos,
        curve={"labels": curve_labels, "values": curve, "color": account.color, "t": {"bal": tr("Qoldiq"), "som": tr("so'm"), **chart_units()}},
    ))


# ---------------------------------------------------------------- void an operation


def void_view(request, pk):
    _check(request, "finance.void_transaction")
    tx = get_object_or_404(Transaction, pk=pk)
    back = reverse("admin:finance_transaction_change", args=[tx.pk])
    if request.method != "POST":
        return HttpResponseRedirect(back)
    reason = (request.POST.get("reason") or "").strip()[:255]
    if tx.voided_at:
        messages.info(request, "Operatsiya allaqachon bekor qilingan.")
    elif not reason:
        messages.error(request, "Bekor qilish sababini yozing.")
    else:
        tx.voided_at = timezone.now()
        tx.voided_by = request.user.get_full_name() or request.user.get_username()
        tx.void_reason = reason
        tx.save(update_fields=["voided_at", "voided_by", "void_reason"])
        messages.success(request, f"{tx.number} bekor qilindi — endi hech qayerda hisoblanmaydi.")
    return HttpResponseRedirect(back)


def urls():
    from django.urls import path

    v = admin.site.admin_view
    return [
        path("finance/overview/", v(overview_view), name="nz_finance"),
        path("finance/report/", v(report_view), name="nz_finance_report"),
        path("finance/pnl/", v(pnl_view), name="nz_finance_pnl"),
        path("finance/cashflow/", v(cashflow_view), name="nz_finance_cashflow"),
        path("finance/budget/", v(budget_view), name="nz_finance_budget"),
        path("finance/debts/", v(debts_view), name="nz_finance_debts"),
        path("finance/account/<uuid:pk>/", v(statement_view), name="nz_finance_statement"),
        path("finance/operation/<uuid:pk>/void/", v(void_view), name="nz_finance_void"),
    ]


def install() -> None:
    """Prepends the finance pages to the admin site's URLs (before the `finance/` app index catch-all)."""
    if getattr(admin.site, "_nz_finance_installed", False):
        return
    previous = admin.site.get_urls

    def get_urls():
        return urls() + previous()

    admin.site.get_urls = get_urls
    admin.site._nz_finance_installed = True
