"""Dashboard → Savdolar → Hisobotlar: branch / seller / payment-method / product breakdowns and a day-week-month revenue chart."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.pos.infrastructure import sales_reports as rep

PERIODS = {
    "today": (_("Bugun"), 0),
    "7d": (_("7 kun"), 6),
    "30d": (_("30 kun"), 29),
    "month": (_("Shu oy"), None),
    "90d": (_("90 kun"), 89),
    "year": (_("Shu yil"), None),
}
GRAINS = {"day": _("Kunlik"), "week": _("Haftalik"), "month": _("Oylik")}


def _parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _window(request) -> tuple[str, datetime, datetime]:
    today = timezone.localtime(timezone.now(), rep.TZ).date()
    start_d, end_d = _parse_date(request.GET.get("from")), _parse_date(request.GET.get("to"))
    period = request.GET.get("period") or "30d"
    if start_d and end_d and start_d <= end_d:
        period = "custom"
    elif period == "month":
        start_d, end_d = today.replace(day=1), today
    elif period == "year":
        start_d, end_d = today.replace(month=1, day=1), today
    else:
        period = period if period in PERIODS else "30d"
        start_d, end_d = today - timedelta(days=PERIODS[period][1]), today
    start = datetime.combine(start_d, time.min, tzinfo=rep.TZ)
    end = datetime.combine(end_d + timedelta(days=1), time.min, tzinfo=rep.TZ)
    return period, start, end


def reports_view(model_admin, request):
    period, start, end = _window(request)
    span_days = (end - start).days
    grain = request.GET.get("grain") or ("day" if span_days <= 45 else "week" if span_days <= 200 else "month")
    grain = grain if grain in GRAINS else "day"
    branch = request.GET.get("branch") or ""

    qs = rep.closed_sales().filter(completed_at__gte=start, completed_at__lt=end)
    if branch == rep.CENTRAL:
        qs = qs.exclude(channel="store")
    elif branch:
        qs = qs.filter(channel="store", branch_id=branch)
    rows = rep.rows(qs)

    branches = rep.by_branch(rows)
    top_branch = max((b["revenue"] for b in branches), default=0) or 1
    for b in branches:
        b["share"] = int(b["revenue"] / top_branch * 100)
    sellers = rep.by_seller(rows)
    top_seller = max((s["revenue"] for s in sellers), default=0) or 1
    for s in sellers:
        s["share"] = int(s["revenue"] / top_seller * 100)

    all_branches = rep.store_names({str(i) for i in rep.closed_sales().filter(channel="store").values_list("branch_id", flat=True).distinct()} | {rep.CENTRAL})
    export_params = f"completed_at__gte={start.date().isoformat()}&completed_at__lt={end.date().isoformat()}"
    if branch:
        export_params += f"&branch={branch}"

    context = {
        **model_admin.admin_site.each_context(request),
        "opts": model_admin.opts,
        "title": _("Savdo hisobotlari"),
        "period": period, "periods": [(k, v[0]) for k, v in PERIODS.items()],
        "grain": grain, "grains": list(GRAINS.items()),
        "branch": branch, "all_branches": sorted(all_branches.items(), key=lambda kv: (kv[0] == rep.CENTRAL, kv[1])),
        "start": start.date(), "end": (end - timedelta(days=1)).date(),
        "summary": rep.summary(rows),
        "series": rep.series(rows, grain, start, end - timedelta(seconds=1)),
        "branches": branches, "sellers": sellers[:15],
        "methods": rep.by_method(rows),
        "top_products": rep.top_products(qs, limit=12),
        "method_labels": {"cash": _("Naqd"), "uzcard": "Uzcard", "humo": "Humo", "coins": "Coins", "click": "Click", "payme": "Payme", "uzum": "Uzum"},
        "method_colors": {"cash": "#10b981", "uzcard": "#2563eb", "humo": "#0d9488", "coins": "#d4a017", "click": "#0ea5e9", "payme": "#06b6d4", "uzum": "#8b5cf6"},
        "export_params": export_params,
    }
    return render(request, "admin/pos/salemodel/reports.html", context)
