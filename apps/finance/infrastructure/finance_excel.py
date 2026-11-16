"""
Moliya → Excel: one styled workbook builder used by every finance page.

* full_report(months) -- the whole picture in one file: Xulosa (summary + advice), Foyda va zarar (with % of revenue
  and margins), Pul oqimi, Hisoblar, Qarzlar (aging + per supplier), Budjet, Operatsiyalar.
* pnl_book / cashflow_book / budget_book / debts_book -- the same sheets on their own for the page "Excel" buttons.
Numbers stay numbers (formatted "# ##0"), totals are real SUM formulas, header rows frozen, filters on tables.
"""
from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

from django.utils import timezone

ZERO = Decimal(0)
BRAND = "0F766E"
HEAD = "1E293B"


class Book:
    def __init__(self):
        from openpyxl import Workbook

        self.wb = Workbook()
        self._first = True

    def sheet(self, title: str, heading: str, subtitle: str = ""):
        from openpyxl.styles import Font

        if self._first:
            ws = self.wb.active
            ws.title = title[:31]
            self._first = False
        else:
            ws = self.wb.create_sheet(title[:31])
        ws.append([f"NutriZone · {heading}"])
        ws["A1"].font = Font(bold=True, size=14, color=BRAND)
        ws.append([f"{subtitle + ' · ' if subtitle else ''}Yuklangan: {timezone.localtime():%d.%m.%Y %H:%M}"])
        ws["A2"].font = Font(italic=True, size=10, color="64748B")
        ws.append([])
        ws.sheet_view.showGridLines = False
        return ws

    @staticmethod
    def header(ws, cells, widths=None):
        from openpyxl.styles import Alignment, Font, PatternFill

        ws.append(cells)
        r = ws.max_row
        for c in ws[r]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor=HEAD)
            c.alignment = Alignment(vertical="center", horizontal="center" if c.column > 1 else "left", wrap_text=True)
        ws.row_dimensions[r].height = 26
        if widths:
            from openpyxl.utils import get_column_letter

            for i, w in enumerate(widths, 1):
                ws.column_dimensions[get_column_letter(i)].width = w
        return r

    @staticmethod
    def row(ws, cells, style: str = "", pct_cols=(), money_from: int = 2):
        """style: '' | head | sub | total | grand | muted"""
        from openpyxl.styles import Border, Font, PatternFill, Side

        ws.append([float(v) if isinstance(v, Decimal) else v for v in cells])
        r = ws.max_row
        fills = {"head": "F1F5F9", "sub": "F8FAFC", "total": "E6FFFA", "grand": "CCFBF1"}
        for c in ws[r]:
            if c.column >= money_from and isinstance(c.value, int | float):
                c.number_format = "0.0\"%\"" if c.column in pct_cols else "#,##0;[Red]-#,##0"
            if style in fills:
                c.fill = PatternFill("solid", fgColor=fills[style])
            if style in ("head", "sub", "total", "grand"):
                c.font = Font(bold=True, color="0F172A" if style != "head" else "475569")
            if style == "grand":
                c.border = Border(top=Side(style="medium", color=BRAND))
            if style == "muted":
                c.font = Font(italic=True, color="64748B")
        return r

    @staticmethod
    def finish(ws, first_data_row: int | None = None, filter_to: int | None = None):
        from openpyxl.utils import get_column_letter

        if first_data_row:
            ws.freeze_panes = f"B{first_data_row}"
        if filter_to and first_data_row:
            ws.auto_filter.ref = f"A{first_data_row - 1}:{get_column_letter(ws.max_column)}{filter_to}"

    def bytes(self) -> bytes:
        buf = io.BytesIO()
        self.wb.save(buf)
        return buf.getvalue()


def _f(v):
    return float(v) if v is not None else None


# ---------------------------------------------------------------- sheets


def sheet_pnl(book: Book, report: dict):
    labels = [m["label"] for m in report["months"]]
    ws = book.sheet("Foyda va zarar", "Foyda va zarar", f"{labels[0]} — {labels[-1]}")
    rev_total = sum(report["revenue"], ZERO)
    hr = Book.header(ws, ["Modda", *labels, "Jami", "Tushumdan %"], [40] + [15] * len(labels) + [16, 13])
    pct_col = len(labels) + 3
    for r in report["rows"]:
        if r["kind"] == "head":
            Book.row(ws, [r["label"].upper()], "head")
            continue
        share = round(float(r["total"] / rev_total * 100), 1) if rev_total else None
        Book.row(ws, [r["label"], *r["values"], r["total"], share], {"line": "", "sub": "sub", "total": "total", "grand": "grand"}.get(r["kind"], ""), pct_cols=(pct_col,))
    total_margin = round(float(sum(report["net"], ZERO) / rev_total * 100), 1) if rev_total else None
    Book.row(ws, ["Sof rentabellik, %", *report["margins"], total_margin], "muted", pct_cols=tuple(range(2, len(labels) + 3)))
    gm = round(float(sum(report["gross"], ZERO) / rev_total * 100), 1) if rev_total else None
    Book.row(ws, ["Yalpi marja, %", *report["gross_margins"], gm], "muted", pct_cols=tuple(range(2, len(labels) + 3)))
    Book.row(ws, ["Tannarxi ma'lum tushum, %", *[m["coverage"] for m in report["months"]]], "muted", pct_cols=tuple(range(2, len(labels) + 3)))
    Book.finish(ws, hr + 1)


