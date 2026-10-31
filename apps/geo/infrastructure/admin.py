"""
Dashboard → Geo & Location: Davlatlar, Viloyatlar, Tumanlar, Shaharlar, Manzillar -- premium lists and forms
(apps/platform/infrastructure/premium_admin.py) with uz / ru / en name tabs, maps with a layer switcher
(Xarita · Sputnik · Gibrid · Relyef), a point editor (click / drag / search / pasted Yandex-Google-Apple-2GIS link /
my location) and "open in" links. The "Manzillar xaritasi" page (geo/infrastructure/admin_map.py) shows customers'
addresses and the stores on one map.

Deletes of countries / regions / cities still go through the Application Services (they refuse to delete a place
that is in use); districts and addresses are plain rows.
"""
from __future__ import annotations

from django import forms
from django.conf import settings
from django.contrib import admin
from django.db.models import Case, Count, IntegerField, OuterRef, Q, Subquery, Value, When
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from apps.geo.application.services._shared import GeoServiceContext
from apps.geo.application.services.hierarchy import DeleteCity, DeleteCountry, DeleteRegion
from apps.geo.infrastructure import models as orm
from apps.geo.infrastructure.repositories import (
    DjangoCityRepository,
    DjangoCountryRepository,
    DjangoRegionRepository,
)
from apps.platform.infrastructure import excel_export as xl
from apps.platform.infrastructure import premium_admin as ui
from apps.platform.infrastructure.excel_export import Col, ExcelExportMixin
from apps.platform.infrastructure.premium_admin import PremiumFormMixin, PremiumListMixin, hero_stat
from apps.products.infrastructure.catalog_form_ui import TranslationInlineMixin
from core.outbox import stage_event

LOCALES = ("uz", "ru", "en")
GEO_JS_V = "6"  # bump after editing nutrizone-geo-admin.js
GEO_CSS = ("admin/css/nutrizone-geo.css",)
STATUS_COLORS = {"active": "#16a34a", "inactive": "#94a3b8"}
STATUS_LABELS = {"active": "Faol", "inactive": "O'chirilgan"}
ADDRESS_TYPES = {"residential": ("Uy", "fa-house", "#4f46e5"), "office": ("Ofis", "fa-briefcase", "#0891b2"), "commercial": ("Biznes", "fa-store", "#ea580c"),
                 "warehouse": ("Ombor", "fa-warehouse", "#64748b"), "pickup_point": ("Olib ketish punkti", "fa-box", "#16a34a")}
SOURCES = {  # how the point was found → (label, color, icon)
    "gps": ("GPS", "#16a34a", "fa-location-crosshairs"), "map_pin": ("Xaritada belgilangan", "#4f46e5", "fa-map-pin"),
    "search": ("Qidiruvdan", "#0891b2", "fa-magnifying-glass"), "link": ("Havoladan", "#9333ea", "fa-link"),
    "telegram_native_share": ("Telegram lokatsiya", "#0284c7", "fa-paper-plane"), "manual": ("Qo'lda", "#64748b", "fa-keyboard"),
}


def _stage_geo_events(events: list[tuple[str, dict]]) -> None:
    for event_type, payload in events:
        stage_event(orm.GeoOutboxEvent, event_type, payload)


def _admin_ctx(request) -> GeoServiceContext:
    return GeoServiceContext(stage_events=_stage_geo_events, actor_id=getattr(request.user, "id", None))


def _titled(filter_cls, title):
    class Titled(filter_cls):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.title = title

    return Titled


# ---------------------------------------------------------------- shared cells


def names(obj) -> dict:
    return {t.locale_code: t.name for t in obj.translations.all()} if obj is not None else {}


def uz_name(obj, fallback: str = "—") -> str:
    if obj is None:
        return fallback
    n = names(obj)
    return n.get("uz") or n.get("en") or n.get("ru") or getattr(obj, "code", fallback)


def _uz_name_sq(translation_model, fk: str):
    """Subquery: the row's Uzbek name -- lists sort A-Z the way the team reads them."""
    return Subquery(translation_model.objects.filter(**{fk: OuterRef("pk"), "locale_code": "uz"}).values("name")[:1])


def flag(code: str | None, emoji: str | None = "", size: int = 28) -> str:
    """A real flag image (flagcdn, retina srcset) -- emoji flags don't render on Windows."""
    if not code:
        return mark_safe('<span class="nzg-flag nzg-flag-empty"><i class="fas fa-globe" aria-hidden="true"></i></span>')
    c = code.lower()
    return format_html('<span class="nzg-flag" style="--w:{}px"><img src="https://flagcdn.com/w40/{}.png" srcset="https://flagcdn.com/w80/{}.png 2x" alt="{}" loading="lazy"></span>',
                       size, c, c, emoji or code.upper())


def place(obj, icon: str, tone: str, lead: str = "", extra: str = "") -> str:
    """Icon (or flag) + the Uzbek name + "ru · en" below."""
    n = names(obj)
    main = n.get("uz") or n.get("en") or n.get("ru") or obj.code
    sub = " · ".join(v for v in (n.get("ru"), n.get("en")) if v and v != main)
    lead = lead or format_html('<span class="nzg-ico" style="--t:{}"><i class="fas {}" aria-hidden="true"></i></span>', tone, icon)
    return format_html('<span class="nzg-place">{}<span><b>{}</b><small>{}{}</small></span></span>', lead, main, sub or "tarjima yo'q", mark_safe(extra))


def langs(obj) -> str:
    have = set(names(obj))
    return format_html('<span class="nzg-langs">{}</span>', mark_safe("".join(f'<span class="{"" if c in have else "no"}">{c.upper()}</span>' for c in LOCALES)))


def num(n, unit: str = "ta") -> str:
    return format_html('<span class="nzg-num"><b>{}</b><small>{}</small></span>', n or 0, unit)


def status_pill(status: str) -> str:
    return format_html('<span class="nzi-pill" style="--t:{}">{}</span>', STATUS_COLORS.get(status, "#94a3b8"), STATUS_LABELS.get(status, status))


def code_cell(code: str) -> str:
    return format_html('<span class="nzg-code">{}</span>', code)


def map_links(lat, lng, label: str = "") -> str:
    """Yandex (pin + ready route) · Google · Apple Maps (iPhone opens the Maps app) · 2GIS -- the same set as the storefront."""
    from urllib.parse import quote

    if lat is None or lng is None:
        return ""
    la, ln = f"{lat:.6f}", f"{lng:.6f}"
    items = [("Yandex", f"https://yandex.uz/maps/?pt={ln},{la}&z=17&l=map", "#FC3F1D"), ("Yo'nalish", f"https://yandex.uz/maps/?rtext=~{la},{ln}&rtt=auto", "#FC3F1D"),
             ("Google", f"https://www.google.com/maps/search/?api=1&query={la},{ln}", "#1a73e8"), ("Apple", f"https://maps.apple.com/?ll={la},{ln}&q={quote(label or 'Manzil')}", "#8b5cf6"),
             ("2GIS", f"https://2gis.uz/geo/{ln},{la}", "#19aa1e")]
    return format_html('<span class="nzgeo-links">{}</span>', mark_safe("".join(str(format_html('<a href="{}" target="_blank" rel="noopener" style="--t:{}">{}</a>', u, c, t)) for t, u, c in items)))


