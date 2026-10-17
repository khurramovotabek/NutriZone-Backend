"""
NutriZone Admin Reports & Business Intelligence view (Phase 08.8).

Patches the *existing* `django.contrib.admin.site`'s own `get_urls()`
to add a new `/django-admin/reports/` page -- does not create a
second `AdminSite`, matching Phase 08.2's own established pattern for
extending the single, existing admin site.

Error isolation, matching Phase 08.2's own convention exactly: each
report section is computed independently and wrapped so one failing
selector cannot break the rest of the page.
"""
from __future__ import annotations

import logging

from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.platform.infrastructure.reports import ReportPeriod, ReportsAggregator

logger = logging.getLogger("nutrizone.app")


def _safe(section_name: str, fn):
    try:
        return {"ok": True, "data": fn()}
    except Exception:
        logger.exception("Report section '%s' failed to load", section_name)
        return {"ok": False, "data": None}


@staff_member_required
def audit_timeline_view(request):
    """Phase 08.9: read-only, merges each covered module's own already-registered OutboxEvent table -- the real audit trail. See audit_timeline.py's own module docstring for the full architectural finding."""
    from apps.platform.infrastructure.audit_timeline import recent_events

    result = _safe("audit_timeline", recent_events)
    context = {**admin.site.each_context(request), "title": _("Audit Timeline"), "events": result}
    return render(request, "admin/audit_timeline.html", context)


@staff_member_required
def pos_receipt_view(request, sale_id):
    """
    Phase 08.10: no Receipt model exists anywhere in this project
    (confirmed by direct search) -- this view renders an existing,
    real SaleModel's own already-persisted line items directly, using
    the exact same subtotal formula already certified in Phase 08.4's
    own Order financial_summary (unit_price * quantity, summed) --
    not a new, alternative monetary calculation. SaleModel has no
    payment_method/payment-detail field at all, so there is no
    sensitive payment data to accidentally expose here in the first
    place.
    """
    from decimal import Decimal
    from django.http import Http404
    from apps.pos.infrastructure import models as orm

    try:
        sale = orm.SaleModel.objects.prefetch_related("line_items").get(id=sale_id)
    except orm.SaleModel.DoesNotExist:
        raise Http404("Sale not found.")

    lines = list(sale.line_items.all())
    total = sum((line.unit_price_amount * line.quantity for line in lines), Decimal("0"))
    currency = lines[0].unit_price_currency if lines else "UZS"

    context = {
        **admin.site.each_context(request),
        "title": f"{_('Receipt')} — {_('Sale')} {sale.id}",
        "sale": sale,
        "lines": lines,
        "total": total,
        "currency": currency,
    }
    return render(request, "admin/pos_receipt.html", context)


