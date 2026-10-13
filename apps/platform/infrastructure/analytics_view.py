"""
Dashboard → Analitika (/django-admin/analytics/): the executive business view -- revenue, profit, branches, products,
payments, orders, customers, stock and alerts for a chosen period, from business_analytics.build() (the same numbers
NutriZoneAnalyticsBot sends to Telegram). The Telegram panel previews the exact report and shows the bot's schedule.

Company-wide money figures: visible to staff who can see both orders and till sales; "send now" is superuser-only.
"""
from __future__ import annotations

import re

from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

PERIOD_TABS = (("today", "Bugun"), ("yesterday", "Kecha"), ("7d", "7 kun"), ("30d", "30 kun"), ("this_month", "Shu oy"),
               ("week", "O'tgan hafta"), ("month", "O'tgan oy"))
SEND_CHOICES = (("bugun", "Bugungi puls"), ("kecha", "Kechagi hisobot"), ("hafta", "Haftalik"), ("oy", "Oylik"), ("moliya", "Moliya (30 kun)"))
REQUIRED_PERMS = ("ordering.view_ordermodel", "pos.view_salemodel")


def can_view(user) -> bool:
    return user.is_active and user.is_staff and (user.is_superuser or user.has_perms(REQUIRED_PERMS))


def _telegram_preview(text: str) -> str:
    """Telegram HTML (already escaped by the renderer) → the same markup for the phone preview, newlines kept by CSS."""
    text = re.sub(r"<(?!/?(b|i|code|blockquote)( expandable)?>)", "&lt;", text)
    return text.replace("<blockquote expandable>", '<blockquote class="is-expandable">')


def _bot_panel(r: dict) -> dict:
    from apps.telegram_bot.infrastructure import analytics_bot as bot
    from apps.telegram_bot.infrastructure import analytics_report as rep

    try:
        from django_celery_beat.models import PeriodicTask

        schedules = list(PeriodicTask.objects.filter(task="telegram_bot.analytics_report").select_related("crontab").order_by("name"))
    except Exception:  # noqa: BLE001
        schedules = []
    layout = None if r["period"].key in ("today", "yesterday", "week", "month") else "full"
    return {
        "username": bot.username(), "live": bot.is_live(), "configured": bot.is_configured(), "recipients": len(bot.recipients()),
        "schedules": [{"name": s.name.split(": ", 1)[-1], "enabled": s.enabled, "last_run": s.last_run_at, "count": s.total_run_count} for s in schedules],
        "preview": [_telegram_preview(m) for m in rep.render(r, layout=layout, on_demand=True)],
    }


def _store_choice(request):
    """(selling branches, the picked one or None) from ?store=<uuid>."""
    import uuid as _uuid

    from apps.stores.infrastructure.models import Store

    stores = list(Store.objects.filter(kind="store").exclude(status="inactive").order_by("name"))
    try:
        wanted = _uuid.UUID(request.GET.get("store", ""))
    except ValueError:
        return stores, None
    return stores, next((st for st in stores if st.id == wanted), None)


def _heat_rows(r: dict) -> list[dict]:
    """Weekday × hour cells with a 0..1 intensity, only for the hours anything ever sells (06–23 by default)."""
    h = r.get("heatmap")
    if not h or not h["peak"]:
        return []
    hours = [x for x in range(24) if any(h["count"][d][x] for d in range(7))]
    lo, hi = (min(hours), max(hours)) if hours else (8, 22)
    lo, hi = min(lo, 8), max(hi, 21)
    peak = h["max"] or 1
    return [{"day": day, "cells": [{"hour": x, "count": h["count"][d][x], "revenue": h["revenue"][d][x], "a": round(h["revenue"][d][x] / peak, 2)}
                                   for x in range(lo, hi + 1)]} for d, day in enumerate(h["days"])]


MIX_COLORS = ("#4f46e5", "#06b6d4", "#22c55e", "#f59e0b", "#ec4899", "#8b5cf6", "#94a3b8")


def _mix_blocks(r: dict) -> list[dict]:
    mix = r.get("mix") or {}

    def paint(rows):
        return [{**x, "color": MIX_COLORS[i % len(MIX_COLORS)]} for i, x in enumerate(rows)]

    return [{"title": "Kategoriyalar ulushi", "icon": "fa-layer-group", "rows": paint(mix.get("categories", []))},
            {"title": "Brendlar ulushi", "icon": "fa-copyright", "rows": paint(mix.get("brands", []))}]