def accuracy_chip(meters) -> str:
    if meters is None:
        return ""
    color, label = ("#16a34a", "aniq") if meters <= 30 else ("#d97706", "taxminiy") if meters <= 150 else ("#dc2626", "past aniqlik")
    return ui.chip(f"±{round(meters)} m · {label}", color, "fa-bullseye")


def point_picker(lat_id: str, lng_id: str, source_id: str = "", accuracy_id: str = "") -> str:
    """The map editor bound to two coordinate inputs (nutrizone-geo-admin.js); optionally also fills "how found" + accuracy."""
    return format_html(
        '<div class="nzgeo-picker" data-nzgeo-picker data-lat="{}" data-lng="{}" data-source="{}" data-accuracy="{}">'
        '<div class="nzgeo-tools" data-tools>'
        '<div><input type="search" placeholder="Joy yoki ko\'cha: Chorsu, Amir Temur 15…" data-q aria-label="Joy qidirish"><div class="nzgeo-results" data-results hidden></div></div>'
        '<div><input type="text" placeholder="Yandex / Google / Apple / 2GIS havolasi yoki 41.31, 69.27" data-link aria-label="Xarita havolasi">'
        '<button type="button" data-paste><i class="fas fa-link" aria-hidden="true"></i> Joylash</button></div></div>'
        '<div class="nzgeo-map" data-map></div>'
        '<div class="nzgeo-actions"><button type="button" data-me><i class="fas fa-location-crosshairs" aria-hidden="true"></i> Mening joylashuvim</button>'
        '<button type="button" data-clear><i class="fas fa-eraser" aria-hidden="true"></i> Tozalash</button>'
        '<span class="nzgeo-status" data-status>Xaritada bosing yoki pinni suring</span><span data-links></span></div></div>',
        lat_id, lng_id, source_id, accuracy_id,
    )


def point_view(lat, lng, label: str = "", accuracy=None, big: bool = False) -> str:
    if lat is None or lng is None:
        return mark_safe('<p class="nzi-muted"><i class="fas fa-location-dot" aria-hidden="true"></i> Koordinata yo\'q — xaritada belgilanmagan.</p>')
    return format_html('<div class="nzgeo-map{}" data-nzgeo-view data-lat="{}" data-lng="{}" data-label="{}" data-accuracy="{}"></div>',
                       " lg" if big else "", f"{lat:.6f}", f"{lng:.6f}", label, accuracy if accuracy is not None else "")


class GeoMapMedia:
    """Leaflet + the geo map script on every geo add / change page."""

    class Media:
        css = {"all": ("admin/vendor/leaflet/leaflet.css",)}
        js = ("admin/vendor/leaflet/leaflet.js", f"{settings.STATIC_URL}admin/js/nutrizone-geo-admin.js?v={GEO_JS_V}")  # absolute → Django keeps the ?v cache-buster


class _Translations(TranslationInlineMixin, admin.StackedInline):
    fields = ("locale_code", "name", "slug")
    verbose_name = _("Nomi")
    verbose_name_plural = _("Nomi (uz · ru · en)")


class CountryTranslationInline(_Translations):
    model = orm.CountryTranslation


class RegionTranslationInline(_Translations):
    model = orm.RegionTranslation


class DistrictTranslationInline(_Translations):
    model = orm.DistrictTranslation


class CityTranslationInline(_Translations):
    model = orm.CityTranslation


class _StatusActions:
    """Faollashtirish / o'chirish for any geo level (status, not delete -- addresses keep pointing at it)."""

    FIELD_LABELS = {"code": "Kod", "status": "Holat", "region": "Viloyat", "country": "Davlat", "district": "Tuman", "icon": "Bayroq (emoji)", "timezone": "Vaqt mintaqasi"}
    FIELD_HELP = {"code": "Lotin harf va raqam, takrorlanmas (masalan UZ, UZ-SA, TSH-CHI).", "icon": "Bo'sh qoldiring — kod bo'yicha avtomatik qo'yiladi."}

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        for name, label in self.FIELD_LABELS.items():
            if name in form.base_fields:
                form.base_fields[name].label = label
                if name in self.FIELD_HELP:
                    form.base_fields[name].help_text = self.FIELD_HELP[name]
        if "status" in form.base_fields:
            form.base_fields["status"].choices = [(k, v) for k, v in STATUS_LABELS.items()]
        return form

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name in ("country", "region", "district") and field is not None:
            field.queryset = field.queryset.prefetch_related("translations")
            field.label_from_instance = lambda o: uz_name(o)
        return field

    @admin.action(description="Faollashtirish")
    def make_active(self, request, queryset):
        self.message_user(request, f"{queryset.update(status='active')} ta faollashtirildi.")

    @admin.action(description="O'chirish (saytda ko'rinmaydi)")
    def make_inactive(self, request, queryset):
        self.message_user(request, f"{queryset.update(status='inactive')} ta o'chirildi — saytda tanlab bo'lmaydi.")

    def _status_tabs(self, request, qs):
        counts = dict(qs.values_list("status").annotate(n=Count("id")))
        return ui.tabs_for(request, "status__exact", [("", "Hammasi", sum(counts.values())), ("active", "Faol", counts.get("active", 0)), ("inactive", "O'chirilgan", counts.get("inactive", 0))],
                           {"active": "#16a34a", "inactive": "#94a3b8"})

    def lookup_allowed(self, lookup, value, request=None):
        return lookup in ("status__exact",) or super().lookup_allowed(lookup, value, request)

    def _service_delete(self, request, queryset, service, noun: str):
        done = 0
        for obj in queryset:
            try:
                service.execute(obj.id)
                done += 1
            except Exception as exc:  # noqa: BLE001 - reported per row
                self.message_user(request, f"{uz_name(obj)}: o'chirib bo'lmadi — {exc}", level="error")
        if done:
            self.message_user(request, f"{done} ta {noun} o'chirildi.")


# ---------------------------------------------------------------- Davlatlar