def sheet_cashflow(book: Book, report: dict):
    labels = [m["label"] for m in report["months"]]
    ws = book.sheet("Pul oqimi", "Pul oqimi", f"{labels[0]} — {labels[-1]}")
    hr = Book.header(ws, ["Manba / modda", *labels, "Jami"], [42] + [15] * len(labels) + [16])
    Book.row(ws, ["KIRIM"], "head")
    for r in report["inflow"]:
        Book.row(ws, [r["label"], *r["values"], r["total"]])
    Book.row(ws, ["Jami kirim", *report["total_in"], sum(report["total_in"], ZERO)], "sub")
    Book.row(ws, ["CHIQIM"], "head")
    for r in report["outflow"]:
        Book.row(ws, [r["label"], *r["values"], r["total"]])
    Book.row(ws, ["Jami chiqim", *report["total_out"], sum(report["total_out"], ZERO)], "sub")
    Book.row(ws, ["Sof pul oqimi", *report["net"], sum(report["net"], ZERO)], "grand")
    Book.row(ws, ["Oy oxirida hisoblarda", *report["closing"]], "total")
    Book.finish(ws, hr + 1)


def sheet_accounts(book: Book):
    from apps.finance.infrastructure import ledger
    from apps.finance.infrastructure.models import SOURCES, MoneyAccount

    accounts = list(MoneyAccount.objects.filter(is_active=True).select_related("store"))
    bal = ledger.balances(None, accounts)
    ws = book.sheet("Hisoblar", "Hisoblar", f"Qoldiq {timezone.localdate():%d.%m.%Y}")
    hr = Book.header(ws, ["Hisob", "Turi", "Filial", "Avtomatik manbalar", "Boshlangan", "Boshlang'ich qoldiq", "Bu oy kirim", "Bu oy chiqim", "Qoldiq"],
                     [26, 16, 20, 46, 12, 17, 15, 15, 17])
    for a in accounts:
        b = bal.get(a.id, {})
        Book.row(ws, [a.name, a.get_kind_display(), a.store.name if a.store else "", ", ".join(str(SOURCES[s][0]) for s in (a.sources or []) if s in SOURCES),
                      a.opening_date.strftime("%d.%m.%Y"), a.opening_balance, b.get("in_month", ZERO), b.get("out_month", ZERO), b.get("balance", ZERO)], money_from=6)
    last = ws.max_row
    if accounts:
        ws.append(["JAMI", None, None, None, None] + [f"=SUM({c}{hr + 1}:{c}{last})" for c in "FGHI"])
        from openpyxl.styles import Font

        for c in ws[ws.max_row]:
            c.font = Font(bold=True)
            c.number_format = "#,##0;[Red]-#,##0"
    Book.finish(ws, hr + 1, last)


