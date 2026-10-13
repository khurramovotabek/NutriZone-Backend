"""
Django Admin registration -- engineering/ops debugging tool only, per
Django Implementation Blueprint §13 and MIC §9's Admin Contract.

**`SaleLineItemModel` deliberately has NO top-level `admin.register()`,
only an inline under `SaleAdmin`** -- the owned entity must not become
independently queryable infrastructure.

**A disclosed scope note, matching every prior module's identical
precedent**: no bulk action is registered. No prior module's bulk
action calls a real Application Service here either, since none
exist for POS yet.
"""
from __future__ import annotations

from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib import admin, messages
from django.db.models import Q
from django.contrib.admin.views.main import ChangeList
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from apps.pos.infrastructure import models as orm

_STATUS_LABELS = {"open": _("Ochiq"), "completed": _("Yakunlangan"), "voided": _("Bekor qilingan"), "refunded": _("Qaytarilgan")}
_STATUS_TONES = {"open": "warning", "completed": "success", "voided": "neutral", "refunded": "danger"}

# Status changes offered on the sale's detail page, keyed by its current status:
# a completed sale can be returned (refund + restock), an abandoned open
# one can be cancelled. Every other status is terminal.
_STATUS_ACTIONS = {
    "completed": {"url_name": "admin:pos_salemodel_refund", "label": _("Qaytarish (vozvrat)"), "icon": "fas fa-rotate-left"},
    "open": {"url_name": "admin:pos_salemodel_void", "label": _("Savdoni bekor qilish"), "icon": "fas fa-ban"},
}
# The project stores and renders in UTC (settings.TIME_ZONE); sales history
# shows the stores' own wall-clock time so it matches the printed receipt.
_STORE_TZ = ZoneInfo("Asia/Tashkent")


def _money(amount) -> str:
    return f"{int(round(Decimal(amount or 0))):,}".replace(",", " ") + " " + str(_("so'm"))


def _order_number(sale_id) -> str:
    """The same short code the POS receipt prints ("#A40CE932")."""
    return "#" + str(sale_id)[:8].upper()


def _users_by_id(ids) -> dict:
    from apps.identity.infrastructure.models import User

    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: u for u in User.objects.filter(id__in=ids).only("id", "full_name", "phone_number")}


def _product_names(product_ids) -> dict:
    from apps.products.infrastructure.models import ProductTranslation

    names = {}
    for t in ProductTranslation.objects.filter(product_id__in=set(product_ids)).only("product_id", "locale_code", "name"):
        if t.name and (t.product_id not in names or t.locale_code == "en"):
            names[t.product_id] = t.name
    return names


class SaleStatusFilter(admin.SimpleListFilter):
    title = _("Holat")
    parameter_name = "status"

    def lookups(self, request, model_admin):
        return list(_STATUS_LABELS.items())

    def queryset(self, request, queryset):
        return queryset.filter(status=self.value()) if self.value() else queryset


class BranchFilter(admin.SimpleListFilter):
    """Filial: every partner store that has sales, plus the dashboard's own till."""

    title = _("Filial")
    parameter_name = "branch"

    def lookups(self, request, model_admin):
        from apps.pos.infrastructure import sales_reports as rep

        ids = orm.SaleModel.objects.filter(channel="store").values_list("branch_id", flat=True).distinct()
        names = rep.store_names([str(i) for i in ids])
        return sorted(((k, v) for k, v in names.items()), key=lambda kv: (kv[0] == rep.CENTRAL, str(kv[1])))

    def queryset(self, request, queryset):
        from apps.pos.infrastructure.sales_reports import CENTRAL

        if not self.value():
            return queryset
        if self.value() == CENTRAL:
            return queryset.exclude(channel="store")
        return queryset.filter(channel="store", branch_id=self.value())


class SellerFilter(admin.SimpleListFilter):
    title = _("Sotuvchi")
    parameter_name = "seller"

    def lookups(self, request, model_admin):
        from apps.pos.infrastructure.sales_reports import people_names

        ids = set(orm.SaleModel.objects.exclude(status="open").values_list("cashier_id", flat=True).distinct())
        names = people_names(ids)
        return sorted(((str(i), names.get(i, str(i)[:8])) for i in ids), key=lambda kv: str(kv[1]))

    def queryset(self, request, queryset):
        return queryset.filter(cashier_id=self.value()) if self.value() else queryset


