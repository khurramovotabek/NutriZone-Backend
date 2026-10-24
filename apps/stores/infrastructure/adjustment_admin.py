"""
Qo'lda +/− jurnali: every stock change people made by hand -- admin edits of a branch's stock, count postings, write-offs,
damaged/expired units and transfer shortages -- with who, where, how many, before -> after and why. Read-only: the rows
are the stock ledger itself, which nobody can edit or delete (model guard + database trigger, migration stores 0020).
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.contrib import admin
from django.db.models import Count, Q, Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.platform.infrastructure import premium_admin as ui
from apps.platform.infrastructure.excel_export import Col, ExcelExportMixin
from apps.platform.infrastructure.premium_admin import PremiumListMixin
from apps.stores.infrastructure import stock_service
from apps.stores.infrastructure.models import MANUAL_MOVEMENT_TYPES, StockAdjustment

TZ = ZoneInfo("Asia/Tashkent")
SOURCE = (
    ("admin", "Admin tuzatishi", Q(reference="ADMIN")),
    ("count", "Inventarizatsiya", Q(reference__startswith="IC-")),
    ("writeoff", "Hisobdan chiqarish", Q(reference__startswith="HC-")),
    ("transfer", "Transfer kamomadi", Q(reference__startswith="TR-")),
)
TYPE_LABEL = {"adjustment": "Tuzatish", "damage": "Shikastlangan", "expired": "Muddati o'tgan", "write_off": "Hisobdan chiqarish"}


def _source_of(m) -> tuple[str, str]:
    for key, label, _q in SOURCE:
        if key == "admin" and m.reference == "ADMIN" or key != "admin" and m.reference.startswith({"count": "IC-", "writeoff": "HC-", "transfer": "TR-"}[key]):
            return key, label
    return "other", "Boshqa"


def _doc_link(m) -> str:
    if m.reference.startswith("TR-") and m.document_id:
        return reverse("admin:stores_stocktransfer_workspace", args=[m.document_id])
    if m.reference.startswith("IC-") and m.document_id:
        return reverse("admin:stores_stockcount_workspace", args=[m.document_id])
    if m.reference.startswith("HC-") and m.document_id:
        return reverse("admin:stores_writeoff_document", args=[m.document_id])
    return ""


@admin.register(StockAdjustment)
class StockAdjustmentAdmin(ExcelExportMixin, PremiumListMixin, admin.ModelAdmin):
    list_display = ("created_at", "store", "product_variant", "quantity", "balance_after", "actor")
    list_filter = ("store", "movement_type", ("created_at", admin.DateFieldListFilter))
    search_fields = ("product_variant__sku", "product_variant__barcode", "product_variant__product__translations__name", "actor", "note", "reference")
    list_select_related = ("store", "product_variant")
    ordering = ("-created_at",)
    list_per_page = 50
    actions = None
    nz_icon, nz_tone, nz_title = "fa-scale-unbalanced", "#be123c", "Qo'lda +/− jurnali"
    nz_subtitle = ("Filiallar qoldig'iga qo'lda qo'shilgan (+) va olib tashlangan (−) har bir mahsulot: kim, qachon, qayerda, nechta va nima uchun. "
                   "Yozuvlarni hech kim o'zgartira yoki o'chira olmaydi.")
    nz_columns = (("Qachon", ""), ("Filial", ""), ("Mahsulot", ""), ("Kim / sabab", ""), ("Oldin → keyin", "r"), ("O'zgarish", "r"))
    nz_grid = "120px minmax(130px,1fr) minmax(240px,2.4fr) minmax(200px,1.8fr) 120px 110px"
    nz_search = "Mahsulot, SKU, xodim yoki sabab…"
    nz_empty = ("Qo'lda o'zgarish yo'q", "Filial qoldig'i qo'lda o'zgartirilganda shu yerda paydo bo'ladi.")
    nz_sorts = (("Yangi", ""), ("Eski", "1"))
    nz_css = ("admin/css/nutrizone-adjustments.css",)
    excel_title = "Qo'lda +/− jurnali"
    excel_columns = [
        Col("Qachon", "created_at", 18), Col("Filial", "store.name", 22), Col("Mahsulot", lambda m: m.nz_name, 40), Col("SKU", "product_variant.sku", 16),
        Col("Turi", lambda m: TYPE_LABEL.get(m.movement_type, m.movement_type), 16), Col("O'zgarish", "quantity", 10, number=True),
        Col("Oldin", lambda m: m.balance_before, 10), Col("Keyin", "balance_after", 10), Col("Kim", "actor", 20), Col("Sabab", "note", 40), Col("Hujjat", "reference", 14),
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request).filter(movement_type__in=MANUAL_MOVEMENT_TYPES)
        src = request.GET.get("src")
        for key, _label, q in SOURCE:
            if src == key:
                qs = qs.filter(q)
        d = request.GET.get("dir")
        if d == "plus":
            qs = qs.filter(quantity__gt=0)
        elif d == "minus":
            qs = qs.filter(quantity__lt=0)
        return qs

    def get_changelist(self, request, **kwargs):
        from django.contrib.admin.views.main import ChangeList

        class _CL(ChangeList):
            def get_filters_params(self, params=None):  # src / dir are applied in get_queryset
                out = super().get_filters_params(params)
                out.pop("src", None)
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
        return request.user.has_perm("stores.view_stockmovement")

    def has_module_permission(self, request):
        return self.has_view_permission(request)

    def nz_href(self, obj):
        return _doc_link(obj) or f"{reverse('admin:nz_wms_stock_product', args=[obj.product_variant_id])}"

    def nz_tabs(self, request):
        base = StockAdjustment.objects.filter(movement_type__in=MANUAL_MOVEMENT_TYPES)
        counts = base.aggregate(**{k: Count("id", filter=q) for k, _l, q in SOURCE}, total=Count("id"))
        return ui.tabs_for(request, "src", [("", "Hammasi", counts["total"])] + [(k, label, counts[k]) for k, label, _q in SOURCE],
                           {"admin": "#be123c", "count": "#0ea5e9", "writeoff": "#f97316", "transfer": "#7c3aed"})

    def nz_stats(self, request):
        today = datetime.combine(timezone.localdate(), time.min, tzinfo=TZ)
        week = today - timedelta(days=6)
        base = StockAdjustment.objects.filter(movement_type__in=MANUAL_MOVEMENT_TYPES)
        agg = base.aggregate(
            plus_t=Sum("quantity", filter=Q(quantity__gt=0, created_at__gte=today)), minus_t=Sum("quantity", filter=Q(quantity__lt=0, created_at__gte=today)),
            minus_w=Sum("quantity", filter=Q(quantity__lt=0, created_at__gte=week)), admin_w=Count("id", filter=Q(reference="ADMIN", created_at__gte=week)),
        )
        q = request.GET.copy()
        q.pop("p", None)

        def url(**kv):
            c = q.copy()
            for k, v in kv.items():
                c[k] = v
            return "?" + c.urlencode()

        return [
            ui.stat_card("Bugun qo'shildi", f"+{agg['plus_t'] or 0} dona", "#16a34a", "fa-circle-plus", href=url(dir="plus")),
            ui.stat_card("Bugun olib tashlandi", f"−{-(agg['minus_t'] or 0)} dona", "#dc2626", "fa-circle-minus", href=url(dir="minus")),
            ui.stat_card("7 kunda olib tashlandi", f"−{-(agg['minus_w'] or 0)} dona", "#be123c", "fa-arrow-trend-down"),
            ui.stat_card("7 kunda admin tuzatishlari", agg["admin_w"] or 0, "#7c3aed", "fa-user-shield", href=url(src="admin")),
        ]

    def nz_hero_actions(self, request):
        return [{"label": "Ombor tarixi", "url": reverse("admin:stores_stockmovement_changelist"), "icon": "fa-clock-rotate-left"},
                {"label": "Excel", "url": self.excel_url(request), "icon": "fa-file-excel"}]

    def nz_prepare(self, request, objs):
        infos = stock_service.variant_infos({m.product_variant_id for m in objs})
        for m in objs:
            m.nz_info = infos.get(m.product_variant_id)
            m.nz_name = m.nz_info.name if m.nz_info else m.product_variant.sku

    def nz_row(self, m):
        info = m.nz_info
        when = timezone.localtime(m.created_at, TZ)
        img = format_html('<img src="{}" alt="" loading="lazy">', info.image_url) if info and info.image_url else mark_safe('<i class="fas fa-box" aria-hidden="true"></i>')
        product = format_html('<span class="nzaj-prod"><span class="nzaj-img">{}</span><span><b>{}</b><small>{}{}</small></span></span>',
                              img, m.nz_name, f"{info.size} · " if info and info.size else "", m.product_variant.sku)
        key, label = _source_of(m)
        reason = m.note.removeprefix("Admin: ") if m.note else ""
        who = format_html('<b>{}</b><small>{}{}</small>', m.actor or "Tizim", label, f" · {reason}" if reason else "")
        sign = "plus" if m.quantity > 0 else "minus"
        delta = format_html('<span class="nzaj-delta is-{}">{}{}</span>', sign, "+" if m.quantity > 0 else "−", abs(m.quantity))
        return [format_html("<b>{}</b><small>{}</small>", when.strftime("%d.%m.%Y"), when.strftime("%H:%M")),
                format_html('<span class="nzaj-store"><i class="fas fa-store" aria-hidden="true"></i> {}</span>', m.store.name), product, who,
                format_html('<span class="nzaj-ba">{} <i class="fas fa-arrow-right" aria-hidden="true"></i> <b>{}</b></span>', m.balance_before, m.balance_after), delta]

    def excel_prepare(self, objs):
        self.nz_prepare(None, objs)
