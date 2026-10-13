"""
Premium list pages for the catalog (Mahsulotlar, Variantlar, Brendlar, Kategoriyalar, Ta'mlar): an analytics header
(KPI cards, a top-5 ranking with bars, a CSS donut) above a glass table with human columns (Uzbek labels, pills,
stock health, 30-day sales with trend). Numbers come from `catalog_analytics.snapshot()`.
"""
from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.products.infrastructure import catalog_analytics as ca

STATUS_UZ = {
    "draft": ("Qoralama", "#64748b"), "pending_review": ("Tekshiruvda", "#f59e0b"), "published": ("Sotuvda", "#16a34a"),
    "unpublished": ("Yashirilgan", "#f59e0b"), "archived": ("Arxivda", "#e11d48"), "active": ("Faol", "#16a34a"),
    "inactive": ("Nofaol", "#64748b"), "discontinued": ("To'xtatilgan", "#e11d48"),
}
LOW_STOCK = 10


def pill(label: str, tone: str, icon: str = "") -> str:
    i = f'<i class="fas {icon}"></i> ' if icon else ""
    return format_html('<span class="nzc-pill" style="--t:{}">{}{}</span>', tone, mark_safe(i), label)


def status_pill(status: str) -> str:
    label, tone = STATUS_UZ.get(status, (status, "#64748b"))
    return pill(label, tone)


def active_pill(active: bool) -> str:
    return pill("Faol", "#16a34a") if active else pill("Nofaol", "#64748b")


def stock_cell(on_hand: int | None, reserved: int = 0) -> str:
    if on_hand is None:
        return mark_safe('<span class="nzc-muted">—</span>')
    tone, label = ("#e11d48", "Tugagan") if on_hand <= 0 else ("#f59e0b", "Kam") if on_hand < LOW_STOCK else ("#16a34a", "Yetarli")
    res = format_html('<small>{} band</small>', reserved) if reserved else ""
    return format_html('<div class="nzc-stock" style="--t:{}"><b>{}</b> <span>{}</span>{}</div>', tone, on_hand, label, res)


def sales_cell(n: ca.Numbers | None, share_of=None) -> str:
    if n is None or (not n.units and not n.revenue):
        return mark_safe('<span class="nzc-muted">Savdo yo\'q</span>')
    trend = ""
    if n.change_pct is not None:
        up = n.change_pct >= 0
        trend = format_html(' <em class="nzc-trend {}">{}{}%</em>', "up" if up else "down", "▲ +" if up else "▼ ", n.change_pct)
    bar = ""
    if share_of:
        pct = max(int(n.revenue * 100 / share_of), 2) if share_of else 0
        bar = format_html('<div class="nzc-bar"><span style="width:{}%"></span></div>', pct)
    return format_html('<div class="nzc-sales"><b>{}</b> so\'m{}<small>{} dona sotildi</small>{}</div>', ca.money(n.revenue), trend, n.units, bar)


class CatalogAnalyticsMixin:
    """Adds the analytics header and the catalog stylesheet to a ModelAdmin changelist."""

    change_list_template = "admin/products/analytics_change_list.html"
    analytics_title = ""

    def analytics(self, request, snap: ca.Snapshot) -> dict:  # pragma: no cover - overridden
        return {}

    def changelist_view(self, request, extra_context=None):
        self._snap = ca.snapshot(30)
        try:
            nzc = self.analytics(request, self._snap)
        except Exception:  # noqa: BLE001 - analytics never block the list itself
            nzc = {}
        return super().changelist_view(request, {**(extra_context or {}), "nzc": nzc, "title": self.analytics_title or None})

    @property
    def snap(self) -> ca.Snapshot:
        snap = getattr(self, "_snap", None)
        if snap is None:
            snap = self._snap = ca.snapshot(30)
        return snap


def kpi(label: str, value, icon: str, tone: str, sub: str = "", change: int | None = None) -> dict:
    return {"label": label, "value": value, "icon": icon, "tone": tone, "sub": sub, "change": ca.change_badge(change)}


def titled(title: str):
    """`list_filter = (("brand", titled("Brend")),)` -- Django's own filter for the field, with a human (Uzbek) title."""

    class _Titled(admin.FieldListFilter):
        def __new__(cls, field, request, params, model, model_admin, field_path):
            inst = admin.FieldListFilter.create(field, request, params, model, model_admin, field_path)
            inst.title = title
            return inst

    return _Titled