@admin.register(orm.Country)
class CountryAdmin(_StatusActions, GeoMapMedia, PremiumListMixin, PremiumFormMixin, admin.ModelAdmin):
    list_filter = (("status", _titled(admin.ChoicesFieldListFilter, "Holat")),)
    search_fields = ("code", "translations__name")
    inlines = [CountryTranslationInline]
    fieldsets = (("Davlat", {"fields": ("code", "icon", "status", "timezone")}),)
    actions = ["make_active", "make_inactive", "delete_via_service"]
    list_per_page = 30

    nz_icon, nz_tone, nz_title = "fa-earth-asia", "#2563eb", "Davlatlar"
    nz_subtitle = "Yetkazib berish davlati (O'zbekiston) va mahsulotlarning ishlab chiqarilgan davlatlari. Bayroq kod bo'yicha avtomatik."
    nz_columns = (("Davlat", ""), ("Kod", ""), ("Vaqt mintaqasi", ""), ("Tillar", ""), ("Viloyatlar", "r"), ("Mahsulotlar", "r"))
    nz_grid = "minmax(230px,2fr) 70px minmax(130px,1fr) 110px 100px 110px"
    nz_search = "Davlat nomi yoki kodi…"
    nz_empty = ("Davlat yo'q", "«Yangi davlat» bilan qo'shing.")
    nz_sorts = (("O'zbekiston birinchi", ""), ("Ko'p mahsulot", "-6"), ("Kod", "2"))
    nz_css = GEO_CSS
    hero_icon, hero_tone, hero_noun = "fa-earth-asia", "#2563eb", "davlat"

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("translations").annotate(
            n_regions=Count("regions", filter=Q(regions__is_deleted=False), distinct=True),
            n_products=Count("manufactured_products", filter=Q(manufactured_products__is_deleted=False), distinct=True),
            home_first=Case(When(code="UZ", then=Value(0)), default=Value(1), output_field=IntegerField()),
            uz_sort=_uz_name_sq(orm.CountryTranslation, "country"),
        ).order_by("home_first", "uz_sort")

    def nz_stats(self, request):
        qs = orm.Country.objects.annotate(n=Count("manufactured_products", filter=Q(manufactured_products__is_deleted=False)))
        makers = qs.filter(n__gt=0)
        top = makers.order_by("-n").prefetch_related("translations").first()
        return [
            ui.stat_card("Davlatlar", qs.count(), "#2563eb", "fa-earth-asia", f"{qs.filter(status='active').count()} faol", "?status__exact=active"),
            ui.stat_card("Ishlab chiqaruvchi", makers.count(), "#16a34a", "fa-industry", "mahsuloti bor davlatlar"),
            ui.stat_card("Viloyatlar", orm.Region.objects.count(), "#f59e0b", "fa-map", f"{orm.City.objects.count()} ta shahar", reverse("admin:geo_region_changelist")),
            ui.stat_card("Yetakchi", uz_name(top) if top else "—", "#db2777", "fa-crown", f"{top.n} ta mahsulot" if top else "mahsulot biriktirilmagan"),
        ]

    def nz_tabs(self, request):
        return self._status_tabs(request, orm.Country.objects.all())

    def nz_hero_actions(self, request):
        return [{"label": "Manzillar xaritasi", "url": reverse("admin:nz_geo_map"), "icon": "fa-map-location-dot"},
                {"label": "Yangi davlat", "url": reverse("admin:geo_country_add"), "icon": "fa-plus", "primary": True}]

    def nz_row(self, c):
        tz = "—"
        if c.timezone:
            try:
                from zoneinfo import ZoneInfo

                from django.utils import timezone as djtz

                now = djtz.now().astimezone(ZoneInfo(c.timezone))
                tz = format_html('<span class="nzg-addr"><b>{}</b><small>UTC{} · hozir {}</small></span>', c.timezone.split("/")[-1].replace("_", " "), now.strftime("%z")[:3] + ":" + now.strftime("%z")[3:], now.strftime("%H:%M"))
            except Exception:  # noqa: BLE001
                tz = c.timezone
        return [place(c, "", "", lead=flag(c.code, c.icon, 34)), code_cell(c.code), tz, langs(c), num(c.n_regions), num(c.n_products)]

    def form_hero(self, request, obj):
        if obj is None:
            return {"subtitle": "ISO kod (UZ, US, DE…) kiriting — bayroq avtomatik qo'yiladi"}
        n = names(obj)
        return {
            "title": uz_name(obj), "subtitle": " · ".join(v for v in (n.get("ru"), n.get("en")) if v), "image": f"https://flagcdn.com/w160/{obj.code.lower()}.png",
            "chips": [status_pill(obj.status), code_cell(obj.code)],
            "stats": [hero_stat("Viloyatlar", obj.regions.count(), "#f59e0b", "kiritilgan", "fa-map"),
                      hero_stat("Shaharlar", orm.City.objects.filter(region__country=obj).count(), "#0d9488", "yetkazish uchun", "fa-city"),
                      hero_stat("Manzillar", obj.addresses.count(), "#8b5cf6", "mijozlarniki", "fa-house"),
                      hero_stat("Mahsulotlar", obj.manufactured_products.filter(is_deleted=False).count(), "#16a34a", "shu yerda ishlab chiqarilgan", "fa-box")],
            "links": [{"label": "Viloyatlari", "url": reverse("admin:geo_region_changelist") + f"?country__id__exact={obj.pk}", "icon": "fa-map"}],
        }

    @admin.action(description="Tanlanganlarni o'chirish (ishlatilmayotgan bo'lsa)")
    def delete_via_service(self, request, queryset):
        self._service_delete(request, queryset, DeleteCountry(DjangoCountryRepository(), _admin_ctx(request)), "davlat")


# ---------------------------------------------------------------- Viloyatlar


