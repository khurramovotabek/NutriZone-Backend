"""Dashboard → Katalog → Birga arzonroq: staff-picked bundles + the automatic-bundle settings (bundles.py)."""
from __future__ import annotations

from decimal import Decimal

from django import forms
from django.contrib import admin, messages
from django.db.models import Count, Q
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html

from apps.platform.infrastructure import premium_admin as ui
from apps.platform.infrastructure.premium_admin import PremiumFormMixin, PremiumListMixin, hero_stat
from apps.products.infrastructure import bundles
from apps.products.infrastructure import models as orm


def _pct(value) -> str:
    return format(Decimal(str(value)).normalize(), "f")


def _name(product) -> str:
    return str(product) if product else "—"


class ProductBundleForm(forms.ModelForm):
    class Meta:
        model = orm.ProductBundle
        fields = ("product", "companion", "discount_percent", "is_active")
        help_texts = {
            "product": "Qaysi mahsulot sahifasida taklif chiqadi (masalan: Whey protein).",
            "companion": "Birga taklif qilinadigan mahsulot (masalan: shaker yoki kreatin). Chegirma shu mahsulotga beriladi.",
            "discount_percent": "Ikkinchi mahsulotga chegirma. Savatda ikkalasi ham bo'lsa avtomatik hisoblanadi (har bir juftga bir marta).",
            "is_active": "O'chirilsa sahifada avtomatik tavsiya (agar yoqilgan bo'lsa) ko'rinadi.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in ("product", "companion"):
            self.fields[f].queryset = orm.Product.objects.filter(status="published").prefetch_related("translations")

    def clean(self):
        data = super().clean()
        if data.get("product") and data.get("product") == data.get("companion"):
            self.add_error("companion", "Mahsulotni o'zi bilan to'plam qilib bo'lmaydi.")
        return data


@admin.register(orm.ProductBundle)
class ProductBundleAdmin(PremiumListMixin, PremiumFormMixin, admin.ModelAdmin):
    form = ProductBundleForm
    list_display = ("created_at",)
    list_select_related = ("product", "companion")
    search_fields = ("product__translations__name", "companion__translations__name")
    ordering = ("-updated_at",)
    autocomplete_fields = ()
    fieldsets = (("To'plam", {"fields": ("product", "companion", "discount_percent", "is_active")}),)
    actions = ["deactivate"]

    nz_icon, nz_tone, nz_title = "fa-cubes-stacked", "#10b981", "Birga arzonroq"
    nz_subtitle = ("Mahsulot sahifasidagi «Birga arzonroq» taklifi: asosiy mahsulot + ikkinchi mahsulot chegirma bilan, bitta tugma bilan savatga. "
                   "Bu yerda tanlangan juftlik avtomatik tavsiyadan ustun turadi.")
    nz_columns = (("Asosiy mahsulot", ""), ("Birga", ""), ("Chegirma", ""), ("Holat", "r"))
    nz_grid = "minmax(220px,2fr) minmax(220px,2fr) 110px 120px"
    nz_search = "Mahsulot nomi…"
    nz_empty = ("Hali qo'lda tanlangan to'plam yo'q", "Avtomatik to'plamlar «Birga xarid qilinadi» ma'lumotidan tuziladi. Maxsus juftlik uchun «Qo'shish»ni bosing.")
    hero_icon, hero_tone = "fa-cubes-stacked", "#10b981"

    def get_queryset(self, request):
        return super().get_queryset(request).distinct()

    def nz_stats(self, request):
        k = orm.ProductBundle.objects.aggregate(on=Count("id", filter=Q(is_active=True)), off=Count("id", filter=Q(is_active=False)))
        cfg = orm.BundleSettings.load()
        return [
            ui.stat_card("Faol juftliklar", k["on"], "#10b981", "fa-cubes-stacked", "qo'lda tanlangan"),
            ui.stat_card("O'chirilgan", k["off"], "#64748b", "fa-power-off"),
            ui.stat_card("Avtomatik to'plamlar", "Yoqilgan" if cfg.auto_enabled else "O'chirilgan", "#0ea5e9" if cfg.auto_enabled else "#64748b", "fa-wand-magic-sparkles",
                         f"−{_pct(cfg.auto_percent)}% · ustama ≥ {_pct(cfg.min_margin_percent)}%", reverse("admin:products_bundlesettings_changelist")),
        ]

    def nz_hero_actions(self, request):
        return [{"label": "Avtomatik sozlamalar", "url": reverse("admin:products_bundlesettings_changelist"), "icon": "fa-sliders"}]

    def nz_row(self, b):
        return [
            format_html("<b>{}</b>", _name(b.product)),
            format_html("<span>+ {}</span>", _name(b.companion)),
            format_html('<span class="nzi-pill" style="--t:#10b981">−{}%</span>', _pct(b.discount_percent)),
            format_html('<span class="nzi-pill" style="--t:{}">{}</span>', "#16a34a" if b.is_active else "#64748b", "Faol" if b.is_active else "O'chirilgan"),
        ]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        bundles.invalidate(obj.product_id)

    @admin.action(description="Tanlanganlarni o'chirish (nofaol qilish)")
    def deactivate(self, request, queryset):
        ids = list(queryset.values_list("product_id", flat=True))
        queryset.update(is_active=False)
        for pid in ids:
            bundles.invalidate(pid)
        messages.success(request, "Nofaol qilindi.")


class BundleSettingsForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # departments and their first level are enough to choose from (the choice covers everything under them)
        self.fields["companion_categories"].queryset = (orm.Category.objects.filter(Q(parent__isnull=True) | Q(parent__parent__isnull=True), is_active=True)
                                                        .prefetch_related("translations").order_by("parent__sort_order", "sort_order"))

    class Meta:
        model = orm.BundleSettings
        fields = ("auto_enabled", "auto_percent", "min_margin_percent", "max_companion_share", "companion_categories")
        widgets = {"companion_categories": forms.CheckboxSelectMultiple}
        help_texts = {
            "auto_enabled": "Qo'lda juftlik tanlanmagan mahsulotlarda tizim o'zi juftlik tanlaydi: mijozlar birga xarid qilgan, omborda bor, "
                            "iloji bo'lsa boshqa kategoriyadagi mahsulot (proteinga — shaker yoki kreatin).",
            "auto_percent": "Avtomatik juftlikda ikkinchi mahsulotga beriladigan chegirma.",
        }


@admin.register(orm.BundleSettings)
class BundleSettingsAdmin(PremiumFormMixin, admin.ModelAdmin):
    form = BundleSettingsForm
    fieldsets = (("Avtomatik to'plamlar", {"fields": ("auto_enabled", "auto_percent", "min_margin_percent", "max_companion_share")}),
                 ("Hamroh bo'limlar", {"fields": ("companion_categories",)}))
    hero_icon, hero_tone = "fa-wand-magic-sparkles", "#10b981"

    def changelist_view(self, request, extra_context=None):
        return redirect(reverse("admin:products_bundlesettings_change", args=[orm.BundleSettings.load().pk]))

    def get_object(self, request, object_id, from_field=None):
        return orm.BundleSettings.load()

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        _flush_bundle_cache()

    def response_change(self, request, obj):
        messages.success(request, "Saqlandi — mahsulot sahifalari yangi sozlama bilan ishlaydi.")
        return redirect(request.path)

    def form_hero(self, request, obj):
        on = orm.ProductBundle.objects.filter(is_active=True).count()
        return {
            "title": "Birga arzonroq — avtomatik", "subtitle": "qo'lda tanlanmagan mahsulotlar uchun",
            "chips": [ui.chip("Yoqilgan" if obj.auto_enabled else "O'chirilgan", "#16a34a" if obj.auto_enabled else "#64748b", "fa-power-off")],
            "stats": [
                hero_stat("Chegirma", f"−{_pct(obj.auto_percent)}%", "#10b981", "ikkinchi mahsulotga", "fa-percent"),
                hero_stat("Minimal ustama", f"{_pct(obj.min_margin_percent)}%", "#0ea5e9", "tannarxdan yuqori", "fa-shield-halved"),
                hero_stat("Qo'lda juftliklar", on, "#6366f1", "ular ustun turadi", "fa-cubes-stacked"),
            ],
            "links": [{"label": "Juftliklar", "url": reverse("admin:products_productbundle_changelist"), "icon": "fa-cubes-stacked", "primary": True}],
        }


def _flush_bundle_cache() -> None:
    """Django's own RedisCache has no delete_pattern: scan the raw keys (the cache key prefix is ':1:')."""
    from django.conf import settings

    try:
        import redis as redis_lib

        r = redis_lib.Redis.from_url(settings.REDIS_URL, socket_timeout=2)
        for key in r.scan_iter(match="*bundle:v2:*", count=500):
            r.delete(key)
    except Exception:  # noqa: BLE001 - the cache simply expires within the hour
        pass


