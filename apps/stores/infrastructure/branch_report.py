"""
Filial hisoboti -- online orders handled by each branch over a period (Dashboard → Do'konlar → Filial hisoboti).

Per branch: orders handed to it (pickup / delivery), completed / active / cancelled / returned, handed back to the
warehouse, how fast it accepts an order (assignment → its first step, median and the share within 15 minutes), how fast
a pickup is ready (assignment → "ready for pickup"), and the revenue of completed orders.

Sources: OrderModel.fulfilment_store_id / store_assigned_at, the order status history, and StoreOrderLog (the only
record of a hand-back -- the order no longer carries the branch afterwards).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from statistics import median
from zoneinfo import ZoneInfo

from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone

TZ = ZoneInfo("Asia/Tashkent")
ACCEPT_SLA_MIN = 15
ACTIVE = ("pending_payment", "confirmed", "processing", "shipped")
DONE = ("delivered", "completed")


def _minutes(a, b) -> float:
    return max(0.0, (b - a).total_seconds() / 60)


def fmt_minutes(m: float | None) -> str:
    if m is None:
        return "—"
    if m < 1:
        return "< 1 daq"
    if m < 60:
        return f"{round(m)} daq"
    return f"{m / 60:.1f} soat" if m < 60 * 48 else f"{m / 1440:.1f} kun"


def branch_report(days: int = 30, store_id: int | None = None) -> dict:
    """Every branch's row + network totals. With `store_id`, the daily series and the hand-back list are that branch's only."""
    from apps.ordering.infrastructure.models import OrderLineItemModel, OrderModel, OrderReturnModel, OrderStatusHistoryEntryModel
    from apps.stores.infrastructure.models import Store, StoreKind, StoreOrderLog

    now = timezone.now()
    since = now - timedelta(days=days)
    branches = list(Store.objects.filter(kind=StoreKind.STORE).order_by("name"))
    orders = list(OrderModel.objects.filter(fulfilment_store_id__in=[b.id for b in branches], store_assigned_at__gte=since))
    by_store: dict = defaultdict(list)
    for o in orders:
        by_store[o.fulfilment_store_id].append(o)

    history: dict = defaultdict(list)
    for oid, to_status, at in OrderStatusHistoryEntryModel.objects.filter(order__in=orders).order_by("changed_at").values_list("order_id", "to_status", "changed_at"):
        history[oid].append((to_status, at))
    returned_ids = set(OrderReturnModel.objects.filter(order_id__in=[o.id for o in orders]).values_list("order_id", flat=True))
    expr = ExpressionWrapper(F("unit_price_amount") * F("quantity") - F("discount_amount") + F("tax_amount"), output_field=DecimalField(max_digits=16, decimal_places=2))
    totals_by_order = dict(OrderLineItemModel.objects.filter(order__in=[o for o in orders if o.status in DONE], status="active")
                           .values("order_id").annotate(t=Sum(expr)).values_list("order_id", "t"))
    logs = list(StoreOrderLog.objects.filter(created_at__gte=since, store__in=branches))
    assigned_log = defaultdict(int)
    handed_back = defaultdict(list)
    for log in logs:
        if log.event == StoreOrderLog.ASSIGNED:
            assigned_log[log.store_id] += 1
        else:
            handed_back[log.store_id].append(log)

    rows, all_accept, all_ready = [], [], []
    for b in branches:
        mine = by_store.get(b.id, [])
        backs = handed_back.get(b.id, [])
        if not mine and not backs and not assigned_log.get(b.id):
            continue
        accept, ready, per_order = [], [], []
        for o in mine:
            after = [(s, at) for s, at in history.get(o.id, []) if at > o.store_assigned_at]
            took = _minutes(o.store_assigned_at, after[0][1]) if after else None
            if took is not None:
                accept.append(took)
            per_order.append({"number": o.order_number, "method": o.fulfilment_method, "status": o.status, "assigned_at": o.store_assigned_at, "accept_min": took})
            if o.fulfilment_method == "pickup":
                shipped = next((at for s, at in after if s == "shipped"), None)
                if shipped:
                    ready.append(_minutes(o.store_assigned_at, shipped))
        all_accept += accept
        all_ready += ready
        done = [o for o in mine if o.status in DONE]
        handled = max(assigned_log.get(b.id, 0), len(mine) + len(backs))
        revenue = sum((totals_by_order.get(o.id) or Decimal(0) for o in done), Decimal(0))
        rows.append({
            "store": b, "handled": handled, "pickup": sum(1 for o in mine if o.fulfilment_method == "pickup"), "delivery": sum(1 for o in mine if o.fulfilment_method != "pickup"),
            "done": len(done), "active": sum(1 for o in mine if o.status in ACTIVE), "cancelled": sum(1 for o in mine if o.status == "cancelled"),
            "returned": sum(1 for o in mine if o.status == "returned" or o.id in returned_ids), "handed_back": len(backs),
            "handed_back_pct": round(100 * len(backs) / handled) if handled else 0,
            "accept_median": median(accept) if accept else None, "accept_sla": round(100 * sum(1 for m in accept if m <= ACCEPT_SLA_MIN) / len(accept)) if accept else None,
            "ready_median": median(ready) if ready else None, "revenue": revenue,
            "done_pct": round(100 * len(done) / len(mine)) if mine else 0,
            "orders": sorted(per_order, key=lambda x: x["assigned_at"], reverse=True),
        })
    for r in rows:
        r["accept_label"], r["ready_label"] = fmt_minutes(r["accept_median"]), fmt_minutes(r["ready_median"])
        r["revenue_label"] = f"{int(r['revenue']):,}".replace(",", " ")
    rows.sort(key=lambda r: (-r["handled"], r["store"].name))

    # orders handed to branches per day (Tashkent days), for the trend bars
    per_day = defaultdict(int)
    for o in orders:
        if store_id is not None and o.fulfilment_store_id != store_id:
            continue
        per_day[timezone.localtime(o.store_assigned_at, TZ).date()] += 1
    today = timezone.localtime(now, TZ).date()
    span = min(days, 31)
    series = [{"date": today - timedelta(days=i), "n": per_day.get(today - timedelta(days=i), 0)} for i in range(span - 1, -1, -1)]
    peak = max((d["n"] for d in series), default=0) or 1
    for d in series:
        d["pct"] = round(100 * d["n"] / peak)

    handled = sum(r["handled"] for r in rows)
    totals = {
        "handled": handled, "pickup": sum(r["pickup"] for r in rows), "done": sum(r["done"] for r in rows), "active": sum(r["active"] for r in rows),
        "returned": sum(r["returned"] for r in rows), "cancelled": sum(r["cancelled"] for r in rows), "handed_back": sum(r["handed_back"] for r in rows),
        "accept": fmt_minutes(median(all_accept) if all_accept else None),
        "accept_sla": round(100 * sum(1 for m in all_accept if m <= ACCEPT_SLA_MIN) / len(all_accept)) if all_accept else None,
        "ready": fmt_minutes(median(all_ready) if all_ready else None), "revenue": sum((r["revenue"] for r in rows), Decimal(0)),
        "accept_median": median(all_accept) if all_accept else None, "ready_median": median(all_ready) if all_ready else None,
        "done_pct": round(100 * sum(r["done"] for r in rows) / max(1, sum(len(by_store.get(r["store"].id, [])) for r in rows))) if rows else 0,
        "handed_back_pct": round(100 * sum(r["handed_back"] for r in rows) / handled) if handled else 0,
    }
    recent_backs = sorted((l for sid, ls in handed_back.items() if store_id is None or sid == store_id for l in ls), key=lambda l: l.created_at, reverse=True)[:10]
    for log in recent_backs:
        log.when = timezone.localtime(log.created_at, TZ).strftime("%d.%m.%Y %H:%M")  # server time is UTC
    return {"days": days, "since": timezone.localtime(since, TZ).strftime("%d.%m.%Y"), "rows": rows, "totals": totals, "series": series,
            "hand_backs": recent_backs, "sla": ACCEPT_SLA_MIN}


def branch_report_view(request):
    """Dashboard page (staff only -- wrapped with staff_member_required in reports_view)."""
    from django.contrib import admin
    from django.shortcuts import render
    from django.urls import reverse

    days = _days(request)
    report = branch_report(days)
    t = report["totals"]
    som = lambda v: f"{int(v):,}".replace(",", " ")  # noqa: E731
    stats = [
        {"label": "Filiallarga berilgan buyurtma", "value": t["handled"], "tone": "#4f46e5", "icon": "fa-store", "sub": f"{t['pickup']} tasi olib ketish"},
        {"label": "Qabul qilish (median)", "value": t["accept"], "tone": "#0891b2", "icon": "fa-stopwatch", "sub": f"{report['sla']} daq ichida: {t['accept_sla']}%" if t["accept_sla"] is not None else "hali ma'lumot yo'q"},
        {"label": "Yakunlangan", "value": t["done"], "tone": "#16a34a", "icon": "fa-circle-check", "sub": f"{som(t['revenue'])} so'm tushum"},
        {"label": "Qaytarilgan / bekor", "value": t["returned"] + t["cancelled"], "tone": "#dc2626" if t["returned"] + t["cancelled"] else "#64748b", "icon": "fa-rotate-left", "sub": f"qaytarilgan {t['returned']} · bekor {t['cancelled']}"},
        {"label": "Omborga qaytarilgan", "value": t["handed_back"], "tone": "#d97706" if t["handed_back"] else "#64748b", "icon": "fa-warehouse", "sub": "filial ololmagan buyurtmalar"},
    ]
    tabs = [{"label": f"{d} kun", "url": f"?days={d}", "on": d == days} for d in (7, 30, 90)]
    return render(request, "admin/branch_report.html", {**admin.site.each_context(request), "title": "Filial hisoboti", "report": report, "stats": stats, "tabs": tabs,
                                                        "orders_url": reverse("admin:ordering_ordermodel_changelist"), "board_url": reverse("admin:ordering_ordermodel_board"),
                                                        "export_url": reverse("admin:nz_branch_report_xlsx") + f"?days={days}"})


def _days(request) -> int:
    return int(request.GET["days"]) if request.GET.get("days") in ("7", "30", "90") else 30


def branch_report_xlsx(request):
    """The same report as an Excel workbook: Filiallar, Kunlar, Omborga qaytarishlar (streamed, never stored)."""
    import io

    from django.http import HttpResponse
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    days = _days(request)
    report = branch_report(days)
    head_font, head_fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="4F46E5")

    def header(ws, cols):
        ws.append(cols)
        for c in ws[ws.max_row]:
            c.font, c.fill, c.alignment = head_font, head_fill, Alignment(vertical="center", wrap_text=True)
        ws.freeze_panes = ws.cell(row=ws.max_row + 1, column=2)

    def widths(ws, sizes):
        for i, w in enumerate(sizes, 1):
            ws.column_dimensions[get_column_letter(i)].width = w

    def mins(v):
        return round(v, 1) if v is not None else None

    wb = Workbook()
    ws = wb.active
    ws.title = "Filiallar"
    ws.append([f"Filial hisoboti — {report['since']} dan, {days} kun"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([f"Tuzildi: {timezone.localtime(timezone.now(), TZ).strftime('%d.%m.%Y %H:%M')} (Toshkent)"])
    ws.append([])
    header(ws, ["Filial", "Berilgan", "Olib ketish", "Yetkazish", "Qabul qilish, daq (median)", f"{report['sla']} daq ichida, %", "Tayyorlash, daq (median)",
                "Yakunlangan", "Yakunlangan, %", "Faol", "Qaytarilgan", "Bekor", "Omborga qaytargan", "Omborga qaytargan, %", "Tushum, so'm"])
    for r in report["rows"]:
        ws.append([r["store"].name, r["handled"], r["pickup"], r["delivery"], mins(r["accept_median"]), r["accept_sla"], mins(r["ready_median"]),
                   r["done"], r["done_pct"], r["active"], r["returned"], r["cancelled"], r["handed_back"], r["handed_back_pct"], int(r["revenue"])])
        ws.cell(row=ws.max_row, column=15).number_format = "#,##0"
    t = report["totals"]
    ws.append(["Jami", t["handled"], t["pickup"], t["handled"] - t["pickup"], mins(t["accept_median"]), t["accept_sla"], mins(t["ready_median"]),
               t["done"], t["done_pct"], t["active"], t["returned"], t["cancelled"], t["handed_back"], t["handed_back_pct"], int(t["revenue"])])
    for c in ws[ws.max_row]:
        c.font = Font(bold=True)
    ws.cell(row=ws.max_row, column=15).number_format = "#,##0"
    widths(ws, [30, 10, 11, 11, 14, 12, 14, 12, 12, 8, 11, 8, 14, 14, 16])
    ws.row_dimensions[4].height = 32

    ws = wb.create_sheet("Buyurtmalar")
    header(ws, ["Filial", "Buyurtma", "Usul", "Holat", "Biriktirildi", "Qabul qilish, daq"])
    for r in report["rows"]:
        for o in r["orders"]:
            ws.append([r["store"].name, o["number"], "Olib ketish" if o["method"] == "pickup" else "Yetkazish", o["status"],
                       timezone.localtime(o["assigned_at"], TZ).strftime("%d.%m.%Y %H:%M"), mins(o["accept_min"])])
    widths(ws, [30, 18, 13, 16, 18, 16])

    ws = wb.create_sheet("Kunlar")
    header(ws, ["Sana", "Filiallarga berilgan"])
    for d in report["series"]:
        ws.append([d["date"].strftime("%d.%m.%Y"), d["n"]])
    widths(ws, [14, 20])

    ws = wb.create_sheet("Omborga qaytarishlar")
    header(ws, ["Vaqt", "Filial", "Buyurtma", "Sabab", "Kim"])
    from apps.stores.infrastructure.models import StoreOrderLog
    since = timezone.now() - timedelta(days=days)
    for log in StoreOrderLog.objects.filter(event=StoreOrderLog.HANDED_BACK, created_at__gte=since).select_related("store").order_by("-created_at"):
        ws.append([timezone.localtime(log.created_at, TZ).strftime("%d.%m.%Y %H:%M"), log.store.name, log.order_number, log.reason, log.actor])
    widths(ws, [18, 30, 18, 50, 28])

    buf = io.BytesIO()
    wb.save(buf)
    resp = HttpResponse(buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = f'attachment; filename="filial-hisoboti-{days}kun-{timezone.localtime(timezone.now(), TZ):%Y%m%d}.xlsx"'
    return resp


def my_branch_report(store, days: int = 30) -> dict:
    """The owner's view (GET /my-store/report): this branch's numbers next to the network's -- never another branch's row."""
    report = branch_report(days, store_id=store.id)
    row = next((r for r in report["rows"] if r["store"].id == store.id), None)
    keys = ("handled", "pickup", "delivery", "done", "done_pct", "active", "cancelled", "returned", "handed_back", "handed_back_pct", "accept_sla")
    mine = {k: (row[k] if row else (None if k == "accept_sla" else 0)) for k in keys}
    mine.update({"accept_min": row["accept_median"] if row else None, "ready_min": row["ready_median"] if row else None, "revenue": str(row["revenue"] if row else 0)})
    t = report["totals"]
    branches = max(1, len(report["rows"]))
    return {
        "days": days, "since": (timezone.now() - timedelta(days=days)).isoformat(), "sla": report["sla"], "me": mine,
        "network": {"accept_min": t["accept_median"], "accept_sla": t["accept_sla"], "ready_min": t["ready_median"], "done_pct": t["done_pct"],
                    "handed_back_pct": t["handed_back_pct"], "avg_handled": round(t["handled"] / branches, 1), "branches": len(report["rows"])},
        "series": [{"date": d["date"].isoformat(), "n": d["n"]} for d in report["series"]],
        "orders": [{**o, "assigned_at": o["assigned_at"].isoformat()} for o in (row["orders"][:12] if row else [])],
        "hand_backs": [{"number": l.order_number, "reason": l.reason, "actor": l.actor, "at": l.created_at.isoformat()} for l in report["hand_backs"]],
    }