def sheet_debts(book: Book, debts: dict, aging: dict):
    ws = book.sheet("Qarzlar", "Qarzlar", f"{timezone.localdate():%d.%m.%Y} holatiga")
    hr = Book.header(ws, ["Ko'rsatkich", "Summa"], [44, 18])
    for label, v in (("Yetkazib beruvchilarga qarz", debts["payable_raw"]), ("Shundan muddati o'tgan", debts["overdue_raw"]),
                     ("Kuryerlardagi naqd (yo'ldagi buyurtmalar)", debts.get("courier_raw", ZERO)), ("Mijozlar coinlari (1 coin = 1 so'm)", debts["coins_raw"])):
        Book.row(ws, [label, v])
    ws.append([])
    Book.header(ws, ["Qarz muddati bo'yicha", "Summa", "Hujjatlar", "Ulushi"])
    for b in aging["buckets"]:
        Book.row(ws, [b["label"], b["amount"], b["count"], b["pct"]], pct_cols=(4,))
    ws.append([])
    from openpyxl.utils import get_column_letter

    Book.header(ws, ["Yetkazib beruvchi", "Muddati kelmagan", "1–30 kun", "31–60 kun", "61–90 kun", "90+ kun", "Jami qarz", "Eng uzoq kechikish, kun"])
    for i, w in enumerate([44, 18, 15, 15, 15, 15, 17, 14], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for s in aging["suppliers"]:
        Book.row(ws, [s["name"], s["not_due"], s["d30"], s["d60"], s["d90"], s["d90p"], s["total"], s["late_days"]])
    Book.finish(ws, hr + 1)


def sheet_budget(book: Book, rows: list, month: date):
    from apps.finance.infrastructure import pnl

    ws = book.sheet("Budjet", "Budjet", pnl.month_label(month))
    hr = Book.header(ws, ["Modda", "Hisobotda", "Reja", "Haqiqiy", "Bajarilishi, %", "Qoldi", "Oy oxiriga prognoz"], [32, 22, 15, 15, 14, 15, 18])
    for r in rows:
        Book.row(ws, [r["c"].name, str(r["c"].get_section_display()), r["plan_raw"], r["actual"], r["pct"], (r["plan_raw"] - r["actual"]) if r["plan_raw"] is not None else None,
                      r.get("forecast")], pct_cols=(5,), money_from=3)
    last = ws.max_row
    if rows:
        ws.append(["JAMI", None] + [f"=SUM({c}{hr + 1}:{c}{last})" for c in "CD"] + [None] + [f"=SUM({c}{hr + 1}:{c}{last})" for c in "FG"])
        from openpyxl.styles import Font

        for c in ws[ws.max_row]:
            c.font = Font(bold=True)
            c.number_format = "#,##0;[Red]-#,##0"
    Book.finish(ws, hr + 1, last)


def sheet_operations(book: Book, start: date, end: date):
    from apps.finance.infrastructure.models import Transaction

    ws = book.sheet("Operatsiyalar", "Operatsiyalar", f"{start:%d.%m.%Y} — {end:%d.%m.%Y}")
    hr = Book.header(ws, ["Raqam", "Sana", "Turi", "Hisob", "Qaysi hisobga", "Modda", "Filial", "Kontragent", "Hujjat", "Izoh", "Kirim", "Chiqim", "O'tkazma", "Holat", "Kiritdi"],
                     [12, 11, 11, 20, 20, 22, 18, 22, 12, 30, 14, 14, 14, 12, 16])
    qs = (Transaction.objects.filter(occurred_on__gte=start, occurred_on__lte=end).select_related("account", "to_account", "category", "store")
          .order_by("occurred_on", "number"))
    for t in qs:
        live = not t.voided_at
        Book.row(ws, [t.number, t.occurred_on.strftime("%d.%m.%Y"), t.get_kind_display(), t.account.name, t.to_account.name if t.to_account else "",
                      t.category.name if t.category else "", t.store.name if t.store else "", t.counterparty, t.reference, t.note,
                      t.amount if live and t.kind == "income" else None, t.amount if live and t.kind == "expense" else None,
                      t.amount if live and t.kind == "transfer" else None, "Bekor qilingan" if t.voided_at else "Faol", t.created_by], money_from=11)
    last = ws.max_row
    if last > hr:
        ws.append([None] * 9 + ["JAMI"] + [f"=SUBTOTAL(9,{c}{hr + 1}:{c}{last})" for c in "KLM"])
        from openpyxl.styles import Font

        for c in ws[ws.max_row]:
            c.font = Font(bold=True)
            c.number_format = "#,##0"
    Book.finish(ws, hr + 1, last)


def sheet_summary(book: Book, s: dict):
    ws = book.sheet("Xulosa", "Moliyaviy xulosa", s["period"])
    hr = Book.header(ws, ["Ko'rsatkich", "Qiymat", "Izoh"], [38, 20, 60])
    for label, value, note in s["rows"]:
        Book.row(ws, [label, value, note], pct_cols=())
    if s.get("advice"):
        ws.append([])
        Book.header(ws, ["Tavsiya", "Daraja", ""])
        levels = {"bad": "Muhim", "warn": "Diqqat", "info": "Ma'lumot", "ok": "Yaxshi"}
        for a in s["advice"]:
            Book.row(ws, [a["text"], levels[a["level"]], a.get("link", "")])
        from openpyxl.styles import Alignment

        for row in ws.iter_rows(min_row=hr + len(s["rows"]) + 3):
            row[0].alignment = Alignment(wrap_text=True, vertical="top")
        ws.column_dimensions["A"].width = 90


# ---------------------------------------------------------------- books


def pnl_book(report) -> bytes:
    b = Book()
    sheet_pnl(b, report)
    return b.bytes()


def cashflow_book(report) -> bytes:
    b = Book()
    sheet_cashflow(b, report)
    return b.bytes()


def budget_book(rows, month) -> bytes:
    b = Book()
    sheet_budget(b, rows, month)
    return b.bytes()


def debts_book(debts, aging) -> bytes:
    b = Book()
    sheet_debts(b, debts, aging)
    return b.bytes()


def full_report(n_months: int, summary: dict, debts: dict, aging: dict, budget_rows: list) -> bytes:
    from apps.finance.infrastructure import pnl

    today = timezone.localdate()
    months = pnl.months_back(today, n_months)
    b = Book()
    sheet_summary(b, summary)
    sheet_pnl(b, pnl.pnl(months))
    sheet_cashflow(b, pnl.cashflow(months))
    sheet_accounts(b)
    sheet_debts(b, debts, aging)
    sheet_budget(b, budget_rows, today.replace(day=1))
    sheet_operations(b, months[0], today)
    return b.bytes()