@admin.register(orm.Region)
class RegionAdmin(_StatusActions, GeoMapMedia, PremiumListMixin, PremiumFormMixin, admin.ModelAdmin):
    list_filter = (("status", _titled(admin.ChoicesFieldListFilter, "Holat")), ("country", _titled(admin.RelatedFieldListFilter, "Davlat")))
    search_fields = ("code", "translations__name")
    inlines = [RegionTranslationInline]
    readonly_fields = ("cities_panel",)
    actions = ["make_active", "make_inactive", "delete_via_service"]
    list_per_page = 30

    nz_icon, nz_tone, nz_title = "fa-map", "#f59e0b", "Viloyatlar"
    nz_subtitle = "Manzil formasida birinchi tanlanadigan hudud. Har viloyatda shaharlar va (kerak bo'lsa) tumanlar bor."
    nz_columns = (("Viloyat", ""), ("Davlat", ""), ("Kod", ""), ("Tillar", ""), ("Tumanlar", "r"), ("Shaharlar", "r"), ("Manzillar", "r"))
    nz_grid = "minmax(220px,2fr) minmax(130px,1fr) 90px 110px 90px 90px 100px"
    nz_search = "Viloyat nomi yoki kodi…"
    nz_empty = ("Viloyat yo'q", "")
    nz_sorts = (("Toshkent birinchi", ""), ("Ko'p manzil", "-7"), ("Ko'p shahar", "-6"))
    nz_css = GEO_CSS
    hero_icon, hero_tone, hero_noun = "fa-map", "#f59e0b", "viloyat"

    def get_fieldsets(self, request, obj=None):
        sets = [("Viloyat", {"fields": ("country", "code", "status")})]
        if obj is not None:
            sets.append(("Shaharlar va tumanlar", {"classes": ("nzi-panel",), "fields": ("cities_panel",)}))
        return sets

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("country").prefetch_related("translations", "country__translations").annotate(
            n_cities=Count("cities", filter=Q(cities__is_deleted=False), distinct=True),
            n_districts=Count("districts", filter=Q(districts__is_deleted=False), distinct=True),
            n_addresses=Count("addresses", filter=Q(addresses__is_deleted=False), distinct=True),
            capital_first=Case(When(code="TGCITYR", then=Value(0)), When(code="UZ-TO", then=Value(1)), When(code="UZ-QR", then=Value(3)), default=Value(2), output_field=IntegerField()),
            uz_sort=_uz_name_sq(orm.RegionTranslation, "region"),
        ).order_by("capital_first", "uz_sort")

    def nz_stats(self, request):
        cities = orm.City.objects.count()
        with_coords = orm.City.objects.exclude(center_latitude=None).count()
        return [
            ui.stat_card("Viloyatlar", orm.Region.objects.count(), "#f59e0b", "fa-map", "12 viloyat + Toshkent shahri + QR"),
            ui.stat_card("Shaharlar", cities, "#0d9488", "fa-city", f"{round(with_coords * 100 / cities) if cities else 0}% xaritada", reverse("admin:geo_city_changelist")),
            ui.stat_card("Tumanlar", orm.District.objects.count(), "#9333ea", "fa-draw-polygon", "GPS bo'yicha avtomatik aniqlanadi", reverse("admin:geo_district_changelist")),
            ui.stat_card("Manzillar", orm.Address.objects.count(), "#4f46e5", "fa-house", "mijozlar manzillari", reverse("admin:geo_address_changelist")),
        ]

    def nz_tabs(self, request):
        return self._status_tabs(request, orm.Region.objects.all())

    def nz_hero_actions(self, request):
        return [{"label": "Manzillar xaritasi", "url": reverse("admin:nz_geo_map"), "icon": "fa-map-location-dot"},
                {"label": "Yangi viloyat", "url": reverse("admin:geo_region_add"), "icon": "fa-plus", "primary": True}]

    def nz_row(self, r):
        country = format_html('<span class="nzg-place">{}<span><b>{}</b></span></span>', flag(r.country.code, r.country.icon, 22), uz_name(r.country))
        cities = format_html('<a href="{}?region__id__exact={}">{}</a>', reverse("admin:geo_city_changelist"), r.pk, num(r.n_cities))
        districts = format_html('<a href="{}?region__id__exact={}">{}</a>', reverse("admin:geo_district_changelist"), r.pk, num(r.n_districts))
        return [place(r, "fa-map", "#f59e0b", extra=f" · {STATUS_LABELS['inactive']}" if r.status != "active" else ""), country, code_cell(r.code), langs(r), districts, cities, num(r.n_addresses)]

    @admin.display(description="")
    def cities_panel(self, obj):
        cities = list(obj.cities.prefetch_related("translations").order_by("code"))
        districts = list(obj.districts.prefetch_related("translations").order_by("code"))
        city_chips = "".join(str(format_html('<a class="nzi-chip" style="--t:#0d9488" href="{}">{}{}</a>', reverse("admin:geo_city_change", args=[c.pk]), uz_name(c),
                                             "" if c.center_latitude is not None else " · koordinatasiz")) for c in cities)
        district_chips = "".join(str(format_html('<a class="nzi-chip" style="--t:#9333ea" href="{}">{}</a>', reverse("admin:geo_district_change", args=[d.pk]), uz_name(d))) for d in districts)
        return format_html(
            '<div class="nzi-panel-body"><p><b>Shaharlar ({}):</b></p><div class="nzp-chips">{}</div><p style="margin-top:12px"><b>Tumanlar ({}):</b></p><div class="nzp-chips">{}</div>'
            '<p style="margin-top:12px"><a href="{}?region={}"><i class="fas fa-map-location-dot" aria-hidden="true"></i> Shu viloyat manzillarini xaritada ko\'rish</a></p></div>',
            len(cities), mark_safe(city_chips) or ui.muted("shahar yo'q"), len(districts), mark_safe(district_chips) or ui.muted("tuman kiritilmagan"), reverse("admin:nz_geo_map"), obj.pk)

    def form_hero(self, request, obj):
        if obj is None:
            return {"subtitle": "Davlatni tanlang, kod yozing (masalan UZ-SA) va uch tilda nomini kiriting"}
        n = names(obj)
        return {
            "title": uz_name(obj), "subtitle": " · ".join(v for v in (n.get("ru"), n.get("en")) if v),
            "chips": [status_pill(obj.status), code_cell(obj.code), format_html("{} {}", flag(obj.country.code, obj.country.icon, 20), uz_name(obj.country))],
            "stats": [hero_stat("Shaharlar", obj.cities.count(), "#0d9488", "yetkazish uchun", "fa-city"),
                      hero_stat("Tumanlar", obj.districts.count(), "#9333ea", "kiritilgan", "fa-draw-polygon"),
                      hero_stat("Manzillar", obj.addresses.count(), "#4f46e5", "mijozlarniki", "fa-house")],
            "links": [{"label": "Xaritada", "url": reverse("admin:nz_geo_map") + f"?region={obj.pk}", "icon": "fa-map-location-dot"}],
        }

    @admin.action(description="Tanlanganlarni o'chirish (ishlatilmayotgan bo'lsa)")
    def delete_via_service(self, request, queryset):
        self._service_delete(request, queryset, DeleteRegion(DjangoRegionRepository(), _admin_ctx(request)), "viloyat")


# ---------------------------------------------------------------- Tumanlar


