"""Dashboard admin for the Store ("Do'kon") module."""
from __future__ import annotations

from django import forms
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from apps.platform.infrastructure.excel_export import Col, ExcelExportMixin
from apps.stores.infrastructure import models as orm


def _titled(title):
    from apps.products.infrastructure.catalog_admin_ui import titled

    return titled(title)


def timezone_local(dt) -> str:
    from zoneinfo import ZoneInfo

    return dt.astimezone(ZoneInfo("Asia/Tashkent")).strftime("%d.%m %H:%M") if dt else ""


_WEEKDAYS = [
    ("mon", _("Dushanba")), ("tue", _("Seshanba")), ("wed", _("Chorshanba")), ("thu", _("Payshanba")),
    ("fri", _("Juma")), ("sat", _("Shanba")), ("sun", _("Yakshanba")),
]


class StoreMediaAdminForm(forms.ModelForm):
    media_upload = forms.FileField(required=False, label=_("Upload image or video"), help_text=_("JPEG/PNG/WebP or MP4/WebM. Runs through the real media pipeline."))

    class Meta:
        model = orm.StoreMedia
        fields = ["sort_order"]


class StoreMediaInline(admin.TabularInline):
    """Real, product-required capability: multiple images and/or videos per store, each row a single upload -- runs through the same, existing media pipeline products/banners already use. is_video/duration_seconds are auto-detected from the processed file, never asked of the admin."""

    model = orm.StoreMedia
    form = StoreMediaAdminForm
    extra = 1
    fields = ("media_display", "media_upload", "sort_order")
    readonly_fields = ("media_display",)

    def media_display(self, obj: orm.StoreMedia) -> str:
        if not obj.pk or not obj.storage_path:
            return "—"
        if obj.is_video:
            return format_html('<video src="/media/{}" style="max-height:80px;" controls></video>', obj.storage_path)
        thumb = (obj.thumbnail_paths or {}).get("small") or obj.storage_path
        return format_html('<img src="/media/{}" style="max-height:80px;border-radius:6px;" />', thumb)

    media_display.short_description = ""

    def save_formset(self, request, form, formset, change):
        for sub_form in formset.forms:
            uploaded = sub_form.cleaned_data.get("media_upload") if sub_form.cleaned_data else None
            if not uploaded:
                continue
            instance = sub_form.instance
            from apps.products.infrastructure.composition import build_media_pipeline
            from core.media import MediaType, MediaUploadRequest

            is_video = uploaded.content_type.startswith("video/")
            media_type = MediaType.VIDEO if is_video else MediaType.IMAGE
            result = build_media_pipeline().process(MediaUploadRequest(filename=uploaded.name, content=uploaded.read(), mime_type=uploaded.content_type, media_type=media_type))
            if result.is_failure:
                raise forms.ValidationError(result.errors[0].message)
            processed = result.value
            instance.storage_path = processed.storage_path
            instance.thumbnail_paths = getattr(processed, "thumbnail_paths", {}) or {}
            instance.is_video = is_video
            instance.duration_seconds = getattr(processed, "duration_seconds", None)
        formset.save()


class StoreProductStockInline(admin.TabularInline):
    """Real, product-required boundary: a store owner NEVER creates a product here -- product_variant is a fixed dropdown over EXISTING variants only (autocomplete), and quantity is the only thing an owner meaningfully edits."""

    model = orm.StoreProductStock
    extra = 1
    autocomplete_fields = ["product_variant"]
    fields = ("product_variant", "quantity", "reserved_quantity", "updated_at")
    readonly_fields = ("reserved_quantity", "updated_at")
    can_delete = False
    verbose_name_plural = _("Stock (every change here is recorded in the stock ledger as an adjustment)")


STORE_COLOR_NAMES = {
    "#2D8CFF": "Moviy", "#22C55E": "Yashil", "#FF9800": "To'q sariq", "#E91E63": "Malina", "#7E35C1": "Binafsha",
    "#4338CA": "Indigo", "#FF8057": "Marjon", "#F45B5B": "Qizil", "#38BDF8": "Osmon", "#E879F9": "Orxideya",
    "#818CF8": "Lavanda", "#C9DC45": "Laym", "#607D8B": "Po'lat", "#14B8A6": "Firuza", "#F59E0B": "Qahrabo",
    "#A855F7": "Ametist", "#EF4444": "Olcha", "#10B981": "Zumrad", "#0EA5E9": "Dengiz", "#D946EF": "Fuksiya",
    "#84CC16": "Maysa", "#F97316": "Apelsin", "#6366F1": "Kobalt", "#EC4899": "Pushti", "#06B6D4": "Moviy-yashil",
    "#C9BEB3": "Qum", "#C5E1A5": "Yalpiz", "#8B5CF6": "Siren", "#FB7185": "Atirgul", "#65A30D": "Zaytun",
}


