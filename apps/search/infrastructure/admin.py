"""
Qidiruv tahlili -- what shoppers search the catalog for (SearchTerm), on the shared premium list.

The "Topilmadi" tab is the point of the page: terms people keep searching that currently find nothing are demand
the store doesn't meet yet (a product to stock, or a missing name/synonym). Read-only: rows are written by search.
"""
from __future__ import annotations

from datetime import timedelta
from urllib.parse import quote

from django.contrib import admin
from django.db.models import Count, Q, Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from apps.platform.infrastructure import premium_admin as ui
from apps.platform.infrastructure.premium_admin import PremiumListMixin
from apps.products.infrastructure.catalog_form_ui import storefront_url
from apps.search.infrastructure.models import SearchTerm
from apps.platform.infrastructure.excel_export import Col, ExcelExportMixin

TABS = {"missing": Q(last_results=0), "recent": None}


@admin.register(SearchTerm)
class SearchTermAdmin(ExcelExportMixin, PremiumListMixin, admin.ModelAdmin):
    excel_title = "Qidiruv so'zlari"
    excel_columns = [Col("So'z", "display", 30), Col("Qidirilgan", "searches", 11, number=True), Col("Topilmagan marta", "zero_results", 14, number=True),
                     Col("Oxirgi natija", "last_results", 12), Col("Til", "last_locale", 6), Col("Birinchi", "first_seen", 17), Col("Oxirgi", "last_seen", 17)]

    list_display = ("display", "last_results", "zero_results", "last_seen", "searches")
    search_fields = ("display", "term")
    ordering = ("-searches", "-last_seen")
    list_per_page = 50
    actions = None

    nz_icon, nz_tone, nz_title = "fa-magnifying-glass-chart", "#0891b2", "Qidiruv tahlili"
    nz_subtitle = "Mijozlar katalogdan nimani qidirmoqda. «Topilmadi» — qidirilgan, lekin do'konda yo'q narsalar: yangi mahsulot yoki yetishmayotgan nom/sinonim uchun signal."
    nz_columns = (("So'rov", ""), ("Holat", ""), ("Natijalar", "r"), ("Natijasiz", "r"), ("Oxirgi marta", ""), ("Qidirilgan", "r"))
    nz_grid = "minmax(240px,3fr) 140px 100px 110px 150px 110px"
    nz_search = "So'rov…"
    nz_empty = ("Hali qidiruv yo'q", "Mijozlar katalogda qidirganda bu yerda paydo bo'ladi.")
    nz_sorts = (("Ko'p qidirilgan", ""), ("Yaqinda", "-4"), ("Ko'p natijasiz", "-3"))

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        tab = request.GET.get("nz")
        if tab == "missing":
            qs = qs.filter(last_results=0)
        elif tab == "recent":
            qs = qs.filter(last_seen__gte=timezone.now() - timedelta(days=7))
        return qs

    def get_changelist(self, request, **kwargs):
        from django.contrib.admin.views.main import ChangeList

        class _CL(ChangeList):
            def get_filters_params(self, params=None):  # `nz` is the tab shortcut, applied in get_queryset
                out = super().get_filters_params(params)
                out.pop("nz", None)
                return out

        return _CL

    def nz_href(self, obj):
        return storefront_url(f"/products?q={quote(obj.display)}") or "#"

    def nz_stats(self, request):
        week = timezone.now() - timedelta(days=7)
        agg = SearchTerm.objects.aggregate(total=Sum("searches"), terms=Count("id"), missing=Count("id", filter=Q(last_results=0)),
                                           missing_searches=Sum("searches", filter=Q(last_results=0)), week=Count("id", filter=Q(last_seen__gte=week)))
        base = reverse("admin:search_searchterm_changelist")
        top_missing = SearchTerm.objects.filter(last_results=0).order_by("-searches").first()
        return [ui.stat_card("Qidiruvlar", agg["total"] or 0, "#0891b2", "fa-magnifying-glass", f"{agg['terms']} xil so'rov", href=base),
                ui.stat_card("Topilmadi", agg["missing"], "#e11d48" if agg["missing"] else "#64748b", "fa-circle-question",
                             f"eng ko'p: «{top_missing.display[:24]}»" if top_missing else "hammasi topilyapti", href=f"{base}?nz=missing"),
                ui.stat_card("Yo'qotilgan talab", agg["missing_searches"] or 0, "#f59e0b", "fa-hand-holding-dollar", "marta natijasiz qidirildi", href=f"{base}?nz=missing"),
                ui.stat_card("7 kunda", agg["week"], "#16a34a", "fa-clock-rotate-left", "xil so'rov qidirildi", href=f"{base}?nz=recent")]

    def nz_tabs(self, request):
        week = timezone.now() - timedelta(days=7)
        return ui.tabs_for(request, "nz", [("", "Barchasi", SearchTerm.objects.count()),
                                           ("missing", "Topilmadi", SearchTerm.objects.filter(last_results=0).count()),
                                           ("recent", "7 kun", SearchTerm.objects.filter(last_seen__gte=week).count())],
                           {"missing": "#e11d48", "recent": "#16a34a"})

    def nz_row(self, t):
        found = t.last_results > 0
        share = round(t.zero_results * 100 / t.searches) if t.searches else 0
        return [format_html('<span class="nzi-user"><span class="nzi-av" style="--c:{}"><i class="fas {}" aria-hidden="true"></i></span><span><b>{}</b><small>{}</small></span></span>',
                            "#0891b2" if found else "#e11d48", "fa-magnifying-glass" if found else "fa-circle-question", t.display, t.term),
                ui.chip("Natija bor", "#16a34a", "fa-check") if found else ui.chip("Topilmadi", "#e11d48", "fa-xmark"),
                format_html("<b>{}</b>", t.last_results),
                format_html("{}<small class=\"nzi-muted\"> · {}%</small>", t.zero_results, share) if t.zero_results else ui.muted("0"),
                format_html("<small>{}</small>", ui.ago(t.last_seen)),
                format_html("<b>{}</b>", t.searches)]