def _chart_data(r: dict) -> dict:
    series = r.get("series") or {"labels": [], "pos": [], "online": [], "previous": [], "hourly": False}
    stores = [{"name": s["name"], "color": s["color"], "revenue": float(s["revenue"])} for s in (r.get("stores") or []) if s["revenue"] > 0]
    pays = [{"label": p["label"], "amount": float(p["amount"]), "code": p["code"]} for p in ((r.get("finance") or {}).get("payments") or {}).get("rows", [])]
    return {"series": series, "stores": stores, "payments": pays}


@staff_member_required
def analytics_view(request):
    from apps.platform.infrastructure import business_analytics as ba

    if not can_view(request.user):
        raise PermissionDenied
    key = request.GET.get("p", "today")
    p = ba.period(key, date_from=request.GET.get("from"), date_to=request.GET.get("to"))
    stores, store = _store_choice(request)
    r = ba.build(p, store_ids=[store.id] if store else None)
    base = reverse("admin:nz_analytics")
    suffix = f"&store={store.id}" if store else ""
    tabs = [{"key": k, "label": label, "url": f"{base}?p={k}{suffix}", "on": p.key == k} for k, label in PERIOD_TABS]
    ctx = {
        **admin.site.each_context(request),
        "title": "Biznes analitikasi",
        "r": r, "p": p, "tabs": tabs, "stores": stores, "store": store,
        "custom_from": p.first_day.isoformat() if p.key == "custom" else "", "custom_to": p.last_day.isoformat() if p.key == "custom" else "",
        "chart_data": _chart_data(r),
        "heat": _heat_rows(r),
        "mix_blocks": _mix_blocks(r),
        "export_url": f"{reverse('admin:nz_analytics_export')}?{request.GET.urlencode()}",
        "bot": _bot_panel(r),
        "send_choices": SEND_CHOICES,
        "can_send": request.user.is_superuser,
        "links": {
            "orders": reverse("admin:ordering_ordermodel_changelist"), "sales": reverse("admin:pos_salemodel_changelist"),
            "stock": reverse("admin:nz_wms_stock"), "expiry": reverse("admin:nz_wms_expiry"), "chat": reverse("admin:nz_chat_admin"),
            "reorder": reverse("admin:stores_reorderrule_changelist"), "wms_reports": reverse("admin:nz_wms_reports"),
        },
    }
    return render(request, "admin/analytics.html", ctx)


@staff_member_required
@require_POST
def analytics_send_view(request):
    from apps.telegram_bot.infrastructure import analytics_bot as bot

    if not request.user.is_superuser:
        raise PermissionDenied
    report = request.POST.get("report", "bugun")
    back = request.POST.get("back") or reverse("admin:nz_analytics")
    if not back.startswith("/django-admin/"):
        back = reverse("admin:nz_analytics")
    if report not in dict(SEND_CHOICES):
        messages.error(request, "Noma'lum hisobot.")
        return redirect(back)
    if not bot.is_configured():
        messages.error(request, "NutriZoneAnalyticsBot sozlanmagan: TELEGRAM_ANALYTICS_BOT_TOKEN va TELEGRAM_ANALYTICS_CHAT_IDS kerak.")
        return redirect(back)
    result = bot.send_now(report)
    if result.get("sent"):
        messages.success(request, f"Hisobot {result['sent']} ta qabul qiluvchiga yuborildi ({result['parts']} ta xabar).")
    if result.get("failed"):
        messages.error(request, f"Yuborilmadi: {', '.join(result['failed'])} — bot bilan /start bosilganini tekshiring.")
    return redirect(back)