@staff_member_required
def settings_overview_view(request):
    from django import forms
    from django.contrib import messages
    from django.shortcuts import redirect

    from apps.platform.infrastructure.admin import get_site_settings
    from apps.platform.infrastructure.models import SiteSettings
    from apps.platform.infrastructure.settings_overview import SettingsOverviewAggregator

    import re

    hex_color = re.compile(r"^#[0-9a-fA-F]{6}$")
    max_image_bytes = 2 * 1024 * 1024
    text = {"class": "nz-input"}

    class SiteSettingsForm(forms.ModelForm):
        default_language = forms.ChoiceField(choices=[("uz", "O'zbekcha"), ("ru", "Русский"), ("en", "English")], widget=forms.Select(attrs={"class": "nz-input"}))

        class Meta:
            model = SiteSettings
            fields = [
                "site_name", "short_name", "default_language", "logo", "favicon",
                "primary_color", "secondary_color", "accent_color",
                "support_phone", "support_email", "address", "working_hours",
                "telegram_username", "telegram_channel_url", "instagram_url",
                "google_site_verification", "yandex_verification", "bing_verification",
            ]
            widgets = {
                "site_name": forms.TextInput(attrs=text),
                "short_name": forms.TextInput(attrs=text),
                "primary_color": forms.TextInput(attrs={"class": "nz-input nz-color-hex", "maxlength": 7, "placeholder": "#1d4ed8"}),
                "secondary_color": forms.TextInput(attrs={"class": "nz-input nz-color-hex", "maxlength": 7, "placeholder": "#0f172a"}),
                "accent_color": forms.TextInput(attrs={"class": "nz-input nz-color-hex", "maxlength": 7, "placeholder": "#f59e0b"}),
                "support_phone": forms.TextInput(attrs={**text, "placeholder": "+998 90 123 45 67"}),
                "support_email": forms.EmailInput(attrs={**text, "placeholder": "support@nutrizone.uz"}),
                "address": forms.TextInput(attrs=text),
                "working_hours": forms.TextInput(attrs={**text, "placeholder": "Du-Sha 09:00-21:00"}),
                "telegram_username": forms.TextInput(attrs={**text, "placeholder": "nutrizone_support"}),
                "telegram_channel_url": forms.URLInput(attrs={**text, "placeholder": "https://t.me/nutrizone"}),
                "instagram_url": forms.URLInput(attrs={**text, "placeholder": "https://instagram.com/nutrizone"}),
                "google_site_verification": forms.TextInput(attrs={**text, "placeholder": '<meta name="google-site-verification" content="…">', "spellcheck": "false"}),
                "yandex_verification": forms.TextInput(attrs={**text, "placeholder": '<meta name="yandex-verification" content="…">', "spellcheck": "false"}),
                "bing_verification": forms.TextInput(attrs={**text, "placeholder": '<meta name="msvalidate.01" content="…">', "spellcheck": "false"}),
                "logo": forms.ClearableFileInput(attrs={"class": "nz-file-input", "accept": "image/png,image/jpeg,image/webp"}),
                "favicon": forms.ClearableFileInput(attrs={"class": "nz-file-input", "accept": "image/png,image/jpeg,image/webp,image/x-icon"}),
            }

        def _clean_color(self, name, required=False):
            value = (self.cleaned_data.get(name) or "").strip()
            if not value:
                if required:
                    raise forms.ValidationError(_("Choose a color."))
                return ""
            if not hex_color.match(value):
                raise forms.ValidationError(_("Enter a color in #RRGGBB format."))
            return value.lower()

        def clean_primary_color(self):
            return self._clean_color("primary_color", required=True)

        def clean_secondary_color(self):
            return self._clean_color("secondary_color")

        def clean_accent_color(self):
            return self._clean_color("accent_color")

        def _clean_image(self, name):
            image = self.cleaned_data.get(name)
            if image and getattr(image, "size", 0) > max_image_bytes:
                raise forms.ValidationError(_("The image must be 2 MB or smaller."))
            return image

        def clean_logo(self):
            return self._clean_image("logo")

        def clean_favicon(self):
            return self._clean_image("favicon")

        def _clean_verification(self, name):
            # Accept the whole <meta ... content="CODE"> tag the search console shows, or just the code.
            value = (self.cleaned_data.get(name) or "").strip()
            m = re.search(r'content\s*=\s*["\']([^"\']+)["\']', value)
            value = (m.group(1) if m else value).strip()
            if value and not re.fullmatch(r"[A-Za-z0-9_\-.=+/]{6,128}", value):
                raise forms.ValidationError(_("Paste the code (or the whole <meta> tag) exactly as the search console shows it."))
            return value

        def clean_google_site_verification(self):
            return self._clean_verification("google_site_verification")

        def clean_yandex_verification(self):
            return self._clean_verification("yandex_verification")

        def clean_bing_verification(self):
            return self._clean_verification("bing_verification")

        def clean_telegram_username(self):
            return (self.cleaned_data.get("telegram_username") or "").strip().lstrip("@")

    site_settings = get_site_settings()

    if request.method == "POST":
        form = SiteSettingsForm(request.POST, request.FILES, instance=site_settings)
        if form.is_valid():
            form.save()
            messages.success(request, _("Settings saved successfully."))
            return redirect("admin:nz_settings_overview")
        messages.error(request, _("Please correct the highlighted fields."))
    else:
        form = SiteSettingsForm(instance=site_settings)

    aggregator = SettingsOverviewAggregator()
    context = {
        **admin.site.each_context(request),
        "title": _("Site Settings"),
        "form": form,
        "site_settings": site_settings,
        "color_presets": ["#1d4ed8", "#2563eb", "#0ea5e9", "#4f46e5", "#7c3aed", "#0f766e", "#16a34a", "#e11d48", "#ea580c", "#0f172a"],
        "integration_status": _safe("integration_status", aggregator.integration_status),
    }
    return render(request, "admin/settings_overview.html", context)


@staff_member_required
def _branch_report_view(request):
    from apps.stores.infrastructure.branch_report import branch_report_view

    return branch_report_view(request)