class StoreColorWidget(forms.TextInput):
    """Brand colour as a choice, not a hex code: named swatches (Uzbek names), colours taken by another store are locked
    and show which store owns them; "Boshqa rang" opens a free picker for anything outside the palette."""

    template_name = ""

    def render(self, name, value, attrs=None, renderer=None):
        from django.utils.html import escape
        from django.utils.safestring import mark_safe

        store_pk = getattr(self, "store_pk", None)
        owners = {c.upper(): n for c, n in orm.Store.objects.exclude(color="").exclude(pk=store_pk).values_list("color", "name")}
        value = (value or "").upper() or orm.next_store_color(exclude_pk=store_pk).upper()
        input_id = (attrs or {}).get("id", f"id_{name}")
        in_palette = value in STORE_COLOR_NAMES
        chips = []
        for hex_, label in STORE_COLOR_NAMES.items():
            owner = owners.get(hex_)
            checked = hex_ == value
            chips.append(
                f'<label class="nzc-chip{" is-used" if owner else ""}" style="--c:{hex_}" title="{escape(label)}{escape(" — " + owner + " ishlatmoqda") if owner else ""}">'
                f'<input type="radio" name="{name}__pick" value="{hex_}"{" checked" if checked else ""}{" disabled" if owner else ""}>'
                f'<span class="nzc-dot"></span><span class="nzc-name">{escape(label)}</span>'
                f'{f"<small>{escape(owner)}</small>" if owner else ""}</label>'
            )
        custom_checked = "" if in_palette else " checked"
        return mark_safe(
            f'<div class="nzc" data-for="{input_id}">'
            f'<input type="hidden" name="{name}" id="{input_id}" value="{value}">'
            f'<div class="nzc-preview"><span class="nzc-big" style="background:{value}"></span><span><b data-nzc-name>{escape(STORE_COLOR_NAMES.get(value, "Maxsus rang"))}</b>'
            f'<small>Grafiklar, hisobotlar va filial kartasida shu rang ishlatiladi</small></span></div>'
            f'<div class="nzc-grid">{"".join(chips)}'
            f'<label class="nzc-chip nzc-custom" style="--c:{value if not in_palette else "#94A3B8"}" title="Palitradan tashqari rang">'
            f'<input type="radio" name="{name}__pick" value="custom"{custom_checked}><span class="nzc-dot nzc-rainbow"></span>'
            f'<span class="nzc-name">Boshqa rang</span><input type="color" class="nzc-free" value="{value}" aria-label="Boshqa rang tanlash"></label>'
            f'</div></div>'
            "<style>"
            ".nzc{display:flex;flex-direction:column;gap:12px;max-width:760px}"
            ".nzc-preview{display:flex;align-items:center;gap:12px;padding:10px 14px;border-radius:14px;border:1px solid var(--nz-border,#e2e8f0);"
            "background:color-mix(in srgb,var(--nz-surface,#fff) 70%,transparent);backdrop-filter:blur(10px)}"
            ".nzc-preview b{display:block;font-size:.95rem}.nzc-preview small{color:var(--nz-text-muted,#64748b);font-size:.75rem}"
            ".nzc-big{width:40px;height:40px;border-radius:12px;box-shadow:inset 0 1px 0 rgba(255,255,255,.4),0 6px 16px -6px rgba(0,0,0,.35);flex-shrink:0}"
            ".nzc-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(128px,1fr));gap:8px}"
            ".nzc-chip{position:relative;display:flex;align-items:center;gap:8px;padding:7px 10px;margin:0;border-radius:12px;cursor:pointer;font-size:.8rem;font-weight:600;"
            "border:1px solid var(--nz-border,#e2e8f0);background:color-mix(in srgb,var(--c) 7%,var(--nz-surface,#fff));color:var(--nz-text-primary,#0f172a);transition:all .15s}"
            ".nzc-chip:hover{border-color:var(--c);transform:translateY(-1px)}"
            ".nzc-chip input[type=radio]{position:absolute;opacity:0;pointer-events:none}"
            ".nzc-chip:has(input[type=radio]:checked){border-color:var(--c);background:color-mix(in srgb,var(--c) 16%,var(--nz-surface,#fff));box-shadow:0 0 0 2px color-mix(in srgb,var(--c) 45%,transparent)}"
            ".nzc-chip:has(input[type=radio]:checked) .nzc-dot::after{content:'\\2713';color:#fff;font-size:.7rem;font-weight:900;display:grid;place-items:center;height:100%}"
            ".nzc-chip:has(input[type=radio]:focus-visible){outline:2px solid var(--nz-focus-ring,#3b82f6);outline-offset:2px}"
            ".nzc-dot{width:22px;height:22px;border-radius:50%;background:var(--c);flex-shrink:0;box-shadow:inset 0 1px 0 rgba(255,255,255,.35)}"
            ".nzc-name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}"
            ".nzc-chip small{position:absolute;right:8px;bottom:2px;font-size:.6rem;font-weight:500;color:var(--nz-text-muted,#64748b);max-width:60%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}"
            ".nzc-chip.is-used{cursor:not-allowed;opacity:.5;padding-bottom:13px}.nzc-chip.is-used:hover{transform:none;border-color:var(--nz-border,#e2e8f0)}"
            ".nzc-chip.is-used .nzc-dot{background:repeating-linear-gradient(45deg,var(--c) 0 4px,transparent 4px 7px)}"
            ".nzc-rainbow{background:conic-gradient(#f43f5e,#f59e0b,#22c55e,#0ea5e9,#8b5cf6,#f43f5e)}"
            ".nzc-free{width:26px;height:22px;border:0;padding:0;margin-left:auto;background:none;cursor:pointer}"
            "</style>"
            "<script>(function(){var r=document.querySelector('.nzc[data-for=\"" + input_id + "\"]');if(!r)return;"
            "var h=document.getElementById('" + input_id + "'),big=r.querySelector('.nzc-big'),nm=r.querySelector('[data-nzc-name]'),free=r.querySelector('.nzc-free'),cust=r.querySelector('.nzc-custom');"
            "function set(v,label){h.value=v.toUpperCase();big.style.background=v;nm.textContent=label;}"
            "r.addEventListener('change',function(e){var t=e.target;if(t.type==='radio'){if(t.value==='custom'){set(free.value,'Maxsus rang');cust.style.setProperty('--c',free.value);}"
            "else set(t.value,t.closest('label').querySelector('.nzc-name').textContent);}});"
            "free.addEventListener('input',function(){cust.querySelector('input[type=radio]').checked=true;cust.style.setProperty('--c',free.value);set(free.value,'Maxsus rang');});"
            "})();</script>"
        )