@admin.register(orm.District)
class DistrictAdmin(_StatusActions, GeoMapMedia, PremiumListMixin, PremiumFormMixin, admin.ModelAdmin):
    list_filter = (("status", _titled(admin.ChoicesFieldListFilter, "Holat")), ("region", _titled(admin.RelatedFieldListFilter, "Viloyat")))
    search_fields = ("code", "translations__name")
    inlines = [DistrictTranslationInline]
    fieldsets = (("Tuman", {"fields": ("region", "code", "status")}),)
    actions = ["make_active", "make_inactive"]
    list_per_page = 40

    nz_icon, nz_tone, nz_title = "fa-draw-polygon", "#9333ea", "Tumanlar"
    nz_subtitle = "Mijoz xaritada nuqta qo'yganda tuman nomi avtomatik aniqlanadi (OpenStreetMap bo'yicha) — nomlar shu ro'yxat bilan solishtiriladi."
    nz_columns = (("Tuman", ""), ("Viloyat", ""), ("Kod", ""), ("Tillar", ""), ("Shaharlar", "r"), ("Manzillar", "r"))
    nz_grid = "minmax(220px,2fr) minmax(150px,1.2fr) 90px 110px 90px 100px"
    nz_search = "Tuman nomi yoki kodi…"
    nz_empty = ("Tuman yo'q", "Viloyat ichidagi tumanlarni qo'shing — mijoz manzilida va kuryer uchun ko'rinadi.")
    nz_sorts = (("Viloyat bo'yicha", ""), ("Ko'p manzil", "-6"))
    nz_css = GEO_CSS
    hero_icon, hero_tone, hero_noun = "fa-draw-polygon", "#9333ea", "tuman"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("region").prefetch_related("translations", "region__translations").annotate(
            n_cities=Count("cities", filter=Q(cities__is_deleted=False), distinct=True),
            n_addresses=Count("addresses", filter=Q(addresses__is_deleted=False), distinct=True),
            region_sort=Subquery(orm.RegionTranslation.objects.filter(region=OuterRef("region"), locale_code="uz").values("name")[:1]),
            uz_sort=_uz_name_sq(orm.DistrictTranslation, "district"),
        ).order_by("region_sort", "uz_sort")

    def nz_stats(self, request):
        regions = orm.Region.objects.annotate(n=Count("districts")).filter(n__gt=0).count()
        used = orm.District.objects.filter(addresses__isnull=False).distinct().count()
        return [
            ui.stat_card("Tumanlar", orm.District.objects.count(), "#9333ea", "fa-draw-polygon", f"{regions} ta viloyatda"),
            ui.stat_card("Manzillarda", used, "#4f46e5", "fa-house", "mijoz manzili biriktirilgan"),
            ui.stat_card("3 tilda", orm.District.objects.annotate(n=Count("translations")).filter(n__gte=3).count(), "#16a34a", "fa-language", "uz · ru · en to'liq"),
            ui.stat_card("Viloyatlar", orm.Region.objects.count(), "#f59e0b", "fa-map", f"{orm.Region.objects.count() - regions} tasida tuman yo'q", reverse("admin:geo_region_changelist")),
        ]

    def nz_tabs(self, request):
        return self._status_tabs(request, orm.District.objects.all())

    def nz_hero_actions(self, request):
        return [{"label": "Yangi tuman", "url": reverse("admin:geo_district_add"), "icon": "fa-plus", "primary": True}]

    def nz_row(self, d):
        return [place(d, "fa-draw-polygon", "#9333ea"), uz_name(d.region), code_cell(d.code), langs(d), num(d.n_cities), num(d.n_addresses)]

    def form_hero(self, request, obj):
        if obj is None:
            return {"subtitle": "Viloyatni tanlang va tuman nomini uch tilda yozing — «Chilonzor tumani», «Чиланзарский район», «Chilanzar District»"}
        n = names(obj)
        return {"title": uz_name(obj), "subtitle": " · ".join(v for v in (n.get("ru"), n.get("en")) if v), "chips": [status_pill(obj.status), code_cell(obj.code), ui.chip(uz_name(obj.region), "#f59e0b", "fa-map")],
                "stats": [hero_stat("Manzillar", obj.addresses.count(), "#4f46e5", "shu tumanda", "fa-house"), hero_stat("Shaharlar", obj.cities.count(), "#0d9488", "biriktirilgan", "fa-city")]}


# ---------------------------------------------------------------- Shaharlar


class CityForm(forms.ModelForm):
    class Meta:
        model = orm.City
        fields = ("region", "district", "code", "status", "timezone", "center_latitude", "center_longitude")
        labels = {"center_latitude": "Kenglik (lat)", "center_longitude": "Uzunlik (lng)", "district": "Tuman", "timezone": "Vaqt mintaqasi"}
        help_texts = {"center_latitude": "Shahar markazi. Xaritada bosing, qidiring yoki Yandex havolasini joylang — maydonlar o'zi to'ladi.",
                      "timezone": "Odatda Asia/Tashkent; bo'sh qolsa davlatniki olinadi."}