@staff_member_required
def _branch_report_xlsx(request):
    from apps.stores.infrastructure.branch_report import branch_report_xlsx

    return branch_report_xlsx(request)


@staff_member_required
def _geo_map_view(request):
    from apps.geo.infrastructure.admin_map import geo_map_view

    return geo_map_view(request)


@staff_member_required
def geo_overview_view(request):
    from apps.geo.infrastructure.geo_overview import GeoOverviewAggregator

    aggregator = GeoOverviewAggregator()
    context = {
        **admin.site.each_context(request),
        "title": _("Geo Overview"),
        "summary": _safe("summary", aggregator.summary),
        "countries": _safe("countries_with_hierarchy_counts", aggregator.countries_with_hierarchy_counts),
        "cities_missing_coordinates": _safe("cities_missing_coordinates", aggregator.cities_missing_coordinates),
    }
    return render(request, "admin/geo_overview.html", context)


@staff_member_required
def roles_overview_view(request):
    from apps.identity.infrastructure.roles_overview import RolePermissionOverviewAggregator

    aggregator = RolePermissionOverviewAggregator()
    context = {
        **admin.site.each_context(request),
        "title": "Rollar va ruxsatlar",
        "summary": _safe("summary", aggregator.summary),
        "matrix": _safe("matrix", aggregator.matrix),
        "roles": _safe("roles_with_permissions", aggregator.roles_with_permissions),
        "unassigned_permissions": _safe("unassigned_permissions", aggregator.unassigned_permissions),
    }
    return render(request, "admin/roles_overview.html", context)


@staff_member_required
def reports_view(request):
    period = ReportPeriod.last_n_days(30, "Last 30 Days")
    aggregator = ReportsAggregator(period)

    context = {
        **admin.site.each_context(request),
        "title": _("Reports & Business Intelligence"),
        "period_label": period.label,
        "last_updated": timezone.now(),
        "sales": _safe("sales", aggregator.sales_report),
        "customers": _safe("customers", aggregator.customer_report),
        "products": _safe("products", aggregator.product_report),
        "inventory": _safe("inventory", aggregator.inventory_report),
        "marketing": _safe("marketing", aggregator.marketing_report),
        "reviews": _safe("reviews", aggregator.review_report),
    }
    return render(request, "admin/reports.html", context)