class PaymentMethodFilter(admin.SimpleListFilter):
    title = _("To'lov turi")
    parameter_name = "method"

    def lookups(self, request, model_admin):
        return [("cash", _("Naqd")), ("uzcard", "Uzcard"), ("humo", "Humo"), ("mixed", _("Aralash to'lov")), ("coins", _("Coin ishlatilgan")), ("discount", _("Chegirmali")), ("returned", _("Qaytarilgani bor"))]

    def queryset(self, request, queryset):
        value = self.value()
        if value == "coins":
            return queryset.filter(coins_redeemed__gt=0)
        if value == "discount":
            return queryset.filter(discount_amount__gt=0)
        if value == "returned":
            return queryset.filter(Q(refunded_amount__gt=0) | Q(refunded_coins__gt=0))
        if value == "mixed":
            return queryset.filter(payment_method="mixed")
        if value == "uzcard":
            return queryset.filter(payment_method__in=["uzcard", "card"])
        if value:
            return queryset.filter(Q(payment_method=value) | Q(payments__contains=[{"method": value}]))
        return queryset


class CompletedAtFilter(admin.DateFieldListFilter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title = _("Yakunlangan vaqt")


class SaleChangeList(ChangeList):
    """Resolves the whole page's buyers, sellers, branches and products in a handful of queries (every reference is a cross-app UUID)."""

    def get_results(self, request):
        from apps.pos.infrastructure import sales_reports as rep

        super().get_results(request)
        page = list(self.result_list)
        people = rep.people_names({r.customer_id for r in page} | {r.cashier_id for r in page})
        stores = rep.store_names({str(r.branch_id) for r in page if r.channel == "store"})
        products = rep.product_summary([r.id for r in page])
        customers = _users_by_id(r.customer_id for r in page)
        for r in page:
            r._customer = customers.get(r.customer_id)
            r._seller = people.get(r.cashier_id)
            r._branch = stores.get(str(r.branch_id)) if r.channel == "store" else stores.get(rep.CENTRAL)
            r._products = products.get(r.id, [])


class SaleLineItemInline(admin.TabularInline):
    model = orm.SaleLineItemModel
    extra = 0
    can_delete = False
    fields = ("product_name", "item_quantity", "unit_price", "line_total")
    readonly_fields = fields
    verbose_name = _("Mahsulot")
    verbose_name_plural = _("Mahsulotlar")

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def product_name(self, obj: orm.SaleLineItemModel) -> str:
        cache = getattr(self, "_names", None)
        if cache is None or obj.product_id not in cache:
            siblings = orm.SaleLineItemModel.objects.filter(sale_id=obj.sale_id).values_list("product_id", flat=True)
            self._names = cache = _product_names(siblings)
        return cache.get(obj.product_id) or _("Noma'lum mahsulot")

    product_name.short_description = _("Mahsulot")

    def item_quantity(self, obj: orm.SaleLineItemModel) -> int:
        return obj.quantity

    item_quantity.short_description = _("Soni")

    def unit_price(self, obj: orm.SaleLineItemModel) -> str:
        return _money(obj.unit_price_amount)

    unit_price.short_description = _("Narxi")

    def line_total(self, obj: orm.SaleLineItemModel) -> str:
        return _money(obj.unit_price_amount * obj.quantity)

    line_total.short_description = _("Summa")


_METHOD_LABELS = {"cash": _("Naqd"), "uzcard": "Uzcard", "humo": "Humo", "card": _("Karta"), "click": "Click", "payme": "Payme", "uzum": "Uzum", "coins": "Coins", "mixed": _("Aralash")}
_METHOD_TONES = {"cash": "#059669", "uzcard": "#2563eb", "humo": "#0d9488", "card": "#475569", "coins": "#d4a017"}


def export_rows(queryset):
    """Header + one row per sale, for CSV / Excel export of exactly what the list shows."""
    from apps.pos.infrastructure import sales_reports as rep

    data = rep.rows(queryset)
    people = rep.people_names({r["customer_id"] for r in data} | {r["cashier_id"] for r in data})
    stores = rep.store_names({rep.branch_key(r) for r in data})
    products = rep.product_summary([r["id"] for r in data])
    header = [
        str(_("Chek raqami")), str(_("Holat")), str(_("Filial")), str(_("Sotuvchi")), str(_("Mijoz")), str(_("Sana")),
        str(_("Mahsulotlar")), str(_("Soni")), str(_("Mahsulotlar summasi")), str(_("Chegirma")), str(_("Yetkazib berish")),
        str(_("Coins")), str(_("To'lov turi")), str(_("Naqd")), "Uzcard", "Humo", str(_("Pul bilan to'langan")), str(_("Qaytarilgan")), str(_("Jami (tushum)")),
    ]
    out = [header]
    for r in sorted(data, key=lambda x: x["when"], reverse=True):
        paid = r["paid"]
        out.append([
            r["receipt_number"] or _order_number(r["id"]), str(_STATUS_LABELS.get(r["status"], r["status"])),
            stores.get(rep.branch_key(r), "—"), people.get(r["cashier_id"], "—"), people.get(r["customer_id"], "") if r["customer_id"] else "",
            timezone.localtime(r["when"], _STORE_TZ).strftime("%d.%m.%Y %H:%M") if r["when"] else "",
            "; ".join(f"{n} × {q}" for n, q in products.get(r["id"], [])), r["units"],
            r["gross"], r["discount_amount"], r["delivery_fee_amount"], r["coins_redeemed"],
            " + ".join(str(_METHOD_LABELS.get(m, m)) for m in r["split_sold"]) or "—",
            r["split"].get("cash", 0), r["split"].get("uzcard", 0), r["split"].get("humo", 0), paid, r["returned"], r["revenue"],
        ])
    return out


def export_response(queryset, fmt: str):
    import csv
    import io

    from django.http import HttpResponse

    table = export_rows(queryset)
    stamp = timezone.localtime(timezone.now(), _STORE_TZ).strftime("%Y%m%d-%H%M")
    if fmt == "xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        wb = Workbook()
        ws = wb.active
        ws.title = "Savdolar"
        for row in table:
            ws.append([float(v) if isinstance(v, Decimal) else v for v in row])
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1E3A8A")
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        money_cols = range(9, len(table[0]) + 1)
        for col in money_cols:
            if col in (13,):
                continue
            for cell in ws.iter_cols(min_col=col, max_col=col, min_row=2):
                for c in cell:
                    c.number_format = "#,##0"
        widths = [14, 14, 24, 22, 22, 17, 60, 8, 16, 12, 12, 12, 12, 14, 14, 14, 16, 16]
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        buf = io.BytesIO()
        wb.save(buf)
        response = HttpResponse(buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="savdolar-{stamp}.xlsx"'
        return response
    buf = io.StringIO()
    buf.write("﻿")  # Excel opens UTF-8 CSV correctly only with a BOM
    writer = csv.writer(buf, delimiter=";")
    for row in table:
        writer.writerow([f"{v:.0f}" if isinstance(v, Decimal) else v for v in row])
    response = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="savdolar-{stamp}.csv"'
    return response


@admin.register(orm.SaleModel)
class SaleAdmin(admin.ModelAdmin):
    """
    Sales Management: every POS sale of every branch (partner stores' terminals
    and the dashboard till) -- receipt number, branch, seller, when, what was
    bought and exactly how it was paid (cash / Uzcard / Humo / coins, discount).
    Filters by branch, seller, date, payment method and status; the header shows
    the filtered totals; the list exports to Excel / CSV. Sales are immutable
    records -- the only change offered is the status action (return / cancel).
    """

    list_display = (
        "receipt_col", "status_badge", "branch_col", "seller_col", "sale_date", "products_col",
        "cash_col", "card_col", "coins_col", "discount_col", "total_col",
    )
    list_display_links = ("receipt_col",)
    list_filter = (BranchFilter, SellerFilter, PaymentMethodFilter, SaleStatusFilter, ("completed_at", CompletedAtFilter))
    date_hierarchy = "created_at"
    search_fields = ("id",)
    search_help_text = _("Chek raqami (NZ-000124), mijoz ismi yoki telefon raqami bo'yicha qidiring")
    ordering = ("-created_at",)
    list_per_page = 25
    inlines = [SaleLineItemInline]
    actions = ["export_selected_xlsx", "export_selected_csv"]
    fieldsets = (
        (_("Chek"), {"fields": ("receipt_col", "status_badge", "sale_date", "refund_date", "e_receipt", "refunds_col")}),
        (_("Kim va qayerda"), {"fields": ("branch_col", "seller_col", "customer_name", "customer_phone", "shift_link")}),
        (_("To'lov"), {"fields": ("purchase_total", "discount_col", "coins_col", "delivery_fee", "payment_col", "tender_col", "total_col")}),
    )
    readonly_fields = (
        "receipt_col", "status_badge", "sale_date", "refund_date", "e_receipt", "branch_col", "seller_col", "customer_name", "customer_phone",
        "shift_link", "purchase_total", "discount_col", "coins_col", "delivery_fee", "payment_col", "tender_col", "total_col", "refunds_col",
    )
    change_form_template = "admin/pos/salemodel/change_form.html"
    change_list_template = "admin/pos/salemodel/change_list.html"

    def get_queryset(self, request):
        qs = super().get_queryset(request).prefetch_related("line_items")
        if request.resolver_match and request.resolver_match.url_name == "pos_salemodel_changelist" and not request.GET.get("status"):
            # an empty basket (opened, nothing scanned, then cancelled / still idle) is not a sale -- hidden unless a status is chosen
            from django.db.models import Exists, OuterRef

            has_lines = Exists(orm.SaleLineItemModel.objects.filter(sale=OuterRef("pk")))
            qs = qs.exclude(Q(status__in=["open", "voided"]) & ~has_lines)
        return qs

    def get_changelist(self, request, **kwargs):
        return SaleChangeList

    def get_changelist_instance(self, request):
        """Premium list rows: everything the template shows, resolved for the whole page (SaleChangeList)."""
        from apps.stores.infrastructure.models import Store

        cl = super().get_changelist_instance(request)
        colors = dict(Store.objects.values_list("id", "color"))
        for s in cl.result_list:
            self._ensure(s)
            split = self._split(s)
            total = self._paid(s) + (s.coins_redeemed or 0)
            returned = (s.refunded_amount or 0) + (s.refunded_coins or 0)
            when = timezone.localtime(s.completed_at or s.created_at, _STORE_TZ)
            label = _STATUS_LABELS.get(s.status, s.status)
            tone = {"open": "#f59e0b", "completed": "#10b981", "voided": "#94a3b8", "refunded": "#e11d48"}.get(s.status, "#64748b")
            if s.status == "completed" and returned:
                label, tone = _("Qisman qaytarilgan"), "#f97316"
            s.nz = {
                "number": s.receipt_number or _order_number(s.id), "date": when.strftime("%d.%m.%Y"), "time": when.strftime("%H:%M"),
                "branch": s._branch or "—", "color": colors.get(s.branch_id) or "#64748b", "seller": s._seller or "—",
                "customer": getattr(s, "_customer", None), "products": s._products[:2], "more": max(0, len(s._products) - 2),
                "units": sum(q for _n, q in s._products),
                "pays": [{"label": _METHOD_LABELS.get(m, m), "tone": _METHOD_TONES.get(m, "#475569"), "amount": f"{int(a):,}".replace(",", " ")} for m, a in split.items() if a],
                "coins": f"{int(s.coins_redeemed):,}".replace(",", " ") if s.coins_redeemed else "", "discount": f"{int(s.discount_amount):,}".replace(",", " ") if s.discount_amount else "",
                "total": f"{int(total - (returned if s.status == 'completed' else 0)):,}".replace(",", " "), "returned": f"{int(returned):,}".replace(",", " ") if returned else "",
                "struck": s.status in ("refunded", "voided"), "label": label, "tone": tone,
            }
        return cl

    def changelist_view(self, request, extra_context=None):
        from apps.pos.infrastructure import sales_reports as rep

        response = super().changelist_view(request, extra_context)
        cl = getattr(response, "context_data", {}).get("cl") if hasattr(response, "context_data") else None
        if cl is not None:
            response.context_data["sales_summary"] = rep.summary(rep.rows(cl.queryset))
            params = request.GET.copy()
            response.context_data["export_query"] = params.urlencode()
            # premium toolbar: every list filter as a select, the date filter as quick chips, status as tabs
            selects, dates, tabs = [], [], []
            for spec in cl.filter_specs:
                choices = list(spec.choices(cl))
                if getattr(spec, "parameter_name", None) == "status":
                    tabs = choices
                elif isinstance(spec, CompletedAtFilter):
                    dates = choices
                else:
                    selects.append({"title": spec.title, "choices": choices})
            response.context_data.update({"nz_selects": selects, "nz_dates": dates, "nz_tabs": tabs, "nz_q": request.GET.get("q", "")})
        return response

    # --- export ---------------------------------------------------------

    @admin.action(description=_("Tanlanganlarni Excel'ga eksport qilish"))
    def export_selected_xlsx(self, request, queryset):
        return export_response(queryset, "xlsx")

    @admin.action(description=_("Tanlanganlarni CSV'ga eksport qilish"))
    def export_selected_csv(self, request, queryset):
        return export_response(queryset, "csv")

    def export_view(self, request):
        """Exports the whole filtered list (the filters/search currently applied), not just one page."""
        fmt = "xlsx" if request.GET.get("format") == "xlsx" else "csv"
        request.GET = request.GET.copy()
        request.GET.pop("format", None)
        cl = self.get_changelist_instance(request)
        return export_response(cl.get_queryset(request), fmt)

    def by_store_json(self, request):
        """Dashboard home → "Daily sales by store" chart data (staff only, via admin_view)."""
        from django.http import JsonResponse

        from apps.pos.infrastructure import sales_reports as rep

        if not self.has_view_permission(request):
            raise PermissionDenied
        key, first, last = rep.resolve_range(request.GET.get("range", "7d"), request.GET.get("from"), request.GET.get("to"))
        return JsonResponse({"range": key, **rep.daily_by_store(first, last)})

    def reports_view(self, request):
        from apps.pos.infrastructure.sales_admin_reports import reports_view

        return reports_view(self, request)

    # --- Status changes (refund / void) ---------------------------------

    def get_urls(self):
        custom = [
            path("export/", self.admin_site.admin_view(self.export_view), name="pos_salemodel_export"),
            path("reports/", self.admin_site.admin_view(self.reports_view), name="pos_salemodel_reports"),
            path("by-store.json", self.admin_site.admin_view(self.by_store_json), name="pos_salemodel_by_store"),
            path("<path:object_id>/refund/", self.admin_site.admin_view(self.refund_view), name="pos_salemodel_refund"),
            path("<path:object_id>/void/", self.admin_site.admin_view(self.void_view), name="pos_salemodel_void"),
        ]
        return custom + super().get_urls()

    def change_view(self, request, object_id, form_url="", extra_context=None):
        """The sale as a premium receipt card (lines, payment split, customer, branch / seller / shift, returns, status action)."""
        obj = self.get_object(request, object_id)
        if obj is None or not self.has_view_permission(request, obj):
            raise PermissionDenied
        from apps.pos.infrastructure import receipts

        rc = receipts.receipt(obj, "uz", public=False)
        self._hydrate(obj)
        action = _STATUS_ACTIONS.get(obj.status)
        tone = {"open": "#f59e0b", "completed": "#10b981", "voided": "#94a3b8", "refunded": "#e11d48"}.get(obj.status, "#64748b")
        when = timezone.localtime(obj.completed_at or obj.created_at, _STORE_TZ)
        pays = [{"label": _METHOD_LABELS.get(p["method"], p["method"]), "tone": _METHOD_TONES.get(p["method"], "#475569"), "amount": p["amount"]} for p in rc["payments"]]
        from apps.stores.infrastructure.models import Store

        color = Store.objects.filter(id=obj.branch_id).values_list("color", flat=True).first() or "#64748b"
        return render(request, "admin/pos/salemodel/sale_detail.html", {
            **self.admin_site.each_context(request), "opts": self.model._meta, "title": rc["number"], "s": obj, "rc": rc, "pays": pays,
            "label": _STATUS_LABELS.get(obj.status, obj.status), "tone": tone, "when": when.strftime("%d.%m.%Y %H:%M"), "branch": obj._branch or "—", "color": color,
            "seller": obj._seller or "—", "customer": self._customer(obj), "e_receipt": receipts.public_url(obj.receipt_token) if obj.receipt_token else None,
            "shift": reverse("admin:stores_cashsession_change", args=[obj.cash_session_id]) if getattr(obj, "cash_session_id", None) else None,
            "action": {**action, "url": reverse(action["url_name"], args=[obj.pk])} if action and self._may_change_status(request, obj) else None,
            "refunded_at": timezone.localtime(obj.refunded_at, _STORE_TZ).strftime("%d.%m.%Y %H:%M") if obj.refunded_at else "",
        })

    def _legacy_change_view(self, request, object_id, form_url="", extra_context=None):
        obj = self.get_object(request, object_id)
        action = _STATUS_ACTIONS.get(obj.status) if obj else None
        extra_context = {
            **(extra_context or {}),
            "sale_status_badge": self.status_badge(obj) if obj else "",
            "sale_status_action": {**action, "url": reverse(action["url_name"], args=[obj.pk])} if action and self._may_change_status(request, obj) else None,
        }
        return super().change_view(request, object_id, form_url, extra_context)

    @staticmethod
    def _hydrate(obj):
        from apps.pos.infrastructure import sales_reports as rep

        people = rep.people_names({obj.customer_id, obj.cashier_id})
        obj._seller = people.get(obj.cashier_id)
        obj._branch = rep.store_names([str(obj.branch_id)]).get(str(obj.branch_id)) if obj.channel == "store" else rep.store_names([]).get(rep.CENTRAL)
        obj._products = rep.product_summary([obj.id]).get(obj.id, [])

    def _may_change_status(self, request, obj) -> bool:
        """Returns and cancellations change money and stock: superadmins only."""
        return bool(obj) and request.user.is_superuser and self.has_change_permission(request, obj)

    def refund_view(self, request, object_id):
        return self._status_change_view(
            request, object_id, expected_status="completed",
            title=_("Savdoni qaytarish (vozvrat)"),
            consequences=[
                _("Savdo holati \"Qaytarilgan\" bo'ladi. Bu amalni ortga qaytarib bo'lmaydi."),
                _("Sotilgan mahsulotlar sotilgan joyiga (filial omboriga) qaytariladi."),
                _("Mijozning ishlatgan coinlari qaytariladi, bu savdodan olgan cashback'i bekor qilinadi."),
                _("Mijozga pulini qaytarib berishni unutmang."),
            ],
            confirm_label=_("Ha, qaytarish"),
            perform=self._perform_refund,
            success_message=_("%(order)s savdosi qaytarildi, mahsulotlar omborga qaytarildi."),
        )

    def void_view(self, request, object_id):
        return self._status_change_view(
            request, object_id, expected_status="open",
            title=_("Savdoni bekor qilish"),
            consequences=[_("Yakunlanmagan savdo \"Bekor qilingan\" bo'ladi. Bu amalni ortga qaytarib bo'lmaydi.")],
            confirm_label=_("Ha, bekor qilish"),
            perform=self._perform_void,
            success_message=_("%(order)s savdosi bekor qilindi."),
        )

    def _status_change_view(self, request, object_id, *, expected_status, title, consequences, confirm_label, perform, success_message):
        obj = self.get_object(request, object_id)
        if obj is None:
            return self._get_obj_does_not_exist_redirect(request, self.opts, object_id)
        if not self._may_change_status(request, obj):
            raise PermissionDenied
        change_url = reverse("admin:pos_salemodel_change", args=[obj.pk])
        if obj.status != expected_status:
            messages.error(request, _("Bu amal %(status)s holatidagi savdo uchun mavjud emas.") % {"status": _STATUS_LABELS.get(obj.status, obj.status)})
            return HttpResponseRedirect(change_url)

        if request.method == "POST":
            from common.exceptions import DomainException

            try:
                perform(request, obj)
            except DomainException:
                messages.error(request, _("Holatni o'zgartirib bo'lmadi: savdo boshqa joyda o'zgargan bo'lishi mumkin. Sahifani yangilab, qayta urinib ko'ring."))
                return HttpResponseRedirect(change_url)
            # audit journal (Dashboard → history); a fresh content-type lookup, never a stale cached id
            from django.contrib.contenttypes.models import ContentType

            ContentType.objects.clear_cache()
            self.log_change(request, obj, [{"changed": {"fields": ["status"], "name": str(title)}}])
            messages.success(request, success_message % {"order": obj.receipt_number or _order_number(obj.pk)})
            return HttpResponseRedirect(change_url)

        lines = list(obj.line_items.all())
        names = _product_names(li.product_id for li in lines)
        products_total = self._products_total(obj)
        context = {
            **self.admin_site.each_context(request),
            "opts": self.opts,
            "title": title,
            "sale": obj,
            "order_number": obj.receipt_number or _order_number(obj.pk),
            "customer_name": self.customer_name(obj),
            "customer_phone": self.customer_phone(obj),
            "status_badge": self.status_badge(obj),
            "lines": [{"name": names.get(li.product_id) or _("Noma'lum mahsulot"), "quantity": li.quantity, "total": _money(li.unit_price_amount * li.quantity)} for li in lines],
            "products_total": _money(products_total),
            "delivery_fee": _money(obj.delivery_fee_amount) if obj.delivery_fee_amount else None,
            "grand_total": _money(self._paid(obj) + (obj.coins_redeemed or 0)),
            "consequences": consequences,
            "confirm_label": confirm_label,
            "change_url": change_url,
        }
        return render(request, "admin/pos/salemodel/status_confirm.html", context)

    @staticmethod
    def _actor_id(request):
        from apps.platform.infrastructure.pos_view import _actor_id

        return _actor_id(request)

    def _perform_refund(self, request, obj):
        actor_id = self._actor_id(request)
        if obj.channel == "store":
            # A partner store's sale: back onto that store's shelf, coins/cashback reversed (the store terminal's own refund rules).
            from apps.stores.infrastructure import pos_service
            from apps.stores.infrastructure.models import Store

            store = Store.objects.get(id=obj.branch_id)
            pos_service.refund(store, actor_id, obj.pk, require_session=False)
            return
        from apps.platform.infrastructure.pos_view import restock_inventory_for_refunded_sale
        from apps.pos.infrastructure import composition

        sale = composition.build_refund_sale(actor_id).execute(obj.pk)
        restock_inventory_for_refunded_sale(sale, actor_id)

    def _perform_void(self, request, obj):
        from apps.pos.infrastructure import composition

        composition.build_void_sale(self._actor_id(request)).execute(obj.pk)

    def get_search_results(self, request, queryset, search_term):
        """Receipt number ("NZ-000124" / "124"), order number ("#A40CE932"), buyer name or phone -- the UUIDs never have to be typed."""
        term = search_term.strip()
        if not term:
            return queryset, False
        from django.db.models import Q

        from apps.identity.infrastructure.models import User

        code = term.lstrip("#").lower()
        digits = "".join(ch for ch in term if ch.isdigit())
        user_q = Q(full_name__icontains=term)
        if len(digits) >= 3:
            user_q |= Q(phone_number__icontains=digits)
        customer_ids = list(User.objects.filter(user_q).values_list("id", flat=True)[:500])
        match = Q(customer_id__in=customer_ids) | Q(receipt_number__iexact=term) | Q(receipt_token=term)
        if digits and len(digits) <= 6:
            match |= Q(receipt_number__endswith=digits.zfill(6))
        if code and all(ch in "0123456789abcdef-" for ch in code):
            match |= Q(id__istartswith=code)
        return queryset.filter(match), False

    # --- columns ----------------------------------------------------------

    def _customer(self, obj: orm.SaleModel):
        if not hasattr(obj, "_customer"):
            obj._customer = _users_by_id([obj.customer_id]).get(obj.customer_id)
        return obj._customer

    def _paid(self, obj) -> Decimal:
        return max(Decimal("0"), self._products_total(obj) - (obj.discount_amount or 0) - (obj.coins_redeemed or 0) + (obj.delivery_fee_amount or 0))

    @admin.display(description=_("Chek"), ordering="receipt_number")
    def receipt_col(self, obj: orm.SaleModel) -> str:
        return format_html('<strong class="nz-num">{}</strong>', obj.receipt_number or _order_number(obj.id))

    def _ensure(self, obj):
        if not hasattr(obj, "_branch"):  # the list resolves a whole page at once (SaleChangeList); a detail page resolves its one sale
            self._hydrate(obj)
        return obj

    @admin.display(description=_("Filial"))
    def branch_col(self, obj) -> str:
        return self._ensure(obj)._branch or "—"

    @admin.display(description=_("Sotuvchi"))
    def seller_col(self, obj) -> str:
        return self._ensure(obj)._seller or "—"

    @admin.display(description=_("Mahsulotlar"))
    def products_col(self, obj) -> str:
        items = self._ensure(obj)._products
        if not items:
            return "—"
        head = ", ".join(f"{name} × {qty}" for name, qty in items[:2])
        more = len(items) - 2
        title = "\n".join(f"{name} × {qty}" for name, qty in items)
        return format_html('<span title="{}" style="display:inline-block;max-width:280px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;vertical-align:bottom">{}</span>{}', title, head, format_html(' <span class="nz-badge nz-badge-neutral">+{}</span>', more) if more > 0 else "")

    def _split(self, obj) -> dict:
        from apps.pos.infrastructure.sales_reports import split_of

        if obj.status not in ("completed", "refunded"):
            return {}
        return split_of(obj.payments, obj.payment_method, self._paid(obj))

    @admin.display(description=_("Naqd"))
    def cash_col(self, obj) -> str:
        amount = self._split(obj).get("cash")
        return _money(amount) if amount else "—"

    @admin.display(description="Uzcard / Humo")
    def card_col(self, obj) -> str:
        parts = [(m, a) for m, a in self._split(obj).items() if m in ("uzcard", "humo") and a]
        if not parts:
            return "—"
        return format_html_join(
            mark_safe("<br>"), '{} <small style="color:{};font-weight:700">{}</small>',
            ((_money(a), _METHOD_TONES.get(m, "#475569"), _METHOD_LABELS.get(m)) for m, a in parts),
        )

    @admin.display(description=_("Coins"), ordering="coins_redeemed")
    def coins_col(self, obj) -> str:
        return format_html('<span style="color:#b8860b;font-weight:700">🪙 {}</span>', f"{int(obj.coins_redeemed):,}".replace(",", " ")) if obj.coins_redeemed else "—"

    @admin.display(description=_("Chegirma"), ordering="discount_amount")
    def discount_col(self, obj) -> str:
        if not obj.discount_amount:
            return "—"
        return format_html('<span style="color:#c026d3" title="{}">−{}</span>', obj.discount_reason or "", _money(obj.discount_amount))

    @admin.display(description=_("Jami"))
    def total_col(self, obj) -> str:
        total = self._paid(obj) + (obj.coins_redeemed or 0)
        returned = (obj.refunded_amount or 0) + (obj.refunded_coins or 0)
        style = "text-decoration:line-through;opacity:.6" if obj.status in ("refunded", "voided") else ""
        if returned and obj.status == "completed":
            return format_html('<strong class="nz-num">{}</strong><br><small style="color:#dc2626">−{} {}</small>', _money(total - returned), _money(returned), _("qaytarildi"))
        return format_html('<strong class="nz-num" style="{}">{}</strong>', style, _money(total))

    @admin.display(description=_("To'lov turi"))
    def payment_col(self, obj) -> str:
        parts = self._split(obj)
        if not parts:
            return "—"
        return format_html_join(" ", '<span class="nz-badge" style="background:{}1f;color:{}">{} {}</span>', (
            (_METHOD_TONES.get(m, "#475569"), _METHOD_TONES.get(m, "#475569"), _METHOD_LABELS.get(m, m), _money(a)) for m, a in parts.items()
        ))

    @admin.display(description=_("Qaytarishlar"))
    def refunds_col(self, obj) -> str:
        refunds = list(obj.refunds.all()) if obj.pk else []
        if not refunds:
            return "—"
        return format_html_join(mark_safe("<br>"), "<strong>{}</strong> · {} · {} {} · {}", (
            (r.number, timezone.localtime(r.created_at, _STORE_TZ).strftime("%d.%m.%Y %H:%M"), sum(int(ln.get("quantity", 0)) for ln in r.lines), _("dona"),
             _money(r.value) + (f" ({_('coin')}: {int(r.coins)})" if r.coins else "")) for r in refunds
        ))

    @admin.display(description=_("Qabul qilindi / qaytim"))
    def tender_col(self, obj) -> str:
        if obj.amount_tendered is None:
            return "—"
        return f"{_money(obj.amount_tendered)} / {_money(obj.change_amount or 0)}"

    @admin.display(description=_("Elektron chek"))
    def e_receipt(self, obj) -> str:
        from apps.pos.infrastructure.receipts import public_url

        url = public_url(obj.receipt_token)
        if not url:
            return "—"
        return format_html('<a href="{}" target="_blank" rel="noopener"><i class="fas fa-qrcode"></i> {}</a>', url, url)

    @admin.display(description=_("Kassa smenasi"))
    def shift_link(self, obj) -> str:
        if not obj.cash_session_id:
            return "—"
        url = reverse("admin:stores_cashsession_change", args=[obj.cash_session_id])
        return format_html('<a href="{}">{}</a>', url, _("Smenani ochish"))

    @admin.display(description=_("Mijoz"))
    def customer_name(self, obj: orm.SaleModel) -> str:
        customer = self._customer(obj)
        if customer is None:
            return format_html('<span class="nz-text-muted">{}</span>', _("Noma'lum"))
        return customer.full_name or _("Noma'lum")

    @admin.display(description=_("Telefon raqami"))
    def customer_phone(self, obj: orm.SaleModel) -> str:
        customer = self._customer(obj)
        return customer.phone_number if customer and customer.phone_number else "—"

    def _products_total(self, obj: orm.SaleModel) -> Decimal:
        return sum((li.unit_price_amount * li.quantity for li in obj.line_items.all()), Decimal("0"))

    @admin.display(description=_("Mahsulotlar summasi"))
    def purchase_total(self, obj: orm.SaleModel) -> str:
        return format_html('<strong class="nz-num">{}</strong>', _money(self._products_total(obj)))

    @admin.display(description=_("Yetkazib berish"), ordering="delivery_fee_amount")
    def delivery_fee(self, obj: orm.SaleModel) -> str:
        return _money(obj.delivery_fee_amount) if obj.delivery_fee_amount else "—"

    @admin.display(description=_("Holat"), ordering="status")
    def status_badge(self, obj: orm.SaleModel) -> str:
        if obj.status == "completed" and ((obj.refunded_amount or 0) + (obj.refunded_coins or 0)) > 0:
            return format_html('<span class="nz-badge nz-badge-warning">{}</span>', _("Qisman qaytarilgan"))
        return format_html(
            '<span class="nz-badge nz-badge-{}">{}</span>', _STATUS_TONES.get(obj.status, "neutral"), _STATUS_LABELS.get(obj.status, obj.status),
        )

    @admin.display(description=_("Qaytarilgan sana"))
    def refund_date(self, obj: orm.SaleModel) -> str:
        return timezone.localtime(obj.refunded_at, _STORE_TZ).strftime("%d.%m.%Y %H:%M") if obj.refunded_at else "—"

    @admin.display(description=_("Sana"), ordering="created_at")
    def sale_date(self, obj: orm.SaleModel) -> str:
        moment = obj.completed_at or obj.voided_at or obj.created_at
        return timezone.localtime(moment, _STORE_TZ).strftime("%d.%m.%Y %H:%M") if moment else "—"


# Real, product-required simplification: removed from Dashboard -- read-only, system-internal (event-log) data an admin never creates or edits by hand.
# @admin.register(orm.PosOutboxEvent)
class PosOutboxEventAdmin(admin.ModelAdmin):
    """Read-only -- append-only/Outbox tables are never editable in admin, per MIC §9."""

    list_display = ("event_type", "event_version", "created_at", "published_at", "publish_attempts")
    list_filter = ("event_type",)
    readonly_fields = [f.name for f in orm.PosOutboxEvent._meta.fields]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