@admin.register(orm.City)
class CityAdmin(_StatusActions, GeoMapMedia, PremiumListMixin, PremiumFormMixin, admin.ModelAdmin):
    form = CityForm
    list_filter = (("status", _titled(admin.ChoicesFieldListFilter, "Holat")), ("region", _titled(admin.RelatedFieldListFilter, "Viloyat")))
    search_fields = ("code", "translations__name")
    inlines = [CityTranslationInline]
    readonly_fields = ("center_map",)
    actions = ["make_active", "make_inactive", "delete_via_service"]
    list_per_page = 50

    nz_icon, nz_tone, nz_title = "fa-city", "#0d9488", "Shaharlar"
    nz_subtitle = "Manzil formasida viloyatdan keyin tanlanadi. Markaz koordinatasi «joylashuvimni aniqlash»da eng yaqin shaharni topish uchun kerak."
    nz_columns = (("Shahar", ""), ("Viloyat", ""), ("Markaz", ""), ("Xaritada ochish", ""), ("Manzillar", "r"))
    nz_grid = "minmax(200px,1.6fr) minmax(150px,1.1fr) 150px minmax(250px,1.6fr) 100px"
    nz_search = "Shahar nomi yoki kodi…"
    nz_empty = ("Shahar yo'q", "")
    nz_sorts = (("Viloyat bo'yicha", ""), ("Ko'p manzil", "-5"))
    nz_css = GEO_CSS
    hero_icon, hero_tone, hero_noun = "fa-city", "#0d9488", "shahar"

    def get_fieldsets(self, request, obj=None):
        return (("Shahar", {"fields": ("region", "district", "code", "status", "timezone")}),
                ("Markaz koordinatasi", {"fields": ("center_map", "center_latitude", "center_longitude")}))

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("region", "district").prefetch_related("translations", "region__translations", "district__translations").annotate(
            n_addresses=Count("addresses", filter=Q(addresses__is_deleted=False), distinct=True),
            region_sort=Subquery(orm.RegionTranslation.objects.filter(region=OuterRef("region"), locale_code="uz").values("name")[:1]),
            uz_sort=_uz_name_sq(orm.CityTranslation, "city"),
        ).order_by("region_sort", "uz_sort")

    def nz_stats(self, request):
        total = orm.City.objects.count()
        coords = orm.City.objects.exclude(center_latitude=None).count()
        return [
            ui.stat_card("Shaharlar", total, "#0d9488", "fa-city", f"{orm.City.objects.filter(status='active').count()} faol", "?status__exact=active"),
            ui.stat_card("Xaritada", f"{round(coords * 100 / total) if total else 0}%", "#16a34a" if coords == total else "#d97706", "fa-location-dot", f"{total - coords} tasida markaz yo'q"),
            ui.stat_card("3 tilda", orm.City.objects.annotate(n=Count("translations")).filter(n__gte=3).count(), "#8b5cf6", "fa-language", "uz · ru · en to'liq"),
            ui.stat_card("Manzillar", orm.Address.objects.count(), "#4f46e5", "fa-house", "mijozlar manzillari", reverse("admin:geo_address_changelist")),
        ]

    def nz_tabs(self, request):
        return self._status_tabs(request, orm.City.objects.all())

    def nz_hero_actions(self, request):
        return [{"label": "Manzillar xaritasi", "url": reverse("admin:nz_geo_map"), "icon": "fa-map-location-dot"},
                {"label": "Yangi shahar", "url": reverse("admin:geo_city_add"), "icon": "fa-plus", "primary": True}]

    def nz_row(self, c):
        region = format_html('<span class="nzg-addr"><b>{}</b><small>{}</small></span>', uz_name(c.region), uz_name(c.district, "") if c.district_id else "")
        coord = format_html('<span class="nzg-coord">{}, {}</span>', f"{c.center_latitude:.4f}", f"{c.center_longitude:.4f}") if c.center_latitude is not None else ui.chip("markaz yo'q", "#d97706", "fa-triangle-exclamation")
        return [place(c, "fa-city", "#0d9488"), region, coord, map_links(c.center_latitude, c.center_longitude, uz_name(c)) or ui.muted(), num(c.n_addresses)]

    @admin.display(description="Xarita")
    def center_map(self, obj):
        return point_picker("id_center_latitude", "id_center_longitude")

    def form_hero(self, request, obj):
        if obj is None:
            return {"subtitle": "Viloyat, kod va nomlar — keyin xaritada shahar markazini belgilang"}
        n = names(obj)
        return {
            "title": uz_name(obj), "subtitle": " · ".join(v for v in (n.get("ru"), n.get("en")) if v),
            "chips": [status_pill(obj.status), code_cell(obj.code), ui.chip(uz_name(obj.region), "#f59e0b", "fa-map")] + ([ui.chip(uz_name(obj.district), "#9333ea", "fa-draw-polygon")] if obj.district_id else []),
            "stats": [hero_stat("Manzillar", obj.addresses.count(), "#4f46e5", "shu shaharda", "fa-house"),
                      hero_stat("Markaz", f"{obj.center_latitude:.4f}, {obj.center_longitude:.4f}" if obj.center_latitude is not None else "—", "#0d9488", "koordinata", "fa-location-dot")],
            "links": [{"label": "Xaritada", "url": reverse("admin:nz_geo_map") + f"?region={obj.region_id}", "icon": "fa-map-location-dot"}],
        }

    @admin.action(description="Tanlanganlarni o'chirish (ishlatilmayotgan bo'lsa)")
    def delete_via_service(self, request, queryset):
        self._service_delete(request, queryset, DeleteCity(DjangoCityRepository(), _admin_ctx(request)), "shahar")


# ---------------------------------------------------------------- Manzillar

META_FIELDS = (("building_name", "Bino / majmua", 128), ("entrance", "Podyezd", 16), ("floor", "Qavat", 16), ("unit", "Xonadon", 16),
               ("entrance_code", "Domofon kodi", 32), ("delivery_instructions", "Mo'ljal va izoh kuryerga", 500))


class AddressAdminForm(forms.ModelForm):
    """Owner as a customer dropdown (owner_type/owner_id are cross-app ids, no FK) + the delivery details (AddressMetadata 1:1)."""

    owner = forms.ModelChoiceField(queryset=None, label="Mijoz")
    building_name = forms.CharField(label="Bino / majmua", required=False, max_length=128, help_text="Masalan: «Tashkent City, Boulevard 5-blok»")
    entrance = forms.CharField(label="Podyezd", required=False, max_length=16)
    floor = forms.CharField(label="Qavat", required=False, max_length=16)
    unit = forms.CharField(label="Xonadon", required=False, max_length=16)
    entrance_code = forms.CharField(label="Domofon kodi", required=False, max_length=32)
    delivery_instructions = forms.CharField(label="Mo'ljal va izoh kuryerga", required=False, max_length=500, widget=forms.Textarea(attrs={"rows": 2}),
                                            help_text="Masalan: «Makro supermarketi ro'parasi, ko'k darvoza»")

    class Meta:
        model = orm.Address
        exclude = ["owner_type", "owner_id", "normalized_signature", "formatted_lines"]
        labels = {"address_type": "Turi", "is_default": "Asosiy manzil", "line1": "Ko'cha va uy", "line2": "Qo'shimcha", "postal_code": "Pochta indeksi",
                  "recipient_name": "Qabul qiluvchi", "recipient_phone": "Telefon", "recipient_telegram_username": "Telegram", "coordinate_latitude": "Kenglik (lat)",
                  "coordinate_longitude": "Uzunlik (lng)", "coordinate_accuracy_meters": "Aniqlik (m)", "coordinate_source": "Qanday aniqlangan", "formatted_single_line": "To'liq manzil (avtomatik)"}

    def __init__(self, *args, **kwargs):
        from apps.identity.infrastructure.models import User

        super().__init__(*args, **kwargs)
        self.fields["owner"].queryset = User.objects.all()
        self.fields["owner"].label_from_instance = lambda u: f"{u.full_name or 'Ismsiz'} · {u.phone_number}"
        if self.instance and self.instance.pk and self.instance.owner_type == "user":
            self.fields["owner"].initial = self.instance.owner_id
        meta = None
        if self.instance and self.instance.pk:
            try:
                meta = self.instance.metadata
            except orm.AddressMetadata.DoesNotExist:
                meta = None
        for name, *_ in META_FIELDS:
            self.fields[name].initial = getattr(meta, name, "") if meta else ""
        if "coordinate_source" in self.fields:
            self.fields["coordinate_source"] = forms.ChoiceField(label="Qanday aniqlangan", required=False, choices=[("", "—")] + [(k, v[0]) for k, v in SOURCES.items()])

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.owner_type = "user"
        obj.owner_id = self.cleaned_data["owner"].pk
        if obj.city_id and not obj.region_id:
            obj.region_id = obj.city.region_id
        if not obj.normalized_signature:
            from apps.geo.domain.services import AddressNormalizer

            obj.normalized_signature = AddressNormalizer.normalized_signature(obj.line1, obj.line2, str(obj.city_id), obj.postal_code)
        if commit:
            obj.save()
            self.save_metadata(obj)
        return obj

    def save_metadata(self, obj):
        orm.AddressMetadata.objects.update_or_create(address=obj, defaults={name: (self.cleaned_data.get(name) or "").strip() or None for name, *_ in META_FIELDS})


