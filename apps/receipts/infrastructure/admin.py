"""
Dashboard → Cheklar: every receipt (POS, online, manual) with print (80 / 58 mm thermal, A4), e-receipt link and QR,
fiscalization; a manual receipt form; seller requisites and fiscal provider settings.
"""
from __future__ import annotations

import json

from django import forms
from django.contrib import admin, messages
from django.db.models import Count, Q, Sum
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from apps.platform.infrastructure import premium_admin as ui
from apps.platform.infrastructure.excel_export import Col, ExcelExportMixin
from apps.platform.infrastructure.premium_admin import PremiumFormMixin, PremiumListMixin, hero_stat
from apps.receipts.infrastructure import builders, fiscal
from apps.receipts.infrastructure.models import Receipt, ReceiptSettings, ReceiptSource, ReceiptStatus

STATUS_TONE = {"issued": "#2563eb", "fiscal_pending": "#f59e0b", "fiscalized": "#16a34a", "fiscal_failed": "#dc2626", "cancelled": "#94a3b8"}
SOURCE_ICON = {"pos": "fa-cash-register", "online": "fa-globe", "manual": "fa-pen"}
PAY_LABEL = {"cash": "Naqd", "card": "Karta", "uzcard": "Uzcard", "humo": "Humo", "payme": "Payme", "click": "Click", "uzum": "Uzum", "mixed": "Aralash"}


def money(v) -> str:
    try:
        return f"{int(float(v)):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "—"


