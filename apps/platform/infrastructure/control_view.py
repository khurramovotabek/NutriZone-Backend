"""
Dashboard → Nazorat markazi (/django-admin/control/): the live control room -- today's money vs yesterday at the same
time, every branch's till right now, and the control centre's findings (control_center.py) with "close" + the rule
thresholds. Same audience as Analitika (orders + till sales view); thresholds are superuser-only.
"""
from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.platform.infrastructure.analytics_view import _store_choice, can_view

STATE_TABS = (("open", "Ochiq"), ("closed", "Yopilgan"), ("all", "Barchasi"))
GROUP_TABS = (("", "Hammasi"), ("risk", "Shubhali operatsiyalar"), ("ops", "Favqulodda holatlar"), ("stock", "Ombor va muddatlar"))
SETTING_FIELDS = (
    ("discount_percent", "Katta chegirma", "%", "int"), ("discount_amount", "yoki chegirma summasi", "so'm", "money"),
    ("quick_refund_minutes", "Tezkor qaytarish", "daqiqa ichida", "int"), ("refunds_per_cashier", "Kassir qaytarishlari", "ta / kun", "int"),
    ("voids_per_cashier", "Bekor qilingan cheklar", "ta / kun", "int"), ("cash_difference", "Kassa farqi", "so'm", "money"),
    ("shift_open_grace_minutes", "Smena ochilmagan", "daqiqa kechikish", "int"), ("shift_max_hours", "Smena ochiq qolgan", "soatdan ko'p", "int"),
    ("payment_errors", "To'lov tizimi xatolari", "ta / 30 daqiqa", "int"),
    ("forecast_days", "Tugash prognozi", "kun ichida", "int"),
)


def _alerts_page(request, store):
    from apps.platform.infrastructure import control_center as cc
    from apps.platform.infrastructure.models import ControlAlert

    state = request.GET.get("state", "open")
    group = request.GET.get("g", "")
    qs = ControlAlert.objects.select_related("store")
    if state == "open":
        qs = qs.filter(resolved_at__isnull=True).order_by("severity", "-happened_at")
    elif state == "closed":
        qs = qs.filter(resolved_at__isnull=False).order_by("-resolved_at")
    if group in cc.GROUPS:
        qs = qs.filter(kind__in=cc.GROUPS[group])
    if store:
        qs = qs.filter(store=store)
    rows = []
    for a in qs[:120]:
        icon, label = cc.KINDS.get(a.kind, ("•", a.kind))
        group_of = next((g for g, kinds in cc.GROUPS.items() if a.kind in kinds), "ops")
        rows.append({"a": a, "icon": icon, "label": label, "group": group_of, "can_transfer": a.kind in ("low_stock", "stock_forecast") and a.store_id and not a.resolved_at})
    return state, group, rows


def _url(request, **changes) -> str:
    q = request.GET.copy()
    for k, v in changes.items():
        if v:
            q[k] = v
        else:
            q.pop(k, None)
    return f"{reverse('admin:nz_control')}?{q.urlencode()}" if q else reverse("admin:nz_control")


@staff_member_required
def control_view(request):
    from apps.platform.infrastructure import control_center as cc

    if not can_view(request.user):
        raise PermissionDenied
    stores, store = _store_choice(request)
    d = cc.live([store.id] if store else None)
    state, group, rows = _alerts_page(request, store)
    cfg = cc.settings_obj()
    ctx = {
        **admin.site.each_context(request),
        "title": "Nazorat markazi",
        "d": d, "ov": d["overview"] or {}, "stores": stores, "store": store, "rows": rows,
        "state_tabs": [{"label": label, "url": _url(request, state=k if k != "open" else ""), "on": state == k} for k, label in STATE_TABS],
        "group_tabs": [{"label": label, "url": _url(request, g=k), "on": group == k} for k, label in GROUP_TABS],
        "state": state, "cfg": cfg, "can_edit": request.user.is_superuser,
        "settings_rows": [{"name": f, "label": label, "unit": unit, "value": int(getattr(cfg, f))} for f, label, unit, _kind in SETTING_FIELDS],
        "can_request": request.user.has_perm("stores.add_stocktransfer"),
        "telegram": _telegram_state(cfg),
        "back": request.get_full_path(),
        "links": {"analytics": reverse("admin:nz_analytics"), "sessions": reverse("admin:stores_cashsession_changelist"),
                  "sales": reverse("admin:pos_salemodel_changelist")},
    }
    from django.utils import timezone

    with timezone.override(cc.TZ):  # the server runs in UTC; every time on this page is Tashkent time
        return render(request, "admin/control.html", ctx)