class SourceFilter(admin.SimpleListFilter):
    title = "Koordinata"
    parameter_name = "coord"

    def lookups(self, request, model_admin):
        return [("none", "Koordinatasiz")] + [(k, v[0]) for k, v in SOURCES.items()]

    def queryset(self, request, queryset):
        if self.value() == "none":
            return queryset.filter(coordinate_latitude__isnull=True)
        if self.value():
            return queryset.filter(coordinate_source=self.value(), coordinate_latitude__isnull=False)
        return queryset


@admin.register(orm.Address)
class AddressAdmin(ExcelExportMixin, GeoMapMedia, PremiumListMixin, PremiumFormMixin, admin.ModelAdmin):
    excel_title = "Manzillar"
    excel_select_related = ("region", "district", "city")
    excel_columns = [
        Col("Qabul qiluvchi", "recipient_name", 22), Col("Telefon", "recipient_phone", 15), Col("Viloyat", lambda a: str(a.region) if a.region else "", 16),
        Col("Tuman", lambda a: str(a.district) if a.district else "", 16), Col("Manzil", "formatted_single_line", 44), Col("Kenglik", "coordinate_latitude", 11),
        Col("Uzunlik", "coordinate_longitude", 11), Col("Asosiy", "is_default", 8), Col("Yaratilgan", "created_at", 17),
    ]

    form = AddressAdminForm
    list_filter = (SourceFilter, ("address_type", _titled(admin.ChoicesFieldListFilter, "Turi")), ("region", _titled(admin.RelatedFieldListFilter, "Viloyat")),
                   ("is_default", _titled(admin.BooleanFieldListFilter, "Asosiy")))
    search_fields = ("line1", "line2", "postal_code", "recipient_name", "recipient_phone", "formatted_single_line")
    readonly_fields = ("coordinate_map", "address_map", "details_panel")
    list_per_page = 30
    actions = ["fill_from_point"]

    nz_icon, nz_tone, nz_title = "fa-house", "#4f46e5", "Manzillar"
    nz_subtitle = "Mijozlarning yetkazib berish manzillari: aniq nuqta, podyezd, qavat, domofon va mo'ljal — kuryer shuni ko'radi."
    nz_columns = (("Manzil", ""), ("Mijoz", ""), ("Hudud", ""), ("Nuqta", ""), ("Xaritada ochish", ""), ("Turi", "r"))
    nz_grid = "minmax(240px,2fr) minmax(190px,1.3fr) minmax(140px,1fr) minmax(130px,.9fr) minmax(230px,1.5fr) 110px"
    nz_search = "Ko'cha, mijoz ismi yoki telefon…"
    nz_empty = ("Manzil yo'q", "Mijozlar saytda yoki Telegram botda manzil qo'shganda shu yerda ko'rinadi.")
    nz_sorts = (("Yangilari", ""), ("Eskilari", "created_at"))
    nz_css = GEO_CSS
    hero_icon, hero_tone, hero_noun = "fa-house", "#4f46e5", "manzil"
    ordering = ("-created_at",)

    def get_fieldsets(self, request, obj=None):
        sets = [
            ("Mijoz", {"fields": ("owner", "address_type", "is_default")}),
            ("Manzil", {"fields": ("country", "region", "district", "city", "line1", "line2", "postal_code")}),
            ("Kuryer uchun", {"fields": ("building_name", "entrance", "floor", "unit", "entrance_code", "delivery_instructions")}),
            ("Qabul qiluvchi", {"fields": ("recipient_name", "recipient_phone", "recipient_telegram_username")}),
            ("Xaritadagi nuqta", {"fields": ("coordinate_map", "coordinate_latitude", "coordinate_longitude", "coordinate_accuracy_meters", "coordinate_source")}),
        ]
        if obj is not None:
            sets.insert(0, ("Xaritada", {"classes": ("nzi-panel",), "fields": ("address_map",)}))
            sets.insert(1, ("Kuryer ko'radigan ma'lumot", {"classes": ("nzi-panel",), "fields": ("details_panel",)}))
        return sets

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name in ("country", "region", "district", "city", "neighborhood") and field is not None:
            field.queryset = field.queryset.prefetch_related("translations")
            field.label_from_instance = lambda o: uz_name(o)
        return field

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("country", "region", "district", "city", "metadata").prefetch_related(
            "region__translations", "district__translations", "city__translations")

    def get_search_results(self, request, queryset, search_term):
        """Also by the customer's name / phone -- owner_id has no FK to search across."""
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        if search_term:
            from apps.identity.infrastructure.models import User

            ids = list(User.objects.filter(Q(full_name__icontains=search_term) | Q(phone_number__icontains=search_term)).values_list("id", flat=True)[:200])
            if ids:
                queryset = (queryset | self.model.objects.filter(owner_type="user", owner_id__in=ids)).distinct()
        return queryset, use_distinct

    def nz_prepare(self, request, objs):
        from django.db.models import Prefetch

        from apps.identity.infrastructure.models import User, UserAvatarAsset

        ids = [o.owner_id for o in objs if o.owner_type == "user"]
        self._users = {u.id: u for u in User.objects.filter(id__in=ids).prefetch_related(Prefetch("avatar_assets", queryset=UserAvatarAsset.objects.order_by("-created_at")))}

    def nz_stats(self, request):
        qs = orm.Address.objects.all()
        total = qs.count()
        coords = qs.exclude(coordinate_latitude=None).count()
        precise = qs.filter(coordinate_accuracy_meters__lte=30).count()
        details = orm.AddressMetadata.objects.filter(address__is_deleted=False).exclude(Q(entrance__isnull=True) & Q(floor__isnull=True) & Q(unit__isnull=True) & Q(delivery_instructions__isnull=True)).count()
        return [
            ui.stat_card("Manzillar", total, "#4f46e5", "fa-house", f"{qs.filter(is_default=True).count()} tasi asosiy"),
            ui.stat_card("Xaritada", f"{round(coords * 100 / total) if total else 0}%", "#16a34a", "fa-location-dot", f"{total - coords} tasi nuqtasiz", "?coord=none"),
            ui.stat_card("Aniq GPS (±30 m)", precise, "#0d9488", "fa-location-crosshairs", "kuryer to'g'ri eshikka boradi", "?coord=gps"),
            ui.stat_card("Podyezd / mo'ljal", details, "#f59e0b", "fa-door-open", "kuryer uchun tafsilot bor"),
        ]

    def nz_hero_actions(self, request):
        return [{"label": "Manzillar xaritasi", "url": reverse("admin:nz_geo_map"), "icon": "fa-map-location-dot", "primary": True}]

    def nz_row(self, a):
        from apps.geo.application.services.address import delivery_details_line
        from apps.geo.domain.entities import AddressMetadata

        try:
            meta = a.metadata
        except orm.AddressMetadata.DoesNotExist:
            meta = None
        details = delivery_details_line(AddressMetadata(**{f: getattr(meta, f, None) for f, *_ in META_FIELDS})) if meta else ""
        addr = format_html('<span class="nzg-addr"><b>{}</b><small>{}</small>{}</span>', a.line1, a.line2 or "", format_html("<em>{}</em>", details) if details else "")
        region = format_html('<span class="nzg-addr"><b>{}</b><small>{}</small></span>', uz_name(a.city), " · ".join(x for x in (uz_name(a.district, "") if a.district_id else "", uz_name(a.region, "") if a.region_id else "") if x))
        if a.coordinate_latitude is not None:
            label, color, icon = SOURCES.get(a.coordinate_source or "manual", SOURCES["manual"])
            point = format_html('<span class="nzg-acc">{}{}</span>', ui.chip(label, color, icon), accuracy_chip(a.coordinate_accuracy_meters) or format_html('<small>{}, {}</small>', f"{a.coordinate_latitude:.4f}", f"{a.coordinate_longitude:.4f}"))
        else:
            point = ui.chip("nuqta yo'q", "#d97706", "fa-triangle-exclamation")
        t_label, t_icon, t_color = ADDRESS_TYPES.get(a.address_type, (a.address_type, "fa-location-dot", "#64748b"))
        kind = format_html("{}{}", ui.chip(t_label, t_color, t_icon), mark_safe('<br><span class="nzi-pill" style="--t:#16a34a">asosiy</span>') if a.is_default else "")
        return [addr, ui.user_cell(self._users.get(a.owner_id)), region, point, map_links(a.coordinate_latitude, a.coordinate_longitude, a.line1) or ui.muted(), kind]

    @admin.display(description="Xarita")
    def coordinate_map(self, obj):
        return point_picker("id_coordinate_latitude", "id_coordinate_longitude", "id_coordinate_source", "id_coordinate_accuracy_meters")

    @admin.display(description="")
    def address_map(self, obj):
        if obj is None or obj.coordinate_latitude is None:
            return mark_safe('<p class="nzi-muted"><i class="fas fa-location-dot" aria-hidden="true"></i> Koordinata yo\'q — mijoz xaritada nuqta belgilamagan. Pastda belgilashingiz mumkin.</p>')
        return format_html('{}<div style="margin-top:10px">{}</div>', point_view(obj.coordinate_latitude, obj.coordinate_longitude, obj.line1, obj.coordinate_accuracy_meters),
                           map_links(obj.coordinate_latitude, obj.coordinate_longitude, obj.line1))

    @admin.display(description="")
    def details_panel(self, obj):
        try:
            meta = obj.metadata
        except orm.AddressMetadata.DoesNotExist:
            meta = None
        cells = [(label, getattr(meta, name, None) if meta else None) for name, label, _ in META_FIELDS]
        body = "".join(str(format_html("<div><small>{}</small><b>{}</b></div>", label, value or "—")) for label, value in cells)
        return format_html('<div class="nzgeo-details">{}</div>', mark_safe(body))

    def form_hero(self, request, obj):
        if obj is None:
            return {"subtitle": "Mijozni, shaharni va ko'chani tanlang — keyin xaritada aniq nuqtani belgilang"}
        from apps.identity.infrastructure.models import User

        owner = User.objects.filter(id=obj.owner_id).first()
        t_label, t_icon, t_color = ADDRESS_TYPES.get(obj.address_type, (obj.address_type, "fa-location-dot", "#64748b"))
        chips = [ui.chip(t_label, t_color, t_icon), ui.chip(uz_name(obj.city), "#0d9488", "fa-city")]
        if obj.coordinate_latitude is not None:
            label, color, icon = SOURCES.get(obj.coordinate_source or "manual", SOURCES["manual"])
            chips.append(ui.chip(label, color, icon))
            if obj.coordinate_accuracy_meters is not None:
                chips.append(accuracy_chip(obj.coordinate_accuracy_meters))
        if obj.is_default:
            chips.append(ui.chip("Asosiy manzil", "#16a34a", "fa-star"))
        links = [{"label": "Xaritada", "url": reverse("admin:nz_geo_map") + f"?focus={obj.pk}", "icon": "fa-map-location-dot"}]
        if owner:
            links.insert(0, {"label": owner.full_name or owner.phone_number, "url": reverse("admin:identity_user_change", args=[owner.pk]), "icon": "fa-user"})
        return {"title": obj.line1, "subtitle": obj.formatted_single_line or "", "chips": chips, "links": links}

    @admin.action(description="Ko'cha, tuman va viloyatni nuqta bo'yicha aniqlash")
    def fill_from_point(self, request, queryset):
        """Old Telegram addresses read "Lat: 41.29, Lon: 69.29" -- the street (OpenStreetMap) replaces only such raw lines; region / district are filled when empty."""
        import re

        from apps.geo.infrastructure.gateways import geocoder

        raw = re.compile(r"^\s*(lat[:\s]|📍|-?\d{1,2}\.\d+\s*,)", re.I)
        done = skipped = 0
        for a in queryset.exclude(coordinate_latitude=None)[:50]:  # OpenStreetMap allows ~1 request a second
            found = geocoder.locate(a.coordinate_latitude, a.coordinate_longitude, "uz")
            changed = []
            if found.get("street") and raw.match(a.line1 or ""):
                a.line1 = found["street"][:255]
                a.formatted_single_line = (found.get("label") or "")[:1024] or a.formatted_single_line
                changed += ["line1", "formatted_single_line"]
            if found.get("in_service_area") and found.get("region") and a.region_id is None and str(a.city.region_id) == found["region"]["id"]:
                a.region_id = a.city.region_id
                changed.append("region")
            if found.get("district") and a.district_id is None and str(a.region_id or a.city.region_id) == (found.get("region") or {}).get("id"):
                a.district_id = found["district"]["id"]
                changed.append("district")
            if changed:
                a.save(update_fields=changed)
                done += 1
            else:
                skipped += 1
        self.message_user(request, f"{done} ta manzil yangilandi" + (f", {skipped} tasida o'zgartirish kerak bo'lmadi yoki ko'cha topilmadi." if skipped else "."))

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.save_metadata(form.instance)