@admin.register(Receipt)
class ReceiptAdmin(ExcelExportMixin, PremiumListMixin, PremiumFormMixin, admin.ModelAdmin):
    list_display = ("number", "issued_at")
    list_filter = ("source", "payment_method")
    search_fields = ("number", "order_number", "customer_phone", "customer_name", "fiscal_number")
    ordering = ("-issued_at",)
    list_per_page = 40
    readonly_fields = ("receipt_panel", "fiscal_panel")
    fieldsets = (("Chek", {"classes": ("nzi-panel",), "fields": ("receipt_panel",)}), ("Fiskal ma'lumot", {"classes": ("nzi-panel",), "fields": ("fiscal_panel",)}))
    excel_title = "Cheklar"
    actions = ["fiscalize_selected"]
    excel_columns = [Col("Raqam", "number", 14), Col("Sana", "issued_at", 17), Col("Manba", lambda r: r.get_source_display(), 14), Col("Holat", lambda r: r.get_status_display(), 16),
                     Col("Buyurtma", "order_number", 14), Col("Mijoz", "customer_name", 20), Col("Telefon", "customer_phone", 15),
                     Col("To'lov", lambda r: PAY_LABEL.get(r.payment_method, r.payment_method), 10), Col("Summa", "total", 14, money=True), Col("QQS", "vat_amount", 12, money=True),
                     Col("Fiskal raqam", "fiscal_number", 16), Col("Fiskal belgi", "fiscal_sign", 20)]

    nz_icon, nz_tone, nz_title = "fa-receipt", "#0d9488", "Cheklar"
    nz_subtitle = "POS, onlayn buyurtma va qo'lda yaratilgan barcha cheklar: chop etish, elektron chek (QR) va fiskallashtirish."
    nz_columns = (("Chek", ""), ("Mijoz", ""), ("To'lov", ""), ("Summa", "r"), ("Holat", "r"))
    nz_grid = "minmax(240px,2fr) minmax(170px,1.3fr) 120px 140px 150px"
    nz_search = "Chek / buyurtma raqami, telefon, fiskal raqam…"
    nz_empty = ("Chek yo'q", "POS sotuvi yoki onlayn buyurtma yetkazilganda chek avtomatik paydo bo'ladi.")
    hero_icon, hero_tone, hero_noun = "fa-receipt", "#0d9488", "chek"

    def has_add_permission(self, request):
        return False  # manual receipts have their own form (Yangi chek)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        wrap = self.admin_site.admin_view
        return [path("new/", wrap(self.manual_view), name="receipts_receipt_manual"),
                path("new/search.json", wrap(self.search_view), name="receipts_receipt_search"),
                path("<uuid:pk>/print/", wrap(self.print_view), name="receipts_receipt_print"),
                path("<uuid:pk>/fiscalize/", wrap(self.fiscalize_view), name="receipts_receipt_fiscalize"),
                *super().get_urls()]

    def lookup_allowed(self, lookup, value, request=None):
        return lookup in ("status__exact", "source__exact") or super().lookup_allowed(lookup, value, request)

    # ---------------------------------------------------------------- list
    def nz_stats(self, request):
        today = timezone.localdate()
        k = Receipt.objects.aggregate(n=Count("id"), today=Count("id", filter=Q(issued_at__date=today)), today_sum=Sum("total", filter=Q(issued_at__date=today)),
                                      fiscal=Count("id", filter=Q(status="fiscalized")), failed=Count("id", filter=Q(status="fiscal_failed")))
        base = reverse("admin:receipts_receipt_changelist")
        return [ui.stat_card("Bugun", k["today"], "#0d9488", "fa-receipt", f"{money(k['today_sum'] or 0)} so'm"),
                ui.stat_card("Jami cheklar", k["n"], "#2563eb", "fa-layer-group", "POS + onlayn + qo'lda"),
                ui.stat_card("Fiskallashtirilgan", k["fiscal"], "#16a34a", "fa-stamp", "soliq tizimida", base + "?status__exact=fiscalized"),
                ui.stat_card("Fiskal xato", k["failed"], "#dc2626", "fa-triangle-exclamation", "qayta yuborish kerak" if k["failed"] else "xatosiz", base + "?status__exact=fiscal_failed")]

    def nz_tabs(self, request):
        counts = dict(Receipt.objects.values_list("source").annotate(n=Count("id")))
        return ui.tabs_for(request, "source__exact", [("", "Hammasi", sum(counts.values()))] + [(v, label, counts.get(v, 0)) for v, label in ReceiptSource.choices],
                           {"pos": "#2563eb", "online": "#0d9488", "manual": "#8b5cf6"})

    def nz_hero_actions(self, request):
        return [{"label": "Sozlamalar", "url": reverse("admin:receipts_receiptsettings_changelist"), "icon": "fa-gear"},
                {"label": "Yangi chek", "url": reverse("admin:receipts_receipt_manual"), "icon": "fa-plus", "primary": True}]

    def nz_row(self, r):
        return [format_html('<span><i class="fas {}" aria-hidden="true" style="opacity:.6;margin-right:6px"></i><b>{}</b><small>{} · {}</small></span>',
                            SOURCE_ICON.get(r.source, "fa-receipt"), r.number, ui.local(r.issued_at, "%d.%m.%Y %H:%M"), r.order_number or r.get_source_display()),
                format_html("<b>{}</b><small>{}</small>", r.customer_name or "—", r.customer_phone),
                format_html("{}", PAY_LABEL.get(r.payment_method, r.payment_method or "—")),
                format_html("<b>{}</b> <small>so'm</small>", money(r.total)),
                format_html('<span class="nzi-pill" style="--t:{}">{}</span>', STATUS_TONE.get(r.status, "#64748b"), r.get_status_display())]

    # ---------------------------------------------------------------- card
    def form_hero(self, request, obj):
        links = [{"label": "Chop etish (80 mm)", "url": reverse("admin:receipts_receipt_print", args=[obj.pk]) + "?w=80", "icon": "fa-print", "primary": True, "external": True},
                 {"label": "A4", "url": reverse("admin:receipts_receipt_print", args=[obj.pk]) + "?w=a4", "icon": "fa-file-lines", "external": True}]
        from apps.pos.infrastructure.receipts import public_url

        if public_url(obj.token):
            links.append({"label": "Elektron chek", "url": public_url(obj.token), "icon": "fa-qrcode", "external": True})
        return {"title": f"Chek {obj.number}", "subtitle": f"{obj.get_source_display()} · {ui.local(obj.issued_at)}", "icon": "fa-receipt", "tone": STATUS_TONE.get(obj.status, "#0d9488"),
                "chips": [format_html('<span class="nzi-pill" style="--t:{}">{}</span>', STATUS_TONE.get(obj.status, "#64748b"), obj.get_status_display())],
                "links": links,
                "stats": [hero_stat("Summa", money(obj.total), "#0d9488", "so'm", "fa-coins"), hero_stat("QQS", money(obj.vat_amount), "#2563eb", "so'm (narx ichida)", "fa-percent"),
                          hero_stat("Chop etilgan", obj.printed, "#64748b", "marta", "fa-print")]}

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        return super().changeform_view(request, object_id, form_url, {**(extra_context or {}), "show_save": False, "show_save_and_continue": False, "show_delete": False})

    @admin.display(description="")
    def receipt_panel(self, obj):
        d = obj.data
        rows = format_html_join("", "<tr><td>{}<small style='display:block;opacity:.6'>{}</small></td><td style='text-align:right'>{} × {}</td><td style='text-align:right'><b>{}</b></td></tr>",
                                ((i["name"], " · ".join(x for x in (i.get("variant_label"), i.get("sku"), f"MXIK {i['mxik']}" if i.get("mxik") else "") if x),
                                  i["quantity"], money(i["unit_price"]), money(i["line_total"])) for i in d.get("items", [])))
        totals = format_html_join("", "<tr><td colspan='2'>{}</td><td style='text-align:right'>{}</td></tr>", (
            (label, money(d.get(k))) for k, label in (("subtotal", "Jami narx"), ("discount", "Chegirma"), ("coins", "Coin bilan"), ("delivery", "Yetkazish")) if float(d.get(k) or 0)))
        return format_html('<div class="nzi-panel-body"><table style="width:100%;border-collapse:collapse">{}{}<tr><td colspan="2"><b>To\'lov ({})</b></td><td style="text-align:right"><b>{} so\'m</b></td></tr></table></div>',
                           rows, totals, PAY_LABEL.get(obj.payment_method, obj.payment_method), money(obj.total))

    @admin.display(description="")
    def fiscal_panel(self, obj):
        if obj.status == ReceiptStatus.FISCALIZED:
            return format_html('<div class="nzi-panel-body"><p>Fiskal raqam: <b>{}</b> · Belgi: <b>{}</b> · Terminal: {}</p><p>{} · <a href="{}" target="_blank" rel="noopener">Soliq tizimida tekshirish ↗</a></p></div>',
                               obj.fiscal_number, obj.fiscal_sign, obj.fiscal_terminal_id, ui.local(obj.fiscalized_at), obj.fiscal_url or "#")
        err = format_html('<p style="color:#f87171">{}</p>', obj.fiscal_error) if obj.fiscal_error else ""
        url = reverse("admin:receipts_receipt_fiscalize", args=[obj.pk])
        return format_html('<div class="nzi-panel-body"><p>Chek hali fiskallashtirilmagan.</p>{}<form method="post" action="{}"><input type="hidden" name="csrfmiddlewaretoken" value="{}">'
                           '<button class="nzp-btn nzp-btn-primary" type="submit"><i class="fas fa-stamp"></i> Fiskallashtirish</button></form></div>', err, url, self._csrf)

    def render_change_form(self, request, context, *args, **kwargs):
        from django.middleware.csrf import get_token

        self._csrf = get_token(request)
        return super().render_change_form(request, context, *args, **kwargs)

    # ---------------------------------------------------------------- views
    def print_view(self, request, pk):
        r = get_object_or_404(Receipt, pk=pk)
        Receipt.objects.filter(pk=pk).update(printed=r.printed + 1)
        from apps.pos.infrastructure.receipts import public_url

        width = request.GET.get("w", "80")
        return render(request, "admin/receipts/print.html", {"r": r, "d": r.data, "width": width if width in ("58", "80", "a4") else "80",
                                                             "qr": r.fiscal_url or public_url(r.token) or "", "pay_label": PAY_LABEL})

    @admin.action(description="Tanlanganlarni fiskallashtirish (soliqqa yuborish)")
    def fiscalize_selected(self, request, queryset):
        ok, failed = 0, []
        for r in queryset.exclude(status__in=(ReceiptStatus.FISCALIZED, ReceiptStatus.CANCELLED))[:100]:
            try:
                fiscal.fiscalize(r)
                ok += 1
            except fiscal.FiscalError as exc:
                failed.append(f"{r.number}: {exc}")
                if "sozlama" in str(exc).lower() or "kalit" in str(exc).lower():
                    break  # a settings problem fails every receipt the same way -- stop at the first one
        if ok:
            messages.success(request, f"{ok} ta chek fiskallashtirildi.")
        if failed:
            messages.error(request, "Fiskallashtirilmadi — " + "; ".join(failed[:3]) + (f" (+{len(failed) - 3})" if len(failed) > 3 else ""))

    def fiscalize_view(self, request, pk):
        r = get_object_or_404(Receipt, pk=pk)
        if request.method == "POST":
            try:
                fiscal.fiscalize(r)
                messages.success(request, f"{r.number} fiskallashtirildi.")
            except fiscal.FiscalError as exc:
                messages.error(request, f"Fiskallashtirilmadi: {exc}")
        return HttpResponseRedirect(reverse("admin:receipts_receipt_change", args=[pk]))

    def manual_view(self, request):
        error = ""
        if request.method == "POST":
            try:
                lines = json.loads(request.POST.get("lines") or "[]")
                r = builders.manual(lines=lines, customer_name=request.POST.get("customer_name", "").strip(), customer_phone=request.POST.get("customer_phone", "").strip(),
                                    payment_method=request.POST.get("payment_method") or "cash", note=request.POST.get("note", "").strip(),
                                    kind=request.POST.get("kind") or "sale", staff=request.user.get_full_name() or request.user.get_username())
                messages.success(request, f"{r.number} chek yaratildi.")
                return HttpResponseRedirect(reverse("admin:receipts_receipt_change", args=[r.pk]))
            except (ValueError, KeyError, TypeError) as exc:
                error = str(exc) or "Ma'lumotlar noto'g'ri."
        return render(request, "admin/receipts/manual.html", {**self.admin_site.each_context(request), "title": "Yangi chek", "error": error,
                                                              "search_url": reverse("admin:receipts_receipt_search"), "pay_label": PAY_LABEL})

    def search_view(self, request):
        """Variants by barcode (incl. DataMatrix) / SKU / name with their current price -- for the manual receipt form."""
        from django.http import JsonResponse

        from apps.products.infrastructure import barcodes
        from apps.products.infrastructure.models import ProductVariant
        from apps.stores.infrastructure.stock_service import variant_infos

        q = (request.GET.get("q") or "").strip()
        if len(q) < 2:
            return JsonResponse({"results": []})
        match = barcodes.resolve(q)
        if match is not None:
            ids = [match.variant.id]
        else:
            ids = list(ProductVariant.objects.filter(Q(sku__icontains=q) | Q(product__translations__name__icontains=q), status="active").values_list("id", flat=True).distinct()[:12])
        infos = variant_infos(ids)
        return JsonResponse({"results": [{"variant_id": str(i), "name": infos[i].name + (f" · {infos[i].size}" if infos[i].size else ""), "sku": infos[i].sku,
                                          "price": str(infos[i].price or 0)} for i in ids if i in infos]})