class StoreAdminForm(forms.ModelForm):
    """Real, product-required UX: working_hours (a single JSON field) is edited as 7 separate, human day-by-day open/close/closed fields -- an owner never hand-writes JSON. Dynamically re-editable at any time: changing any single day's fields and saving immediately updates that day's entry, leaving every other day untouched."""

    logo_upload = forms.ImageField(required=False, label=_("Upload logo"), help_text=_("JPEG, PNG, or WebP. Runs through the real media pipeline."))
    cover_image_upload = forms.ImageField(required=False, label=_("Upload cover image"), help_text=_("JPEG, PNG, or WebP. Runs through the real media pipeline."))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "color" in self.fields:
            self.fields["color"].widget = StoreColorWidget()
            self.fields["color"].widget.store_pk = self.instance.pk if self.instance else None
            if not (self.instance and self.instance.pk and self.instance.color):
                self.initial.setdefault("color", orm.next_store_color())

    def clean_phone_numbers(self):
        """"90 123 45 67", "998901234567", "+998 (90) 123-45-67" -> "+998901234567"; anything else is rejected."""
        from apps.stores.infrastructure.store_admin_ui import PHONE_RE

        raw = self.cleaned_data.get("phone_numbers") or []
        if isinstance(raw, str):
            raw = [raw]
        out = []
        for p in raw:
            digits = "".join(ch for ch in str(p) if ch.isdigit())
            if len(digits) == 9:
                digits = "998" + digits
            phone = "+" + digits
            if not PHONE_RE.match(phone):
                raise forms.ValidationError(_("Telefon raqami noto'g'ri: %(p)s. Masalan: +998 90 123 45 67") % {"p": p})
            if phone not in out:
                out.append(phone)
        return out

    def clean_special_hours(self):
        rows = self.cleaned_data.get("special_hours") or []
        for r in rows:
            if not r.get("closed") and (not r.get("open") or not r.get("close") or r["open"] >= r["close"]):
                raise forms.ValidationError(_("%(d)s: ochilish va yopilish vaqtini to'g'ri kiriting (yoki «Dam olish» belgilang).") % {"d": r.get("date")})
        return sorted(rows, key=lambda r: r["date"])

    def clean(self):
        data = super().clean()
        for code, label in _WEEKDAYS:
            if data.get(f"hours_{code}_closed"):
                continue
            o, c = data.get(f"hours_{code}_open") or "", data.get(f"hours_{code}_close") or ""
            if bool(o) != bool(c) or (o and c and o >= c):
                self.add_error(f"hours_{code}_open", _("%(day)s: ochilish vaqti yopilishdan oldin bo'lsin.") % {"day": label})
        return data

    def clean_color(self):
        color = (self.cleaned_data.get("color") or "").upper()
        if color and orm.Store.objects.exclude(pk=self.instance.pk).filter(color__iexact=color).exists():
            raise forms.ValidationError(_("Another store already uses this colour — pick a different one so the charts stay readable."))
        return color

    class Meta:
        model = orm.Store
        fields = ["owner", "kind", "name", "slug", "color", "description", "status", "phone_numbers", "email", "telegram_username", "instagram_username", "address", "city", "district", "latitude", "longitude", "special_hours"]
        widgets = {
            "kind": forms.RadioSelect(attrs={"class": "nzf-cards"}),
            "status": forms.RadioSelect(attrs={"class": "nzf-pills"}),
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Filial haqida qisqacha: mo'ljal, parkovka, xizmatlar…"}),
            "name": forms.TextInput(attrs={"placeholder": "Masalan: NutriZone Chilonzor"}),
            "address": forms.TextInput(attrs={"placeholder": "Ko'cha, uy, mo'ljal"}),
            "district": forms.TextInput(attrs={"placeholder": "Masalan: Chilonzor tumani"}),
            "email": forms.EmailInput(attrs={"placeholder": "filial@example.uz"}),
            "telegram_username": forms.TextInput(attrs={"placeholder": "username (@ siz)"}),
            "instagram_username": forms.TextInput(attrs={"placeholder": "username (@ siz)"}),
            "latitude": forms.NumberInput(attrs={"step": "any", "readonly": False}),
            "longitude": forms.NumberInput(attrs={"step": "any"}),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        working_hours = {}
        for code, _label in _WEEKDAYS:
            working_hours[code] = {
                "open": self.cleaned_data.get(f"hours_{code}_open") or "",
                "close": self.cleaned_data.get(f"hours_{code}_close") or "",
                "closed": bool(self.cleaned_data.get(f"hours_{code}_closed")),
            }
        instance.working_hours = working_hours
        if commit:
            instance.save()
        return instance

    def save_media(self, instance) -> None:
        """Real, critical fix: called from StoreAdmin.save_model() -- Django admin's own save_model() always calls form.save(commit=False) and saves the instance itself afterward, so logic gated on `if commit` inside this form's own save() never ran. This is the correct place: it always fires, right after the real instance.save()."""
        self._save_logo(instance)
        self._save_cover_image(instance)

    def _save_logo(self, instance) -> None:
        uploaded = self.cleaned_data.get("logo_upload")
        if not uploaded:
            return
        processed = self._process_image(uploaded)
        instance.logo_storage_path = processed.storage_path
        instance.logo_thumbnail_paths = processed.thumbnail_paths
        instance.save(update_fields=["logo_storage_path", "logo_thumbnail_paths"])

    def _save_cover_image(self, instance) -> None:
        uploaded = self.cleaned_data.get("cover_image_upload")
        if not uploaded:
            return
        processed = self._process_image(uploaded)
        instance.cover_image_storage_path = processed.storage_path
        instance.cover_image_thumbnail_paths = processed.thumbnail_paths
        instance.save(update_fields=["cover_image_storage_path", "cover_image_thumbnail_paths"])

    @staticmethod
    def _process_image(uploaded):
        from apps.products.infrastructure.composition import build_media_pipeline
        from core.media import MediaType, MediaUploadRequest

        result = build_media_pipeline().process(MediaUploadRequest(filename=uploaded.name, content=uploaded.read(), mime_type=uploaded.content_type, media_type=MediaType.IMAGE))
        if result.is_failure:
            raise forms.ValidationError(result.errors[0].message)
        return result.value


# Real, critical fix: these 21 fields MUST be declared at class level
# (not added dynamically inside __init__) -- Django admin's own
# get_form() rebuilds the form via modelform_factory() using each
# fieldset entry as a "fields" list; any field the base ModelForm
# class doesn't already declare raises FieldError("Unknown field(s)")
# at that point, since modelform_factory has no visibility into
# fields an __init__ would only add per-instance, matching this
# module's own already-proven ProductVariantAdminForm.stock pattern.
for _code, _label in _WEEKDAYS:
    StoreAdminForm.base_fields[f"hours_{_code}_open"] = forms.CharField(required=False, label=_("Ochiladi"), widget=forms.TimeInput(attrs={"type": "time", "data-day": _code, "data-part": "open"}))
    StoreAdminForm.base_fields[f"hours_{_code}_close"] = forms.CharField(required=False, label=_("Yopiladi"), widget=forms.TimeInput(attrs={"type": "time", "data-day": _code, "data-part": "close"}))
    StoreAdminForm.base_fields[f"hours_{_code}_closed"] = forms.BooleanField(required=False, label=_label, widget=forms.CheckboxInput(attrs={"data-day": _code, "data-part": "closed"}))


_store_admin_form_base_init = StoreAdminForm.__init__


def _store_admin_form_init(self, *args, **kwargs):
    """Populates the 21 working-hours fields' initial values from the instance's real working_hours JSON, and makes slug optional (auto-generated in Store.save() if left blank) -- the fields themselves are already declared at class level above."""
    _store_admin_form_base_init(self, *args, **kwargs)  # keeps the class __init__ (brand colour picker)
    from apps.stores.infrastructure.store_admin_ui import CityWidget, PhoneListWidget, SpecialDaysWidget

    self.fields["slug"].required = False
    self.fields["phone_numbers"].widget = PhoneListWidget()
    self.fields["phone_numbers"].help_text = _("Bir nechta raqam bo'lsa, «Raqam qo'shish»ni bosing. Birinchisi asosiy raqam.")
    self.fields["city"].widget = CityWidget()
    self.fields["city"].help_text = _("O'zbekiston viloyatlari va shaharlari ro'yxatidan. Tanlanganda xarita o'sha shaharga o'tadi.")
    self.fields["special_hours"].widget = SpecialDaysWidget()
    self.fields["special_hours"].help_text = _("Bayramlar va maxsus kunlar — haftalik jadvaldan ustun turadi.")
    self.fields["slug"].help_text = _("Saytdagi manzil: /store/<slug>. Bo'sh qoldirilsa nomdan avtomatik yaratiladi.")
    for f in ("telegram_username", "instagram_username"):
        self.fields[f].widget.attrs.setdefault("placeholder", "username")
    hours = (self.instance.working_hours or {}) if self.instance and self.instance.pk else {}
    for code, _label in _WEEKDAYS:
        day = hours.get(code, {})
        self.fields[f"hours_{code}_open"].initial = day.get("open", "")
        self.fields[f"hours_{code}_close"].initial = day.get("close", "")
        self.fields[f"hours_{code}_closed"].initial = day.get("closed", False)


StoreAdminForm.__init__ = _store_admin_form_init


@admin.register(orm.Store)
class StoreAdmin(ExcelExportMixin, admin.ModelAdmin):
    excel_title = "Do'konlar va omborlar"
    excel_columns = [
        Col("Nomi", "name", 24), Col("Turi", "kind", 10), Col("Holat", "status", 10), Col("Shahar", "city", 14), Col("Tuman", "district", 14),
        Col("Manzil", "address", 30), Col("Telefon", lambda s: ", ".join(s.phone_numbers or []), 22), Col("Telegram", "telegram_username", 16),
        Col("Olib ketish", "pickup_enabled", 10), Col("Mahsulot turi", lambda s: getattr(s, "_product_count", None), 12, number=True),
        Col("Jami dona", lambda s: getattr(s, "_units", None), 11, number=True), Col("Reyting", lambda s: round(s._rating, 1) if getattr(s, "_rating", None) else None, 9),
    ]

    form = StoreAdminForm
    inlines = [StoreMediaInline, StoreProductStockInline]
    list_display = ("store_col", "location_col", "rating_col", "sales_col", "stock_col", "open_col", "status_col")
    list_display_links = ("store_col",)
    list_filter = (("kind", _titled("Joy turi")), ("status", _titled("Holat")), ("city", _titled("Shahar")))
    change_list_template = "admin/products/analytics_change_list.html"
    search_fields = ("name", "slug", "owner__username", "owner__full_name", "owner__phone_number", "email")
    list_per_page = 25
    autocomplete_fields = ["owner"]
    readonly_fields = ("id", "logo_display", "cover_image_display", "map_link_display", "map_picker", "created_at", "updated_at")
    change_form_template = "admin/stores/store/change_form.html"

    class Media:
        css = {"all": ("admin/vendor/leaflet/leaflet.css", "admin/css/nutrizone-store-form.css")}
        js = ("admin/vendor/leaflet/leaflet.js", "admin/js/nutrizone-store-form.js")

    @admin.display(description=_("Xaritada"))
    def map_picker(self, obj):
        from apps.stores.infrastructure.store_admin_ui import map_picker_html

        return map_picker_html(obj)
    actions = ["mark_active", "mark_inactive", "mark_temporarily_closed"]

    fieldsets = (
        (_("Asosiy ma'lumot"), {"fields": ("kind", "name", "slug", "status", "description")}),
        (_("Brend rangi"), {"fields": ("color",)}),
        (_("Rasmlar"), {"fields": ("logo_display", "logo_upload", "cover_image_display", "cover_image_upload")}),
        (_("Aloqa"), {"fields": ("phone_numbers", "email", "telegram_username", "instagram_username")}),
        (_("Manzil va xarita"), {"fields": ("city", "district", "address", "map_picker", ("latitude", "longitude"))}),
        (_("Ish vaqti"), {"classes": ("nz-hours",), "fields": tuple((f"hours_{code}_closed", f"hours_{code}_open", f"hours_{code}_close") for code, _l in _WEEKDAYS)}),
        (_("Maxsus kunlar"), {"fields": ("special_hours",)}),
        (_("Egasi (sayt akkaunti)"), {"fields": ("owner",), "description": _("Bu do'konni saytdagi o'z kabinetidan boshqaradigan mijoz akkaunti (dashboard xodimi emas). Ixtiyoriy.")}),
        (_("Tizim ma'lumotlari"), {"classes": ("collapse",), "fields": ("id", "created_at", "updated_at")}),
    )

    def save_formset(self, request, form, formset, change):
        """Stock edits never overwrite the shelf silently: each change becomes an ADJUSTMENT in the stock ledger."""
        if formset.model is not orm.StoreProductStock:
            return super().save_formset(request, form, formset, change)
        from django.db import transaction

        from apps.stores.infrastructure import stock_service

        actor = request.user.get_full_name() or request.user.get_username()

        # Initialize Django formset bookkeeping without directly saving stock.
        # Stock quantities must still be changed through stock_service.move().
        formset.save(commit=False)

        with transaction.atomic():
            for sub in formset.forms:
                if not sub.cleaned_data or not sub.has_changed() or not sub.cleaned_data.get("product_variant"):
                    continue
                variant = sub.cleaned_data["product_variant"]
                new_qty = int(sub.cleaned_data.get("quantity") or 0)
                old_qty = orm.StoreProductStock.objects.filter(store=form.instance, product_variant=variant).values_list("quantity", flat=True).first() or 0
                if new_qty != old_qty:
                    stock_service.move(form.instance, variant.id, new_qty - old_qty, orm.StockMovementType.ADJUSTMENT, reference="ADMIN", actor=actor, note="Admin: qo'lda tuzatish")

    def get_queryset(self, request):
        """Real, professional-grade performance: annotates the real product count in one query rather than triggering an N+1 (one extra query per row) via a naive obj.stock_entries.count() in product_count_display."""
        from django.db.models import Avg, Count, OuterRef, Q, Subquery, Sum

        units = orm.StoreProductStock.objects.filter(store=OuterRef("pk")).values("store").annotate(u=Sum("quantity")).values("u")[:1]
        return super().get_queryset(request).select_related("owner").annotate(
            _product_count=Count("stock_entries", filter=Q(stock_entries__quantity__gt=0), distinct=True),
            _units=Subquery(units),
            _rating=Avg("ratings__rating"), _ratings=Count("ratings", distinct=True),
        )

    # ------------------------------------------------------------ premium list

    def changelist_view(self, request, extra_context=None):
        from collections import Counter

        from django.db.models import Avg, Count

        from apps.products.infrastructure import catalog_analytics as ca
        from apps.products.infrastructure.catalog_admin_ui import kpi
        from apps.stores.infrastructure.store_admin_ui import store_sales

        self._sales = sales = store_sales(30)
        stores = list(orm.Store.objects.all())
        branches = [x for x in stores if x.kind == orm.StoreKind.STORE]
        open_now = sum(1 for x in branches if x.is_open_now())
        rating = orm.StoreRating.objects.aggregate(a=Avg("rating"), n=Count("id"))
        ids = {x.id for x in stores}
        total = sum((v["revenue"] for k, v in sales.items() if k in ids), ca.Decimal(0))  # Dashboard-terminal sales have no store
        prev = sum((v["prev_revenue"] for k, v in sales.items() if k in ids), ca.Decimal(0))
        change = round(float((total - prev) / prev * 100)) if prev else None
        names = {x.id: x.name for x in stores}
        colors = {x.id: x.color or "#64748b" for x in stores}
        rank_rows = [(names.get(sid, "—"), ca.Numbers(units=v["sales"], revenue=v["revenue"], prev_revenue=v["prev_revenue"]), colors.get(sid, "#64748b")) for sid, v in sales.items() if sid in names]
        rank = ca.ranking(rank_rows)
        for r in rank:
            r["color"] = next((colors[x.id] for x in stores if x.name == r["label"]), r["color"])
            r["units"] = f"{r['units']} ta savdo"
        by_city = Counter((x.city or "Shahar yo'q") for x in branches)
        top = rank[0]["label"] if rank else "—"
        nzc = {
            "kpis": [
                kpi("Filiallar", len(branches), "fa-store", "#2563eb", f"{sum(1 for x in branches if x.status == orm.StoreStatus.ACTIVE)} faol"),
                kpi("Hozir ochiq", open_now, "fa-door-open", "#16a34a", "ish vaqti bo'yicha, Toshkent vaqti"),
                kpi("Omborlar (sklad)", len(stores) - len(branches), "fa-warehouse", "#64748b", "sotuv qilmaydi"),
                kpi("O'rtacha reyting", f"{rating['a']:.1f} ★" if rating["a"] else "—", "fa-star", "#f59e0b", f"{rating['n']} ta baho"),
                kpi("30 kunlik tushum", ca.compact(total), "fa-sack-dollar", "#10b981", "so'm · do'kon kassalari", change),
                kpi("Yetakchi filial", top, "fa-crown", "#db2777", rank[0]["revenue"] + " so'm" if rank else ""),
            ],
            "ranking_title": "Filiallar reytingi (tushum)", "ranking": {"rows": rank},
            "donut_title": "Filiallar shaharlar bo'yicha", "donut_unit": "filial", "donut": ca.donut(list(by_city.items())),
        }
        return super().changelist_view(request, {**(extra_context or {}), "nzc": nzc, "title": _("Do'konlar")})

    def change_view(self, request, object_id, form_url="", extra_context=None):
        from django.db.models import Avg, Count, Sum

        from apps.products.infrastructure import catalog_analytics as ca
        from apps.stores.infrastructure.store_admin_ui import stars, store_sales

        extra = dict(extra_context or {})
        store = orm.Store.objects.filter(pk=object_id).first()
        if store is not None:
            v = store_sales(30).get(store.id, {"revenue": 0, "sales": 0})
            r = store.ratings.aggregate(a=Avg("rating"), n=Count("id"))
            st = store.stock_entries.aggregate(u=Sum("quantity"), n=Count("id"))
            shift = orm.CashSession.objects.filter(store=store).order_by("-opened_at").first()
            logo = (store.logo_thumbnail_paths or {}).get("small") or store.logo_storage_path
            from django.conf import settings

            base = (getattr(settings, "FRONTEND_URL", "") or "").rstrip("/")
            extra["nzs_summary"] = {
                "revenue": ca.money(v["revenue"]) + " so'm", "sales": v["sales"], "stars": stars(r["a"], size=".9rem") if r["a"] else "—", "rating_count": r["n"],
                "units": st["u"] or 0, "skus": st["n"], "open_now": store.is_open_now(), "logo": f"/media/{logo}" if logo else "",
                "shift": ("Ochiq" if shift and shift.status == "open" else "Yopiq") if shift else "—",
                "shift_sub": timezone_local(shift.opened_at) if shift else "hali smena ochilmagan",
                "public_url": f"{base}/store/{store.slug}" if base and store.kind == orm.StoreKind.STORE else "",
            }
        return super().change_view(request, object_id, form_url, extra)

    @admin.display(description=_("Do'kon"), ordering="name")
    def store_col(self, obj: orm.Store) -> str:
        logo = (obj.logo_thumbnail_paths or {}).get("small") or obj.logo_storage_path
        mark = format_html('<img src="/media/{}" alt="">', logo) if logo else format_html("<span>{}</span>", (obj.name or "?")[:1].upper())
        kind = mark_safe('<span class="nzc-pill" style="--t:#64748b"><i class="fas fa-warehouse"></i> Sklad</span>') if obj.kind == orm.StoreKind.WAREHOUSE else ""
        return format_html('<div class="nzs-store" style="--c:{}"><span class="nzs-logo">{}</span><span class="nzc-name"><b>{} {}</b><small>/{}</small></span></div>', obj.color or "#64748b", mark, obj.name, kind, obj.slug)

    @admin.display(description=_("Manzil"), ordering="city")
    def location_col(self, obj: orm.Store) -> str:
        phones = obj.phone_numbers or []
        place = ", ".join(p for p in (obj.city, obj.district) if p) or "—"
        return format_html('<div class="nzc-name"><b>{}</b><small>{}</small></div>', place, phones[0] if phones else (obj.address or ""))

    @admin.display(description=_("Reyting"), ordering="_rating")
    def rating_col(self, obj: orm.Store) -> str:
        from apps.stores.infrastructure.store_admin_ui import stars

        return stars(obj._rating, obj._ratings) if obj.kind == orm.StoreKind.STORE else mark_safe('<span class="nzc-muted">—</span>')

    @admin.display(description=_("30 kunlik savdo"))
    def sales_col(self, obj: orm.Store) -> str:
        from apps.products.infrastructure import catalog_analytics as ca

        v = getattr(self, "_sales", {}).get(obj.id)
        if not v or not v["sales"]:
            return mark_safe('<span class="nzc-muted">Savdo yo\'q</span>')
        trend = ""
        if v["prev_revenue"]:
            pct = round(float((v["revenue"] - v["prev_revenue"]) / v["prev_revenue"] * 100))
            trend = format_html(' <em class="nzc-trend {}">{}{}%</em>', "up" if pct >= 0 else "down", "▲ +" if pct >= 0 else "▼ ", pct)
        return format_html('<div class="nzc-sales"><b>{}</b> so\'m{}<small>{} ta savdo</small></div>', ca.money(v["revenue"]), trend, v["sales"])

    @admin.display(description=_("Qoldiq"), ordering="_units")
    def stock_col(self, obj: orm.Store) -> str:
        return format_html('<span class="nzc-count"><b>{}</b><small>dona · {} xil</small></span>', obj._units or 0, obj._product_count)

    @admin.display(description=_("Hozir"))
    def open_col(self, obj: orm.Store) -> str:
        from apps.products.infrastructure.catalog_admin_ui import pill

        if obj.kind == orm.StoreKind.WAREHOUSE:
            return pill("Sklad", "#64748b", "fa-warehouse")
        if obj.status != orm.StoreStatus.ACTIVE:
            return mark_safe('<span class="nzc-muted">—</span>')
        return pill("Ochiq", "#16a34a", "fa-door-open") if obj.is_open_now() else pill("Yopiq", "#64748b", "fa-door-closed")

    @admin.display(description=_("Holat"), ordering="status")
    def status_col(self, obj: orm.Store) -> str:
        from apps.products.infrastructure.catalog_admin_ui import pill

        tone = {"active": "#16a34a", "inactive": "#64748b", "temporarily_closed": "#f59e0b", "coming_soon": "#2563eb"}.get(obj.status, "#64748b")
        return pill(str(obj.get_status_display()), tone)

    @admin.display(description=_("Brand colour"), ordering="color")
    def color_display(self, obj: orm.Store) -> str:
        return format_html('<span style="display:inline-flex;align-items:center;gap:6px"><span style="width:14px;height:14px;border-radius:50%;background:{}"></span><code>{}</code></span>', obj.color or "#94A3B8", obj.color or "—")

    def product_count_display(self, obj: orm.Store) -> str:
        return str(getattr(obj, "_product_count", obj.stock_entries.count()))

    product_count_display.short_description = _("Products")
    product_count_display.admin_order_field = "_product_count"

    def city_district_display(self, obj: orm.Store) -> str:
        parts = [p for p in (obj.city, obj.district) if p]
        return ", ".join(parts) or "—"

    city_district_display.short_description = _("City / District")

    def map_link_display(self, obj: orm.Store) -> str:
        if obj.latitude is None or obj.longitude is None:
            return _("No coordinates set.")
        return format_html('<a href="https://www.google.com/maps?q={},{}" target="_blank" rel="noopener noreferrer">{}</a>', obj.latitude, obj.longitude, _("Open in Google Maps"))

    map_link_display.short_description = _("Map")

    def mark_active(self, request, queryset):
        updated = queryset.update(status=orm.StoreStatus.ACTIVE)
        self.message_user(request, _("%(count)d store(s) marked as Active.") % {"count": updated})

    mark_active.short_description = _("Mark selected stores as Active")

    def mark_inactive(self, request, queryset):
        updated = queryset.update(status=orm.StoreStatus.INACTIVE)
        self.message_user(request, _("%(count)d store(s) marked as Inactive.") % {"count": updated})

    mark_inactive.short_description = _("Mark selected stores as Inactive")

    def mark_temporarily_closed(self, request, queryset):
        updated = queryset.update(status=orm.StoreStatus.TEMPORARILY_CLOSED)
        self.message_user(request, _("%(count)d store(s) marked as Temporarily closed.") % {"count": updated})

    mark_temporarily_closed.short_description = _("Mark selected stores as Temporarily closed")

    def phone_display(self, obj: orm.Store) -> str:
        return ", ".join(obj.phone_numbers or []) or "—"

    phone_display.short_description = _("Phone numbers")

    def status_badge(self, obj: orm.Store) -> str:
        labels = {
            orm.StoreStatus.ACTIVE: ("#1F7A4D", "●"),
            orm.StoreStatus.INACTIVE: ("#8B96A3", "○"),
            orm.StoreStatus.TEMPORARILY_CLOSED: ("#D97706", "⚠"),
            orm.StoreStatus.COMING_SOON: ("#3B82F6", "◐"),
        }
        color, icon = labels.get(obj.status, ("#8B96A3", "○"))
        return format_html('<span style="color:{};font-weight:600;">{} {}</span>', color, icon, obj.get_status_display())

    status_badge.short_description = _("Status")

    def open_now_display(self, obj: orm.Store) -> str:
        if obj.status != orm.StoreStatus.ACTIVE:
            return "—"
        if obj.is_open_now():
            return format_html('<span style="color:#1F7A4D;">{}</span>', "● Open")
        return format_html('<span style="color:#8B96A3;">{}</span>', "○ Closed")

    open_now_display.short_description = _("Open now")

    def get_form(self, request, obj=None, **kwargs):
        """Real, critical fix: Django admin's own get_form() rebuilds a fresh ModelForm via modelform_factory() from `fields`/`fieldsets`, which does not reliably inherit dynamically-mutated base_fields -- it raised FieldError("Unknown field(s)") for the 21 working-hours fields even though they were declared on StoreAdminForm. Returning StoreAdminForm directly (already fully, correctly declared) bypasses that reconstruction entirely."""
        return StoreAdminForm

    def logo_display(self, obj: orm.Store) -> str:
        if not obj.pk or not obj.logo_storage_path:
            return "—"
        thumb = (obj.logo_thumbnail_paths or {}).get("small") or obj.logo_storage_path
        return format_html('<img src="/media/{}" style="max-height:48px;border-radius:6px;" />', thumb)

    logo_display.short_description = _("Logo")

    def cover_image_display(self, obj: orm.Store) -> str:
        if not obj.pk or not obj.cover_image_storage_path:
            return "—"
        thumb = (obj.cover_image_thumbnail_paths or {}).get("medium") or obj.cover_image_storage_path
        return format_html('<img src="/media/{}" style="max-height:120px;border-radius:8px;" />', thumb)

    cover_image_display.short_description = _("Cover image")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        form.save_media(obj)


class ReviewStateFilter(admin.SimpleListFilter):
    title = "Izoh"
    parameter_name = "review"

    def lookups(self, request, model_admin):
        return [("new", "Yangi (o'qilmagan)"), ("with", "Izohli"), ("without", "Faqat baho")]

    def queryset(self, request, qs):
        v = self.value()
        if v == "new":
            return qs.filter(is_read=False).exclude(comment="")
        if v == "with":
            return qs.exclude(comment="")
        if v == "without":
            return qs.filter(comment="")
        return qs


@admin.register(orm.StoreRating)
class StoreRatingAdmin(ExcelExportMixin, admin.ModelAdmin):
    """Read-mostly moderation view -- a rating is customer-submitted from the storefront, never created here; staff can still inspect/remove an abusive one."""
    excel_title = "Filial baholari"
    excel_select_related = ("store", "customer")
    excel_columns = [
        Col("Sana", "created_at", 17), Col("Filial", lambda r: r.store.name if r.store else "", 20), Col("Mijoz", lambda r: r.customer.full_name if r.customer else "", 22),
        Col("Telefon", lambda r: r.customer.phone_number if r.customer else "", 15), Col("Baho", "rating", 7, number=True), Col("Izoh", "comment", 40),
    ]


    list_display = ("store_col", "stars_col", "review_col", "customer_col", "when_col")
    readonly_fields = ("store_col", "stars_col", "customer_col", "review_full", "when_col")
    fields = ("store_col", "stars_col", "customer_col", "review_full", "when_col")
    actions = ("mark_read",)

    class Media:
        css = {"all": ("admin/css/nutrizone-store-form.css",)}

    # Reviews are private feedback for management: the whole section is superadmin-only.
    def has_module_permission(self, request) -> bool:
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None) -> bool:
        return request.user.is_active and request.user.is_superuser

    def has_change_permission(self, request, obj=None) -> bool:
        return False  # a customer's words are never edited

    def has_delete_permission(self, request, obj=None) -> bool:
        return request.user.is_active and request.user.is_superuser  # removing an abusive one stays possible

    def has_add_permission(self, request) -> bool:
        return False  # ratings come from customers on the storefront

    def get_list_filter(self, request):
        return (ReviewStateFilter, *self.list_filter)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        orm.StoreRating.objects.filter(pk=object_id, is_read=False).update(is_read=True)  # opened = read
        return super().change_view(request, object_id, form_url, extra_context)

    @admin.action(description=_("O'qilgan deb belgilash"))
    def mark_read(self, request, queryset):
        n = queryset.filter(is_read=False).update(is_read=True)
        self.message_user(request, _("%(n)d ta izoh o'qilgan deb belgilandi.") % {"n": n})

    @admin.display(description=_("Izoh (faqat superadmin)"))
    def review_col(self, obj) -> str:
        if not obj.comment:
            return mark_safe('<span class="nzc-muted">—</span>')
        new = mark_safe('<span class="nzc-pill" style="--t:#e11d48">Yangi</span> ') if not obj.is_read else ""
        text = obj.comment if len(obj.comment) <= 140 else obj.comment[:140] + "…"
        return format_html('<div class="nzs-review">{}<span>{}</span></div>', new, text)

    @admin.display(description=_("Mijoz izohi"))
    def review_full(self, obj) -> str:
        if not obj.comment:
            return mark_safe('<span class="nzc-muted">Mijoz faqat baho qo\'ygan, izoh yozmagan.</span>')
        from django.utils import timezone

        when = timezone.localtime(obj.commented_at).strftime("%d.%m.%Y %H:%M") if obj.commented_at else ""
        return format_html('<blockquote class="nzs-quote">{}<footer>{} · {}</footer></blockquote>', obj.comment, obj.customer.full_name or obj.customer.phone_number, when)
    list_display_links = ("stars_col",)
    list_filter = (("rating", _titled("Baho")), ("store", _titled("Do'kon")))
    list_select_related = ("store", "customer")
    change_list_template = "admin/products/analytics_change_list.html"
    ordering = ("-updated_at",)

    def changelist_view(self, request, extra_context=None):
        from datetime import timedelta

        from django.db.models import Avg, Count
        from django.utils import timezone

        from apps.products.infrastructure import catalog_analytics as ca
        from apps.products.infrastructure.catalog_admin_ui import kpi

        qs = orm.StoreRating.objects.all()
        agg = qs.aggregate(a=Avg("rating"), n=Count("id"))
        dist = {r["rating"]: r["n"] for r in qs.values("rating").annotate(n=Count("id"))}
        month = qs.filter(updated_at__gte=timezone.now() - timedelta(days=30)).aggregate(a=Avg("rating"), n=Count("id"))
        per_store = list(orm.Store.objects.filter(kind=orm.StoreKind.STORE).annotate(a=Avg("ratings__rating"), n=Count("ratings")).filter(n__gt=0).order_by("-a", "-n"))
        n = agg["n"] or 0
        rank = [{"label": x.name, "revenue": f"{x.a:.2f} ★", "units": f"{x.n} ta baho", "pct": int(float(x.a) * 20), "color": x.color or ca.PALETTE[i % 10], "change": None} for i, x in enumerate(per_store[:5])]
        donut = ca.donut([(f"{k} ★", dist.get(k, 0)) for k in (5, 4, 3, 2, 1)])
        tones = {"5 ★": "#16a34a", "4 ★": "#84cc16", "3 ★": "#f59e0b", "2 ★": "#f97316", "1 ★": "#e11d48"}
        for item in donut["legend"]:
            item["color"] = tones.get(item["label"], item["color"])
        acc, stops = 0.0, []
        for item in donut["legend"]:
            start, acc = acc, acc + item["value"] * 100 / (donut["total"] or 1)
            stops.append(f"{item['color']} {start:.2f}% {acc:.2f}%")
        donut["gradient"] = f"conic-gradient({', '.join(stops)})" if stops else ""
        nzc = {
            "kpis": [
                kpi("O'rtacha baho", f"{agg['a']:.2f} ★" if agg["a"] else "—", "fa-star", "#f59e0b", f"{n} ta baho"),
                kpi("5 yulduz", f"{round(dist.get(5, 0) * 100 / n) if n else 0}%", "fa-face-smile", "#16a34a", f"{dist.get(5, 0)} ta mijoz"),
                kpi("Salbiy (1–2★)", dist.get(1, 0) + dist.get(2, 0), "fa-face-frown", "#e11d48", "e'tibor talab qiladi"),
                kpi("So'nggi 30 kun", month["n"] or 0, "fa-calendar", "#2563eb", f"o'rtacha {month['a']:.1f} ★" if month["a"] else "yangi baho yo'q"),
                kpi("Yangi izohlar", qs.filter(is_read=False).exclude(comment="").count(), "fa-envelope", "#8b5cf6", f"jami {qs.exclude(comment='').count()} ta izoh"),
                kpi("Eng yaxshi", per_store[0].name if per_store else "—", "fa-trophy", "#db2777", f"{per_store[0].a:.2f} ★" if per_store else ""),
            ],
            "ranking_title": "Filiallar reytingi (baho)", "ranking": {"rows": rank},
            "donut_title": "Baholar taqsimoti", "donut_unit": "baho", "donut": donut,
        }
        return super().changelist_view(request, {**(extra_context or {}), "nzc": nzc, "title": _("Do'kon baholari va izohlari")})

    @admin.display(description=_("Do'kon"), ordering="store__name")
    def store_col(self, obj) -> str:
        return format_html('<span class="nzs-store" style="--c:{}"><span class="nzs-dot"></span><b>{}</b></span>', obj.store.color or "#64748b", obj.store.name)

    @admin.display(description=_("Baho"), ordering="rating")
    def stars_col(self, obj) -> str:
        from apps.stores.infrastructure.store_admin_ui import stars

        return stars(obj.rating, size=".95rem")

    @admin.display(description=_("Mijoz"), ordering="customer__full_name")
    def customer_col(self, obj) -> str:
        return format_html('<div class="nzc-name"><b>{}</b><small>{}</small></div>', obj.customer.full_name or "Mijoz", obj.customer.phone_number)

    @admin.display(description=_("Sana"), ordering="updated_at")
    def when_col(self, obj) -> str:
        from django.utils import timezone

        return timezone.localtime(obj.updated_at).strftime("%d.%m.%Y %H:%M")
    search_fields = ("store__name", "store__slug", "customer__full_name", "customer__phone_number")
    autocomplete_fields = ["store", "customer"]
    readonly_fields = ("created_at", "updated_at")