@staff_member_required
def analytics_export_view(request):
    """The page's numbers as an Excel workbook (one sheet per section), for the same period."""
    import io

    from django.http import HttpResponse
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    from apps.platform.infrastructure import business_analytics as ba

    if not can_view(request.user):
        raise PermissionDenied
    p = ba.period(request.GET.get("p", "today"), date_from=request.GET.get("from"), date_to=request.GET.get("to"))
    _stores, store = _store_choice(request)
    r = ba.build(p, store_ids=[store.id] if store else None)
    wb = Workbook()
    head_fill, head_font = PatternFill("solid", fgColor="4F46E5"), Font(bold=True, color="FFFFFF")

    def sheet(title: str, header: list, rows: list, first: bool = False):
        ws = wb.active if first else wb.create_sheet()
        ws.title = title[:31]
        ws.append([f"NutriZone · {title}"])
        ws["A1"].font = Font(bold=True, size=14)
        ws.append([f"{p.title} · {p.range_text()}"])
        ws.append([])
        ws.append(header)
        for cell in ws[ws.max_row]:
            cell.fill, cell.font, cell.alignment = head_fill, head_font, Alignment(horizontal="center")
        for row in rows:
            ws.append([float(v) if hasattr(v, "quantize") else v for v in row])
        for i, _ in enumerate(header, 1):
            ws.column_dimensions[chr(64 + i)].width = 34 if i == 1 else 18
        return ws

    ov, fin = r.get("overview") or {}, r.get("finance") or {}
    sheet("Umumiy", ["Ko'rsatkich", "Qiymat"], [
        ("Sof tushum (so'm)", ov.get("revenue")), ("Do'konlar", ov.get("pos_revenue")), ("Onlayn (yetkazilgan)", ov.get("online_revenue")),
        ("Xaridlar", ov.get("purchases")), ("Sotilgan mahsulot (dona)", ov.get("units")), ("O'rtacha chek", ov.get("average")),
        ("Yalpi savdo", fin.get("gross_sales")), ("Chegirmalar", fin.get("discounts")), ("Yetkazish puli", fin.get("delivery")), ("Qaytarishlar", fin.get("refunds")),
        ("Tannarx (COGS)", ov.get("cogs")), ("Yalpi foyda", ov.get("gross_profit")), ("Marja %", ov.get("margin")), ("Tannarx qamrovi %", ov.get("cost_coverage")),
        ("Yo'ldagi onlayn buyurtmalar", ov.get("pipeline_orders")), ("Yo'ldagi summa", ov.get("pipeline_value")),
    ], first=True)
    sheet("Filiallar", ["Filial", "Tushum", "Xaridlar", "Dona", "O'rtacha chek", "Ulush %", "Oldingi davr"],
          [(s["name"], s["revenue"], s["purchases"], s["units"], s["average"], s["share"], s["prev_revenue"]) for s in r.get("stores") or []])
    sheet("Mahsulotlar", ["Mahsulot", "Hajm", "Dona", "Tushum"], [(t["name"], t["size"], t["units"], t["revenue"]) for t in (r.get("products") or {}).get("top", [])])
    sheet("To'lovlar", ["Usul", "Summa", "Soni", "Ulush %"], [(x["label"], x["amount"], x["count"], x["share"]) for x in (fin.get("payments") or {}).get("rows", [])])
    sheet("Kassirlar", ["Sotuvchi", "Filial", "Tushum", "Cheklar", "O'rtacha chek", "Dona"], [(x["name"], x["branch"], x["revenue"], x["count"], x["average"], x["units"]) for x in r.get("sellers") or []])
    mix = r.get("mix") or {}
    sheet("Kategoriyalar", ["Kategoriya", "Tushum", "Ulush %"], [(x["name"], x["revenue"], x["share"]) for x in mix.get("categories", [])])
    sheet("Brendlar", ["Brend", "Tushum", "Ulush %"], [(x["name"], x["revenue"], x["share"]) for x in mix.get("brands", [])])
    o = r.get("orders") or {}
    sheet("Buyurtmalar", ["Holat", "Soni"], [(x["label"], x["count"]) for x in o.get("statuses", [])])
    inv = r.get("inventory") or {}
    sheet("Ombor", ["Mahsulot · joy", "Mavjud", "Minimal"], [(i["code"], i["available_quantity"], i["low_stock_at"]) for i in inv.get("low_stock", [])])
    buf = io.BytesIO()
    wb.save(buf)
    response = HttpResponse(buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="nutrizone-analitika-{p.first_day:%Y%m%d}-{p.last_day:%Y%m%d}.xlsx"'
    return response