def _telegram_state(cfg) -> dict:
    from apps.platform.infrastructure import control_center as cc
    from apps.telegram_bot.infrastructure import analytics_bot

    try:
        people = len(cc.audience())
    except Exception:  # noqa: BLE001
        people = 0
    return {"live": analytics_bot.is_live(), "enabled": cfg.telegram_enabled, "username": analytics_bot.username(), "recipients": people}


def _safe_back(request) -> str:
    back = request.POST.get("back") or ""
    return back if back.startswith("/django-admin/control/") else reverse("admin:nz_control")


def _actor(user) -> str:
    return (user.get_full_name() or user.get_username())[:150]


@staff_member_required
@require_POST
def control_resolve_view(request):
    from apps.platform.infrastructure import control_center as cc

    if not can_view(request.user):
        raise PermissionDenied
    note = (request.POST.get("note") or "").strip()
    ids = []
    for raw in request.POST.getlist("alert"):
        try:
            ids.append(uuid.UUID(raw))
        except ValueError:
            continue
    done = sum(cc.resolve(i, _actor(request.user), note) for i in ids)
    if done:
        messages.success(request, f"{done} ta signal yopildi.")
    else:
        messages.info(request, "Signal allaqachon yopilgan.")
    return redirect(_safe_back(request))


@staff_member_required
@require_POST
def control_settings_view(request):
    from apps.platform.infrastructure import control_center as cc

    if not request.user.is_superuser:
        raise PermissionDenied
    cfg = cc.settings_obj()
    errors = []
    for field, label, _unit, kind in SETTING_FIELDS:
        raw = (request.POST.get(field) or "").replace(" ", "").replace(" ", "")
        try:
            value = Decimal(raw) if kind == "money" else int(raw)
        except (ValueError, InvalidOperation):
            errors.append(label)
            continue
        f = cfg._meta.get_field(field)
        try:
            f.run_validators(value)
            if value < 0:
                raise ValueError
        except Exception:  # noqa: BLE001 - django ValidationError or the sign check
            errors.append(label)
            continue
        setattr(cfg, field, value)
    cfg.enabled = request.POST.get("enabled") == "on"
    cfg.telegram_enabled = request.POST.get("telegram_enabled") == "on"
    cfg.stock_alerts = request.POST.get("stock_alerts") == "on"
    if errors:
        messages.error(request, "Noto'g'ri qiymat: " + ", ".join(errors))
        return redirect(_safe_back(request))
    cfg.save()
    messages.success(request, "Nazorat sozlamalari saqlandi. Yangi chegaralar keyingi tekshiruvdan (2 daqiqa ichida) ishlaydi.")
    return redirect(_safe_back(request))


@staff_member_required
@require_POST
def control_transfer_view(request):
    """"📦 Transfer so'rash" on a stock alert: a transfer draft warehouse → branch, then straight to its workspace."""
    from apps.platform.infrastructure import control_center as cc

    if not (can_view(request.user) and request.user.has_perm("stores.add_stocktransfer")):
        raise PermissionDenied
    try:
        alert_id = uuid.UUID(request.POST.get("alert", ""))
    except ValueError:
        return redirect(_safe_back(request))
    res = cc.request_transfer_for_alert(alert_id, _actor(request))
    if not res["ok"]:
        messages.info(request, res["reason"])
        return redirect(_safe_back(request))
    t = res["transfer"]
    messages.success(request, f"{t.number} qoralamasi yaratildi: {res['lines']} mahsulot, {res['units']} dona. Tekshirib, band qiling.")
    return redirect(reverse("admin:stores_stocktransfer_workspace", args=[t.pk]))