def _shift_totals(s) -> dict:
    """A closed shift's frozen Z-report figures, or the live ones of an open shift."""
    if s.status == orm.CashSessionStatus.CLOSED:
        return {k: getattr(s, k) for k in ("sales_count", "items_sold", "gross_sales", "discounts_total", "cash_sales", "uzcard_sales", "humo_sales",
                                           "coins_redeemed", "refunds_total")} | {"expected_cash": s.expected_cash}
    from apps.stores.infrastructure.pos_service import _session_totals

    return _session_totals(s)


@admin.register(orm.CashSession)
class CashSessionAdmin(ExcelExportMixin, admin.ModelAdmin):
    excel_title = "Kassa smenalari (Z-hisobot)"
    excel_select_related = ("store", "opened_by", "closed_by")
    excel_columns = [
        Col("Kassa", "store.name", 22), Col("Holat", lambda s: "Ochiq" if s.status == orm.CashSessionStatus.OPEN else "Yopilgan", 10),
        Col("Ochilgan", "opened_at", 17), Col("Yopilgan", "closed_at", 17),
        Col("Ochgan", lambda s: s.opened_by_name or (s.opened_by.full_name if s.opened_by else ""), 20),
        Col("Yopgan", lambda s: s.closed_by_name or (s.closed_by.full_name if s.closed_by else ""), 20),
        Col("Sotuvlar", lambda s: s.x["sales_count"], 10, number=True), Col("Dona", lambda s: s.x["items_sold"], 9, number=True),
        Col("Yalpi savdo", lambda s: s.x["gross_sales"], 15, money=True), Col("Chegirma", lambda s: s.x["discounts_total"], 13, money=True),
        Col("Naqd", lambda s: s.x["cash_sales"], 14, money=True), Col("Uzcard", lambda s: s.x["uzcard_sales"], 14, money=True),
        Col("Humo", lambda s: s.x["humo_sales"], 14, money=True), Col("Coins", lambda s: s.x["coins_redeemed"], 12, money=True),
        Col("Qaytarishlar", lambda s: s.x["refunds_total"], 13, money=True), Col("Kutilgan naqd", lambda s: s.x["expected_cash"], 14, money=True),
        Col("Sanalgan naqd", "counted_cash", 14, money=True), Col("Farq", "cash_difference", 12, money=True), Col("Izoh", "closing_note", 26),
    ]

    def excel_prepare(self, objs):
        for s in objs:
            s.x = _shift_totals(s)

    """
    Cash Register Management: every shift of every branch -- who opened / closed
    it, when, the float, what was sold in it split by cash / Uzcard / Humo / coins,
    the expected vs counted drawer and the shortage / overage. Open shifts show
    live figures; closed ones their frozen Z-report. Read-only: shifts are opened
    and closed only from the store's own POS terminal.
    """

    list_display = (
        "store", "status_badge", "opened_local", "closed_local", "duration_display", "opened_by",
        "sales_col", "gross_display", "cash_display", "cards_display", "coins_display", "expected_display", "difference_display",
    )
    list_display_links = ("store",)
    list_filter = ("status", "store", ("opened_at", admin.DateFieldListFilter))
    search_fields = ("store__name", "opened_by__full_name", "opened_by__phone_number")
    date_hierarchy = "opened_at"
    list_select_related = ("store", "opened_by", "closed_by")
    ordering = ("-opened_at",)
    list_per_page = 30
    change_list_template = "admin/stores/cashsession/change_list.html"
    fieldsets = (
        (_("Shift"), {"fields": ("store", "status_badge", "opened_by", "opened_local", "opening_cash", "opening_note", "closed_by", "closed_local", "duration_display", "closing_note")}),
        (_("Z-report"), {"fields": ("z_report",)}),
        (_("Sales in this shift"), {"fields": ("sales_table",)}),
    )

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields] + ["status_badge", "opened_local", "closed_local", "duration_display", "z_report", "sales_table"]

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    def changelist_view(self, request, extra_context=None):
        from datetime import datetime, time
        from zoneinfo import ZoneInfo

        from django.utils import timezone

        from apps.pos.infrastructure import sales_reports as rep

        tz = ZoneInfo("Asia/Tashkent")
        today = datetime.combine(timezone.localtime(timezone.now(), tz).date(), time.min, tzinfo=tz)
        month = today.replace(day=1)
        store_sales = rep.closed_sales().filter(channel="store")
        today_summary = rep.summary(rep.rows(store_sales.filter(completed_at__gte=today)))
        closed_month = orm.CashSession.objects.filter(status=orm.CashSessionStatus.CLOSED, closed_at__gte=month)
        from django.db.models import Sum

        shortage = closed_month.filter(cash_difference__lt=0).aggregate(v=Sum("cash_difference"))["v"] or 0
        overage = closed_month.filter(cash_difference__gt=0).aggregate(v=Sum("cash_difference"))["v"] or 0
        extra_context = {
            **(extra_context or {}),
            "shift_kpis": {
                "open": orm.CashSession.objects.filter(status=orm.CashSessionStatus.OPEN).count(),
                "stores": orm.Store.objects.filter(status="active").count(),
                "today": today_summary,
                "shortage": shortage, "overage": overage,
                "closed_month": closed_month.count(),
            },
        }
        return super().changelist_view(request, extra_context)

    # --- figures: live for an open shift, the frozen Z-report for a closed one ---

    def _totals(self, obj) -> dict:
        if not hasattr(obj, "_totals"):
            from apps.stores.infrastructure import pos_service

            obj._totals = pos_service.session_totals(obj)
        return obj._totals

    @admin.display(description=_("Status"), ordering="status")
    def status_badge(self, obj):
        from django.utils.html import format_html

        open_ = obj.status == orm.CashSessionStatus.OPEN
        return format_html('<span class="nzs-pill {}">{}{}</span>', "nzs-live" if open_ else "nzs-closed", "● " if open_ else "", obj.get_status_display())

    @staticmethod
    def _local(value) -> str:
        # Stores run on Tashkent time; the project clock (TIME_ZONE) is UTC.
        from zoneinfo import ZoneInfo

        from django.utils import timezone

        return timezone.localtime(value, ZoneInfo("Asia/Tashkent")).strftime("%d.%m.%Y %H:%M") if value else "—"

    @admin.display(description=_("Opened at"), ordering="opened_at")
    def opened_local(self, obj):
        return self._local(obj.opened_at)

    @admin.display(description=_("Closed at"), ordering="closed_at")
    def closed_local(self, obj):
        from django.utils.html import format_html

        return self._local(obj.closed_at) if obj.closed_at else format_html('<span class="nzs-pill nzs-live">{}</span>', _("Open"))

    @admin.display(description=_("Duration"))
    def duration_display(self, obj):
        from django.utils import timezone

        minutes = int(((obj.closed_at or timezone.now()) - obj.opened_at).total_seconds() // 60)
        return f"{minutes // 60}h {minutes % 60:02d}m"

    @staticmethod
    def _som(value) -> str:
        return f"{int(value or 0):,}".replace(",", " ")

    @admin.display(description=_("Sales"), ordering="sales_count")
    def sales_col(self, obj):
        return self._totals(obj)["sales_count"]

    @admin.display(description=_("Gross sales"), ordering="gross_sales")
    def gross_display(self, obj):
        from django.utils.html import format_html

        t = self._totals(obj)
        return format_html("<strong>{}</strong>", self._som(t["gross_sales"] - t["discounts_total"]))

    @admin.display(description=_("Cash taken"), ordering="cash_sales")
    def cash_display(self, obj):
        return self._som(self._totals(obj)["cash_sales"])

    @admin.display(description="Uzcard / Humo")
    def cards_display(self, obj):
        from django.utils.html import format_html

        t = self._totals(obj)
        return format_html('<span title="Uzcard {} · Humo {}">{}</span>', self._som(t["uzcard_sales"]), self._som(t["humo_sales"]), self._som(t["uzcard_sales"] + t["humo_sales"]))

    @admin.display(description=_("Paid with coins"), ordering="coins_redeemed")
    def coins_display(self, obj):
        return self._som(self._totals(obj)["coins_redeemed"])

    @admin.display(description=_("Expected cash"))
    def expected_display(self, obj):
        return self._som(self._totals(obj)["expected_cash"])

    @admin.display(description=_("Difference"), ordering="cash_difference")
    def difference_display(self, obj):
        from django.utils.html import format_html

        if obj.cash_difference is None:
            return "—"
        color = "#16a34a" if obj.cash_difference == 0 else "#dc2626" if obj.cash_difference < 0 else "#d97706"
        return format_html('<strong style="color:{}">{}</strong>', color, f"{int(obj.cash_difference):+,}".replace(",", " "))

    @admin.display(description=_("Z-report"))
    def z_report(self, obj):
        from django.utils.html import format_html, format_html_join

        t = self._totals(obj)
        rows = [
            (_("Sales"), t["sales_count"]), (_("Units sold"), t["items_sold"]),
            (_("Gross sales"), self._som(t["gross_sales"])), (_("Discounts"), "−" + self._som(t["discounts_total"])),
            (_("Paid with coins"), "−" + self._som(t["coins_redeemed"])),
            (_("Cash taken"), self._som(t["cash_sales"])), ("Uzcard", self._som(t["uzcard_sales"])), ("Humo", self._som(t["humo_sales"])),
            (_("Refunds"), f'{t["refunds_count"]} · −{self._som(t["refunds_total"])}'), (_("Cash refunded"), "−" + self._som(t["cash_refunded"])),
            (_("Opening cash (float)"), self._som(obj.opening_cash)), (_("Expected cash"), self._som(t["expected_cash"])),
            (_("Counted cash"), self._som(obj.counted_cash) if obj.counted_cash is not None else "—"),
        ]
        body = format_html_join("", '<tr><td>{}</td><td class="num">{}</td></tr>', ((str(k), v) for k, v in rows))
        return format_html('<table class="nzs-table" style="max-width:520px">{}<tr><td><strong>{}</strong></td><td class="num">{}</td></tr></table>', body, _("Difference"), self.difference_display(obj))

    @admin.display(description=_("Sales in this shift"))
    def sales_table(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html, format_html_join

        from apps.pos.infrastructure import sales_reports as rep
        from apps.pos.infrastructure.models import SaleModel

        data = sorted(rep.rows(SaleModel.objects.filter(cash_session_id=obj.id).exclude(status__in=["open", "voided"])), key=lambda r: r["when"])
        if not data:
            return "—"
        products = rep.product_summary([r["id"] for r in data])
        labels = {"cash": _("Cash"), "uzcard": "Uzcard", "humo": "Humo"}
        body = format_html_join("", '<tr><td><a href="{}">{}</a></td><td>{}</td><td>{}</td><td>{}</td><td class="num">{}</td><td class="num">{}</td><td>{}</td></tr>', (
            (
                reverse("admin:pos_salemodel_change", args=[r["id"]]), r["receipt_number"] or str(r["id"])[:8],
                self._local(r["completed_at"])[-5:], ", ".join(f"{n} × {q}" for n, q in products.get(r["id"], []))[:90],
                " + ".join(str(labels.get(m, m)) for m in r["split_sold"]) or "—", self._som(sum(r["split_sold"].values())), self._som(r["coins_redeemed"]) if r["coins_redeemed"] else "—",
                str(_("Refunded")) if r["status"] == "refunded" else (f'−{self._som(r["returned"])}' if r["returned"] else ""),
            ) for r in data
        ))
        return format_html('<table class="nzs-table"><thead><tr><th>#</th><th>{}</th><th>{}</th><th>{}</th><th class="num">{}</th><th class="num">Coins</th><th></th></tr></thead><tbody>{}</tbody></table>', _("Time"), _("Products"), _("Payment"), _("Paid"), body)


from apps.stores.infrastructure import (  # noqa: E402
    count_admin,  # noqa: E402,F401  (registers the stock count / Inventarizatsiya admin)
    planning_admin,  # noqa: E402,F401  (reorder points / replenishment, expiry)
    pos_cashier_admin,  # noqa: E402,F401  (POS cashiers / PIN sign-in)
    supplier_admin,  # noqa: E402,F401  (suppliers and accounts payable)
    warehouse_admin,  # noqa: E402,F401  (registers the WMS admins: transfers, goods receipts, ledger)
    writeoff_admin,  # noqa: E402,F401  (write-offs / Hisobdan chiqarish)
)