EPOS_ENDPOINT = "https://api.epos.uz/v1/receipts"


class ReceiptSettingsForm(forms.ModelForm):
    """The provider key is write-only: typed once, stored encrypted, shown back only as ••••1234."""

    fiscal_secret = forms.CharField(label="API kaliti / parol", required=False, strip=True,
                                    widget=forms.PasswordInput(render_value=False, attrs={"class": "vTextField form-control", "style": "max-width:620px;width:100%", "autocomplete": "new-password", "placeholder": "Yangi kalit (o'zgartirmaslik uchun bo'sh qoldiring)"}))
    fiscal_secret_clear = forms.BooleanField(label="Saqlangan kalitni o'chirish", required=False)

    class Meta:
        model = ReceiptSettings
        exclude = ("fiscal_secret_encrypted", "fiscal_checked_at", "fiscal_check_result")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.payment.infrastructure.crypto import decrypt_secrets, mask

        stored = decrypt_secrets(self.instance.fiscal_secret_encrypted).get("secret", "") if self.instance.pk else ""
        self.fields["fiscal_secret"].help_text = (f"Saqlangan: {mask(stored)} (shifrlangan)." if stored else
                                                  "Kalit kiritilmagan" + (" — serverdagi FISCAL_API_TOKEN ishlatiladi." if self.instance.fiscal_secret else "."))

    def clean(self):
        data = super().clean()
        if data.get("fiscal_provider") == "epos" and not data.get("fiscal_endpoint"):
            data["fiscal_endpoint"] = EPOS_ENDPOINT
        if data.get("fiscal_provider") in ("http", "epos"):
            endpoint = data.get("fiscal_endpoint") or ""
            if endpoint and not endpoint.startswith("https://"):
                self.add_error("fiscal_endpoint", "Faqat https:// manzil — kalit ochiq kanal orqali yuborilmasin.")
            if data.get("fiscal_auth") == "basic" and not data.get("fiscal_login"):
                self.add_error("fiscal_login", "«Login + parol» turi uchun login kerak.")
            if data.get("fiscal_auth") == "header" and not (data.get("fiscal_auth_header") or "").strip():
                self.add_error("fiscal_auth_header", "Sarlavha nomini kiriting (masalan X-API-Key).")
        if data.get("fiscal_timeout") is not None and not 3 <= data["fiscal_timeout"] <= 60:
            self.add_error("fiscal_timeout", "3–60 soniya.")
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.cleaned_data.get("fiscal_secret_clear"):
            obj.set_fiscal_secret("")
        elif self.cleaned_data.get("fiscal_secret"):
            obj.set_fiscal_secret(self.cleaned_data["fiscal_secret"])
        if commit:
            obj.save()
        return obj