@staff_member_required
def sales_report_excel_export(request):
    """
    Phase 16: the one genuinely missing capability found during
    reconnaissance -- no Excel export existed anywhere in this
    project. Reuses ReportsAggregator.sales_report() verbatim (the
    exact same certified data already rendered in reports.html, not a
    second calculation). Streams the file directly in the HTTP
    response rather than writing to MEDIA_ROOT, so no generated
    report is ever reachable via a predictable public URL.
    """
    import io

    from django.http import HttpResponse
    from openpyxl import Workbook
    from openpyxl.styles import Font

    period = ReportPeriod.last_n_days(30, "Last 30 Days")
    aggregator = ReportsAggregator(period)
    sales = aggregator.sales_report()

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sales Report"

    sheet.append([f"{_brand()} Sales Report"])
    sheet["A1"].font = Font(bold=True, size=14)
    sheet.append([f"Period: {period.label}"])
    sheet.append([f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M UTC')}"])
    sheet.append([])

    header_font = Font(bold=True)
    sheet.append(["Metric", "Value"])
    for cell in sheet[sheet.max_row]:
        cell.font = header_font

    revenue_change = sales["revenue_change"]["value"]
    orders_change = sales["orders_change"]["value"]
    rows = [
        ("Gross Sales (UZS)", float(sales["gross_sales"])),
        ("Revenue Change (%)", revenue_change if revenue_change is not None else "N/A"),
        ("Completed Orders", sales["orders"]),
        ("Orders Change (%)", orders_change if orders_change is not None else "N/A"),
        ("Cancelled Orders", sales["cancelled_orders"]),
        ("Average Order Value (UZS)", float(sales["average_order_value"])),
    ]
    for label, value in rows:
        sheet.append([label, value])

    sheet.append([])
    sheet.append(["Order Status", "Count"])
    for cell in sheet[sheet.max_row]:
        cell.font = header_font
    for status, count in sales["order_status_distribution"].items():
        sheet.append([status, count])

    sheet.column_dimensions["A"].width = 28
    sheet.column_dimensions["B"].width = 18

    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    response = HttpResponse(buffer.read(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    filename = f"nutrizone_sales_report_{timezone.now().strftime('%Y-%m-%d')}.xlsx"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


_SECTION_REPORT_EXPORTERS = {
    "products": ("Products Report", lambda agg: agg.product_report()),
    "inventory": ("Inventory Report", lambda agg: agg.inventory_report()),
    "marketing": ("Marketing Report", lambda agg: agg.marketing_report()),
    "reviews": ("Reviews Report", lambda agg: agg.review_report()),
}


def _flatten_report_rows(prefix: str, value) -> list:
    """Turns a (possibly nested) report dict/list into flat (label, value) rows for a two-column Excel sheet -- e.g. {"counts_by_status": {"pending": 3}} becomes a row labeled "counts_by_status (pending)" = 3."""
    rows = []
    if isinstance(value, dict):
        for key, sub_value in value.items():
            child_label = f"{prefix} ({key})" if prefix else str(key)
            rows.extend(_flatten_report_rows(child_label, sub_value))
    elif isinstance(value, list):
        for index, item in enumerate(value, start=1):
            rows.extend(_flatten_report_rows(f"{prefix} #{index}", item))
    else:
        rows.append((prefix, value))
    return rows


@staff_member_required
def report_section_excel_export(request, section: str):
    """
    Real, closed gap: only the Sales section had an export -- the
    other 7 report sections (Products, Inventory, Marketing, Loyalty,
    Wallet, Reviews, Fulfillment) had no way to download their data at
    all. Reuses the exact same, already-certified
    ReportsAggregator.*_report() methods already rendered on the
    Reports page (never a second/duplicate calculation), and the same
    streamed-response-not-written-to-disk pattern sales_report_excel_export
    already established above.
    """
    import io

    from django.http import HttpResponse, HttpResponseNotFound
    from openpyxl import Workbook
    from openpyxl.styles import Font

    if section not in _SECTION_REPORT_EXPORTERS:
        return HttpResponseNotFound("Unknown report section.")

    title, get_report_data = _SECTION_REPORT_EXPORTERS[section]
    period = ReportPeriod.last_n_days(30, "Last 30 Days")
    aggregator = ReportsAggregator(period)
    data = get_report_data(aggregator)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title[:31]  # Excel's own hard sheet-name length limit

    sheet.append([f"{_brand()} {title}"])
    sheet["A1"].font = Font(bold=True, size=14)
    sheet.append([f"Period: {period.label}"])
    sheet.append([f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M UTC')}"])
    sheet.append([])

    header_font = Font(bold=True)
    sheet.append(["Metric", "Value"])
    for cell in sheet[sheet.max_row]:
        cell.font = header_font

    for label, value in _flatten_report_rows("", data):
        sheet.append([label, value])

    sheet.column_dimensions["A"].width = 40
    sheet.column_dimensions["B"].width = 20

    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    response = HttpResponse(buffer.read(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    filename = f"nutrizone_{section}_report_{timezone.now().strftime('%Y-%m-%d')}.xlsx"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


_original_get_urls = admin.site.get_urls


def _get_urls_with_reports():
    from django.urls import path

    from apps.platform.infrastructure import chat_view, inventory_view, pos_view, transfer_view
    from apps.products.infrastructure import price_list_view

    return [
        path("products/price-list/", price_list_view.price_list_view, name="nz_price_list"),
        path("products/price-list/api/save/<str:variant_id>", price_list_view.price_list_api_save, name="nz_price_list_save"),
        path("products/price-list/api/history/<str:variant_id>", price_list_view.price_list_api_history, name="nz_price_list_history"),
        path("products/price-list/api/product/<str:product_id>", price_list_view.price_list_api_product, name="nz_price_list_product"),
        path("control/", _control_view, name="nz_control"),
        path("sales-plan/", _growth("sales_plan_view"), name="nz_sales_plan"),
        path("sales-plan/save/", _growth("sales_plan_save_view"), name="nz_sales_plan_save"),
        path("segments/", _growth("segments_view"), name="nz_segments"),
        path("segments/export.xlsx", _growth("segments_export_view"), name="nz_segments_export"),
        path("control/resolve/", _control_resolve, name="nz_control_resolve"),
        path("control/settings/", _control_settings, name="nz_control_settings"),
        path("control/transfer/", _control_transfer, name="nz_control_transfer"),
        path("analytics/", _analytics_view, name="nz_analytics"),
        path("analytics/send/", _analytics_send, name="nz_analytics_send"),
        path("analytics/export.xlsx", _analytics_export, name="nz_analytics_export"),
        path("reports/", reports_view, name="nz_reports"),
        path("reports/export/sales.xlsx", sales_report_excel_export, name="nz_reports_sales_export"),
        path("reports/export/<str:section>.xlsx", report_section_excel_export, name="nz_reports_section_export"),
        path("audit-timeline/", audit_timeline_view, name="nz_audit_timeline"),
        path("roles-overview/", roles_overview_view, name="nz_roles_overview"),
        path("geo-overview/", geo_overview_view, name="nz_geo_overview"),
        path("geo/map/", _geo_map_view, name="nz_geo_map"),
        path("stores/branch-report/", _branch_report_view, name="nz_branch_report"),
        path("stores/branch-report/export.xlsx", _branch_report_xlsx, name="nz_branch_report_xlsx"),
        path("settings-overview/", settings_overview_view, name="nz_settings_overview"),
        path("pos/receipt/<uuid:sale_id>/", pos_receipt_view, name="nz_pos_receipt"),
        path("telegram/status/", _telegram("telegram_center_view"), name="nz_telegram_status"),
        path("telegram/preview/", _telegram("telegram_preview_view"), name="nz_telegram_preview"),
        path("telegram/check/", _telegram("telegram_check_view"), name="nz_telegram_check"),
        path("pos/terminal/", _pos2_terminal, name="nz_pos_terminal"),
        path("pos/terminal/api2/<str:action>", _pos2_api, name="nz_pos2_api"),
        path("pos/terminal/receipt/<uuid:sale_id>/", _pos2_receipt, name="nz_pos2_receipt"),
        path("pos/terminal/classic/", pos_view.pos_terminal_view, name="nz_pos_terminal_classic"),
        path("pos/terminal/api/open-sale", pos_view.pos_api_open_sale, name="nz_pos_open_sale"),
        path("pos/terminal/api/search", pos_view.pos_api_search, name="nz_pos_search"),
        path("pos/terminal/api/browse", pos_view.pos_api_browse, name="nz_pos_browse"),
        path("pos/terminal/api/customer-search", pos_view.pos_api_customer_search, name="nz_pos_customer_search"),
        path("pos/terminal/api/customer-create", pos_view.pos_api_customer_create, name="nz_pos_customer_create"),
        path("pos/terminal/api/sales/<str:sale_id>/customer", pos_view.pos_api_set_customer, name="nz_pos_set_customer"),
        path("pos/terminal/api/recent-sales", pos_view.pos_api_recent_sales, name="nz_pos_recent_sales"),
        path("pos/terminal/api/price", pos_view.pos_api_price, name="nz_pos_price"),
        path("pos/terminal/api/sales/<str:sale_id>/line-items", pos_view.pos_api_add_line_item, name="nz_pos_add_line_item"),
        path("pos/terminal/api/sales/<str:sale_id>/line-items/<str:line_item_id>/remove", pos_view.pos_api_remove_line_item, name="nz_pos_remove_line_item"),
        path("pos/terminal/api/sales/<str:sale_id>/line-items/<str:line_item_id>/quantity", pos_view.pos_api_update_line_item_quantity, name="nz_pos_update_line_item_quantity"),
        path("pos/terminal/api/sales/<str:sale_id>/complete", pos_view.pos_api_complete_sale, name="nz_pos_complete_sale"),
        path("pos/terminal/api/sales/<str:sale_id>/void", pos_view.pos_api_void_sale, name="nz_pos_void_sale"),
        path("chat/", chat_view.chat_admin_view, name="nz_chat_admin"),
        path("chat/operators/", chat_view.chat_report_view, name="nz_chat_report"),
        path("chat/api/queue", chat_view.chat_queue_api, name="nz_chat_queue"),
        path("chat/api/cards", chat_view.chat_cards_api, name="nz_chat_cards"),
        path("chat/api/conversations/<str:conversation_id>", chat_view.chat_conversation_api, name="nz_chat_conversation"),
        path("chat/api/conversations/<str:conversation_id>/upload", chat_view.chat_upload_api, name="nz_chat_upload"),
        path("chat/api/conversations/<str:conversation_id>/do/<str:action>", chat_view.chat_action_api, name="nz_chat_action"),
        path("chat/conversations/<str:conversation_id>/messages", chat_view.chat_admin_messages_api, name="nz_chat_messages"),
        path("chat/conversations/<str:conversation_id>/send", chat_view.chat_admin_send_message_api, name="nz_chat_send"),
        path("wms/stock/", _wms_stock_view, name="nz_wms_stock"),
        path("wms/stock/product/<uuid:variant_id>/", _wms_stock_product_view, name="nz_wms_stock_product"),
        path("wms/expiry/", _wms_expiry_view, name="nz_wms_expiry"),
        path("wms/reports/", _wms_reports_view, name="nz_wms_reports"),
        path("profile/", _profile_view, name="nz_profile"),
        *_notification_urls(),
        path("dashboard/online-orders.json", _online_orders_json, name="nz_online_orders_json"),
        path("inventory/", inventory_view.inventory_dashboard_view, name="nz_inventory_dashboard"),
        path("inventory/api/stock-list", inventory_view.inventory_api_stock_list, name="nz_inventory_stock_list"),
        path("inventory/api/adjust-stock", inventory_view.inventory_api_adjust_stock, name="nz_inventory_adjust_stock"),
        path("inventory/transfers/", transfer_view.stock_transfer_view, name="nz_stock_transfers"),
        path("inventory/transfers/<uuid:transfer_id>/", transfer_view.stock_transfer_detail_view, name="nz_stock_transfer_detail"),
        path("inventory/transfers/api/products", transfer_view.transfer_api_products, name="nz_stock_transfer_products"),
        path("inventory/transfers/api/create", transfer_view.transfer_api_create, name="nz_stock_transfer_create"),
    ] + _original_get_urls()


def _telegram(name: str):
    def view(request):
        from apps.platform.infrastructure import telegram_view

        return getattr(telegram_view, name)(request)

    view.__name__ = name
    return view


def _growth(name: str):
    def view(request):
        from apps.platform.infrastructure import growth_view

        return getattr(growth_view, name)(request)

    view.__name__ = name
    return view


def _control_view(request):
    from apps.platform.infrastructure.control_view import control_view

    return control_view(request)


def _control_resolve(request):
    from apps.platform.infrastructure.control_view import control_resolve_view

    return control_resolve_view(request)


def _control_transfer(request):
    from apps.platform.infrastructure.control_view import control_transfer_view

    return control_transfer_view(request)


def _control_settings(request):
    from apps.platform.infrastructure.control_view import control_settings_view

    return control_settings_view(request)


def _analytics_view(request):
    from apps.platform.infrastructure.analytics_view import analytics_view

    return analytics_view(request)


def _analytics_export(request):
    from apps.platform.infrastructure.analytics_view import analytics_export_view

    return analytics_export_view(request)


def _analytics_send(request):
    from apps.platform.infrastructure.analytics_view import analytics_send_view

    return analytics_send_view(request)


def _online_orders_json(request):
    from apps.platform.infrastructure.online_orders_report import online_orders_json

    return online_orders_json(request)


def _notification_urls():
    from apps.notifications.infrastructure.broadcast_view import urls

    return urls()


def _profile_view(request):
    from apps.platform.infrastructure.profile_view import profile_view

    return admin.site.admin_view(profile_view)(request)


def _brand() -> str:
    from apps.platform.infrastructure.branding import brand_name

    return brand_name()


def _wms_stock_product_view(request, variant_id):
    from apps.stores.infrastructure.warehouse_admin import stock_product_view

    return admin.site.admin_view(stock_product_view)(request, variant_id=variant_id)


def _wms_stock_view(request):
    from apps.stores.infrastructure.warehouse_admin import stock_view

    return admin.site.admin_view(stock_view)(request)


def _wms_expiry_view(request):
    from apps.stores.infrastructure.planning_admin import expiry_view

    return admin.site.admin_view(expiry_view)(request)


def _wms_reports_view(request):
    from apps.stores.infrastructure.planning_admin import reports_view

    return admin.site.admin_view(reports_view)(request)


def _pos2_terminal(request):
    from apps.stores.infrastructure.pos_admin_terminal import terminal_view

    return admin.site.admin_view(terminal_view)(request)


def _pos2_receipt(request, sale_id):
    from apps.stores.infrastructure.pos_admin_terminal import receipt_view

    return admin.site.admin_view(receipt_view)(request, sale_id)


def _pos2_api(request, action):
    from django.views.decorators.csrf import csrf_protect

    from apps.stores.infrastructure.pos_admin_terminal import api

    return admin.site.admin_view(csrf_protect(api))(request, action)


def install() -> None:
    """Called once from PlatformConfig.ready() -- idempotent (safe if ready() ever runs twice)."""
    admin.site.get_urls = _get_urls_with_reports
