"""
Narx o'zgarishlari: every price a cashier changed in the basket at any till (branch kassas and the online kassa) --
which kassa, which cashier, which product, list price -> sold price, how much was given away and whether the sale
really went through. Read-only: rows are written only by pos_service.set_price.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib import admin
from django.db.models import Count, F, Q, Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.platform.infrastructure import premium_admin as ui
from apps.platform.infrastructure.excel_export import Col, ExcelExportMixin
from apps.platform.infrastructure.premium_admin import PremiumListMixin
from apps.stores.infrastructure import stock_service
from apps.stores.infrastructure.models import PosPriceChange

TZ = ZoneInfo("Asia/Tashkent")
STATUS = {"completed": ("Sotildi", "#16a34a"), "open": ("Savatda", "#0ea5e9"), "voided": ("Bekor qilindi", "#64748b"), "refunded": ("Qaytarildi", "#dc2626")}


def _money(v) -> str:
    return f"{int(round(Decimal(v or 0))):,}".replace(",", " ")


def _sales(objs) -> dict:
    from apps.pos.infrastructure.models import SaleModel

    return {r["id"]: r for r in SaleModel.objects.filter(id__in={o.sale_id for o in objs}).values("id", "status", "receipt_number")}


@admin.register(PosPriceChange)
class PosPriceChangeAdmin(ExcelExportMixin, PremiumListMixin, admin.ModelAdmin):
    list_display = ("created_at", "store", "product_name", "cashier_name", "list_price", "new_price")
    list_filter = ("store", ("created_at", admin.DateFieldListFilter))
    search_fields = ("product_name", "cashier_name", "reason", "store__name")
    list_select_related = ("store",)
    ordering = ("-created_at",)
    list_per_page = 50
    actions = None
    nz_icon, nz_tone, nz_title = "fa-tags", "#d97706", "Narx o'zgarishlari"
    nz_subtitle = ("Kassalarda savatdagi narxi o'zgartirilgan har bir mahsulot: qaysi kassa, qaysi kassir, eski va yangi narx, farq va sotuv holati. "
                   "Yozuvlarni hech kim o'zgartira olmaydi.")
    nz_columns = (("Qachon", ""), ("Kassa", ""), ("Mahsulot", ""), ("Kassir / sabab", ""), ("Eski → yangi narx", "r"), ("Farq", "r"), ("Holat", ""))
    nz_grid = "110px minmax(130px,1fr) minmax(220px,2.2fr) minmax(170px,1.5fr) 190px 120px 120px"
    nz_search = "Mahsulot, kassir, kassa yoki sabab…"
    nz_empty = ("Narx o'zgarishi yo'q", "Kassir savatdagi mahsulot narxini o'zgartirganda shu yerda paydo bo'ladi.")
    nz_sorts = (("Yangi", ""), ("Eski", "1"))
    nz_css = ("admin/css/nutrizone-adjustments.css",)
    excel_title = "Narx o'zgarishlari"
    excel_columns = [
        Col("Qachon", "created_at", 18), Col("Kassa", "store.name", 22), Col("Mahsulot", "product_name", 40), Col("Soni", "quantity", 8, number=True),
        Col("Eski narx", "list_price", 14, number=True), Col("Yangi narx", "new_price", 14, number=True), Col("Farq", lambda o: o.difference, 14, number=True),
        Col("Kassir", "cashier_name", 22), Col("Sabab", "reason", 30), Col("Holat", lambda o: STATUS.get(o.nz_status, ("—",))[0], 14), Col("Chek", lambda o: o.nz_receipt, 14),
    ]

    def get_queryset(self, request):
        from apps.pos.infrastructure.models import SaleModel

        qs = super().get_queryset(request)
        st = request.GET.get("st")
        if st in STATUS:
            qs = qs.filter(sale_id__in=SaleModel.objects.filter(status=st).values("id"))
        if request.GET.get("dir") == "down":
            qs = qs.filter(new_price__lt=F("list_price"))
        elif request.GET.get("dir") == "up":
            qs = qs.filter(new_price__gt=F("list_price"))
        return qs

    def get_changelist(self, request, **kwargs):
        from django.contrib.admin.views.main import ChangeList

        class _CL(ChangeList):
            def get_filters_params(self, params=None):  # st / dir are applied in get_queryset
                out = super().get_filters_params(params)
                out.pop("st", None)
                out.pop("dir", None)
                return out

        return _CL

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm("pos.view_salemodel") or request.user.has_perm("stores.view_pospricechange")

    def has_module_permission(self, request):
        return self.has_view_permission(request)

    def nz_href(self, obj):
        return reverse("admin:pos_salemodel_change", args=[obj.sale_id])

    def nz_tabs(self, request):
        from apps.pos.infrastructure.models import SaleModel

        status_of = dict(SaleModel.objects.filter(id__in=PosPriceChange.objects.values("sale_id")).values_list("id", "status"))
        counts: dict = {}
        for sale_id in PosPriceChange.objects.values_list("sale_id", flat=True):
            key = status_of.get(sale_id, "open")
            counts[key] = counts.get(key, 0) + 1
        options = [("", "Hammasi", sum(counts.values()))] + [(k, label, counts.get(k, 0)) for k, (label, _c) in STATUS.items() if counts.get(k)]
        return ui.tabs_for(request, "st", options, {k: c for k, (_l, c) in STATUS.items()})

    def nz_stats(self, request):
        from apps.pos.infrastructure.models import SaleModel

        today = datetime.combine(timezone.localdate(), time.min, tzinfo=TZ)
        month = today.replace(day=1)
        sold = PosPriceChange.objects.filter(sale_id__in=SaleModel.objects.filter(status="completed").values("id"))
        given = (F("list_price") - F("new_price")) * F("quantity")
        agg = sold.aggregate(
            n_today=Count("id", filter=Q(created_at__gte=today)), d_today=Sum(given, filter=Q(created_at__gte=today, new_price__lt=F("list_price"))),
            d_week=Sum(given, filter=Q(created_at__gte=today - timedelta(days=6), new_price__lt=F("list_price"))),
            d_month=Sum(given, filter=Q(created_at__gte=month, new_price__lt=F("list_price"))),
        )
        return [
            ui.stat_card("Bugun o'zgartirildi", f"{agg['n_today'] or 0} ta", "#d97706", "fa-tags"),
            ui.stat_card("Bugungi chegirma", f"{_money(agg['d_today'])} so'm", "#dc2626", "fa-arrow-trend-down", href="?dir=down"),
            ui.stat_card("7 kunda", f"{_money(agg['d_week'])} so'm", "#be123c", "fa-calendar-week"),
            ui.stat_card("Shu oy", f"{_money(agg['d_month'])} so'm", "#7c3aed", "fa-calendar"),
        ]

    def nz_hero_actions(self, request):
        return [{"label": "Sotuvlar", "url": reverse("admin:pos_salemodel_changelist"), "icon": "fa-receipt"},
                {"label": "Excel", "url": self.excel_url(request), "icon": "fa-file-excel"}]

    def nz_prepare(self, request, objs):
        sales = _sales(objs)
        infos = stock_service.variant_infos({o.product_variant_id for o in objs if o.product_variant_id})
        for o in objs:
            s = sales.get(o.sale_id) or {}
            o.nz_status, o.nz_receipt = s.get("status") or "open", s.get("receipt_number") or ""
            o.nz_info = infos.get(o.product_variant_id) if o.product_variant_id else None

    def nz_row(self, o):
        when = timezone.localtime(o.created_at, TZ)
        info = o.nz_info
        img = format_html('<img src="{}" alt="" loading="lazy">', info.image_url) if info and info.image_url else mark_safe('<i class="fas fa-box" aria-hidden="true"></i>')
        product = format_html('<span class="nzaj-prod"><span class="nzaj-img">{}</span><span><b>{}</b><small>{} dona</small></span></span>', img, o.product_name or "—", o.quantity)
        who = format_html("<b>{}</b><small>{}</small>", o.cashier_name or "—", o.reason or "sabab ko'rsatilmagan")
        prices = format_html('<span class="nzaj-ba"><s>{}</s> <i class="fas fa-arrow-right" aria-hidden="true"></i> <b>{}</b> so\'m</span>', _money(o.list_price), _money(o.new_price))
        diff = o.difference
        delta = format_html('<span class="nzaj-delta is-{}">{}{}</span>', "minus" if diff > 0 else "plus", "−" if diff > 0 else "+", _money(abs(diff)))
        label, color = STATUS.get(o.nz_status, ("—", "#64748b"))
        status = format_html('<b style="color:{}">{}</b><small>{}</small>', color, label, o.nz_receipt)
        return [format_html("<b>{}</b><small>{}</small>", when.strftime("%d.%m.%Y"), when.strftime("%H:%M")),
                format_html('<span class="nzaj-store"><i class="fas fa-cash-register" aria-hidden="true"></i> {}</span>', o.store.name), product, who, prices, delta, status]

    def excel_prepare(self, objs):
        self.nz_prepare(None, objs)