@admin.register(ReceiptSettings)
class ReceiptSettingsAdmin(PremiumFormMixin, admin.ModelAdmin):
    form = ReceiptSettingsForm
    readonly_fields = ("fiscal_readiness",)
    fieldsets = (
        ("Fiskal tayyorlik", {"classes": ("nzi-panel",), "fields": ("fiscal_readiness",)}),
        ("Sotuvchi rekvizitlari (chekda ko'rinadi)", {"fields": ("legal_name", "tin", "address", "phone", "footer")}),
        ("QQS", {"fields": ("vat_payer", "vat_rate")}),
        ("Payme virtual kassasi", {"fields": ("payme_fiscal",)}),
        ("Kassa / OFD provayderi (E-POS va boshqalar)", {
            "fields": ("fiscal_provider", "fiscal_endpoint", "fiscal_terminal_id", "fiscal_cashier_id", "fiscal_auth", "fiscal_auth_header", "fiscal_login",
                       "fiscal_secret", "fiscal_secret_clear", "fiscal_timeout", "fiscal_auto")}),
    )
    hero_icon, hero_tone, hero_noun = "fa-gear", "#0d9488", "sozlama"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        ReceiptSettings.get()
        return HttpResponseRedirect(reverse("admin:receipts_receiptsettings_change", args=[1]))

    def form_hero(self, request, obj):
        return {"title": "Chek sozlamalari", "subtitle": "Rekvizitlar, QQS va fiskal provayder", "icon": "fa-gear", "tone": "#0d9488"}

    @admin.display(description="Holat")
    def fiscal_readiness(self, obj):
        checks = fiscal.readiness(obj)
        done = sum(1 for _l, ok, _h in checks if ok)
        rows = format_html_join("", '<li style="display:flex;gap:8px;align-items:baseline;padding:3px 0"><span style="color:{};font-weight:700">{}</span>'
                                    '<b>{}</b><small style="opacity:.7">{}</small></li>',
                                (("#16a34a" if ok else "#dc2626", "✓" if ok else "✗", label, hint) for label, ok, hint in checks))
        last = format_html('<p style="margin-top:10px"><b>Oxirgi tekshiruv:</b> {} <small style="opacity:.7">{}</small></p>',
                           obj.fiscal_check_result, ui.local(obj.fiscal_checked_at, "%d.%m.%Y %H:%M")) if obj.fiscal_checked_at else ""
        return format_html('<div class="nzi-panel-body"><p style="opacity:.8">Ikki yo\'l: <b>Payme virtual kassasi</b> — Payme bilan to\'langan buyurtmalarga soliq cheki va QR kodni '
                           'Payme o\'zi chiqaradi (Payme Business\'da fiskalizatsiyani yoqing, kalitlar To\'lov tizimlari sahifasida); '
                           '<b>E-POS yoki boshqa OFD</b> — kassa va qolgan cheklar uchun. Kalitlar shifrlangan holda saqlanadi.</p><p><b>{}/{}</b> tayyor{}</p><ul style="list-style:none;margin:8px 0 0;padding:0">{}</ul>{}'
                           '<p style="margin-top:12px"><button type="submit" name="_fiscal_check" value="1" class="button" '
                           'style="padding:8px 14px;border-radius:10px"><i class="fas fa-plug" aria-hidden="true"></i> Saqlash va ulanishni tekshirish</button> '
                           '<small style="opacity:.7">Chek yuborilmaydi — faqat server va kalit tekshiriladi.</small></p></div>',
                           done, len(checks), " — fiskallashtirish mumkin" if done == len(checks) else "", rows, last)

    def response_change(self, request, obj):
        if "_fiscal_check" in request.POST:
            ok, text = fiscal.check_connection(ReceiptSettings.get())
            (messages.success if ok else messages.error)(request, text)
            return HttpResponseRedirect(request.path)
        return super().response_change(request, obj)
