"""
NutriZone Admin Dashboard Home view (Phase 08.2).

Patches the *existing* `django.contrib.admin.site`'s own `index()`
method to inject real dashboard data -- does not create a second
`AdminSite`, per this phase's own explicit instruction. Django's own
`app_list`/permission-filtered context is computed by the original
`index()` first and passed through unchanged; this only adds
dashboard-specific context on top of it.

Error isolation (per this phase's own requirement): each section is
computed independently and wrapped so one failing query cannot break
the rest of the page -- a failure renders that section's own error
state, never a fake zero or a full 500.
"""
from __future__ import annotations

import logging

from django.contrib import admin
from django.utils import timezone

from apps.platform.infrastructure.dashboard_home import DashboardHomeAggregator, DashboardPeriod

logger = logging.getLogger("nutrizone.app")

import types

_original_index = admin.site.index


def _safe(section_name: str, fn):
    try:
        return {"ok": True, "data": fn()}
    except Exception:
        logger.exception("Dashboard section '%s' failed to load", section_name)
        return {"ok": False, "data": None}


def _nz_dashboard_index(self, request, extra_context=None):
    extra_context = extra_context or {}

    if request.user.is_authenticated and request.user.is_staff:
        from django.utils.translation import gettext as _t

        period = DashboardPeriod.last_n_days(7, _t("Last 7 Days"))
        aggregator = DashboardHomeAggregator(period)

        extra_context["nz_dashboard"] = {
            "period_label": period.label,
            "last_updated": timezone.now(),
            "kpis": _safe("kpis", aggregator.kpis),
            "recent_orders": _safe("recent_orders", aggregator.recent_orders),
            "low_stock_alerts": _safe("low_stock_alerts", aggregator.low_stock_alerts),
        }
        from apps.platform.infrastructure import dashboard_tasks

        extra_context["nz_tasks"] = _safe("tasks", dashboard_tasks.build)
        extra_context["nzsc_labels"] = _store_sales_labels()
        from apps.platform.infrastructure import dashboard_rankings

        try:
            rank_days = int(request.GET.get("rank") or 30)
        except ValueError:
            rank_days = 30
        extra_context["nz_rankings"] = _safe("rankings", lambda: dashboard_rankings.build(rank_days))

    return _original_index(request, extra_context=extra_context)


def install() -> None:
    """Called once from PlatformConfig.ready() -- patches the specific admin.site instance's own bound index method, not the AdminSite class. Idempotent (safe if ready() ever runs twice, e.g. under certain test runners)."""
    admin.site.index = types.MethodType(_nz_dashboard_index, admin.site)


def _store_sales_labels() -> dict:
    """UI strings for the "daily sales by store" chart script (rendered in the admin's current language)."""
    from django.utils.translation import gettext as _t

    return {
        "som": _t("so'm"), "total": _t("Jami"), "sales": _t("ta savdo"), "stores": _t("filial"), "of": _t("dan"),
        "noPrev": _t("Oldingi davrda savdo yo'q"), "prev": _t("oldingi davr"), "active": _t("faol filial"),
        "empty": _t("Bu davrda savdo yo'q"), "error": _t("Ma'lumotni yuklab bo'lmadi. Qayta urinib ko'ring."), "retry": _t("Qayta urinish"),
        "share": _t("ulush"), "noSales": _t("savdo yo'q"), "open": _t("Savdolarni ochish"),
        "months": [_t("yanvar"), _t("fevral"), _t("mart"), _t("aprel"), _t("may"), _t("iyun"), _t("iyul"), _t("avgust"), _t("sentabr"), _t("oktabr"), _t("noyabr"), _t("dekabr")],
    }
