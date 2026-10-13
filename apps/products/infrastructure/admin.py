"""
Django Admin registration -- engineering/ops debugging tool only, per
Django Implementation Blueprint §13 and MIC §9's Admin Contract (NOT
the business-facing Admin CRM, which is a separate Next.js frontend
consuming the REST API). Every mutating admin action calls the
module's own Application Service rather than saving the ORM object
directly (MIC §9's bulk-action rule) -- matching
`apps/identity/infrastructure/admin.py`'s exact pattern.
"""
from __future__ import annotations

from decimal import Decimal

from django import forms
from django.conf import settings
from django.contrib import admin
from django.utils.html import format_html, mark_safe
from django.utils.translation import gettext_lazy as _

from apps.platform.infrastructure.excel_export import Col, ExcelExportMixin
from apps.products.application.services._shared import ProductServiceContext
from apps.products.application.services.lifecycle import (
    ArchiveProduct,
    DeleteProduct,
    HideProduct,
    PublishProduct,
    RestoreProduct,
)
from apps.products.infrastructure import models as orm
from apps.products.infrastructure.catalog_form_ui import (
    CatalogFormMixin,
    TranslationInlineMixin,
    media_url,
    sales_stat,
    stat,
    storefront_url,
)
from apps.products.infrastructure.repositories import (
    DjangoBrandRepository,
    DjangoCategoryRepository,
    DjangoProductRepository,
)
from core.outbox import stage_event


def _stage_products_events(events: list[tuple[str, dict]]) -> None:
    for event_type, payload in events:
        stage_event(orm.ProductsOutboxEvent, event_type, payload)


def _admin_ctx(request) -> ProductServiceContext:
    return ProductServiceContext(stage_events=_stage_products_events, actor_id=getattr(request.user, "id", None))


class ProductTranslationInline(TranslationInlineMixin, admin.StackedInline):
    model = orm.ProductTranslation
    fields = ("locale_code", "name", "slug", "description")
    verbose_name = _("Tarjima")
    verbose_name_plural = _("Nomi va tavsifi (uz · ru · en)")


class ProductVariantAdminForm(forms.ModelForm):
    """
    Real, closed bug: this form previously had no override at all --
    Django's own auto-generated ModelForm treats `barcode` as a plain
    CharField with zero validation, so an invalid-checksum value saved
    here without error. The domain's own Barcode value object only
    runs later, when the Product is re-read (e.g. during the image
    upload step's `get_by_id()` reconstruction) -- by then the
    invalid row is already committed, and the crash surfaces as an
    unrelated HTTP 500 during media upload rather than a barcode
    field error at save time.

    Reuses the exact same, unmodified domain Barcode value object
    (never a second, parallel validation rule) -- clean_barcode()
    only translates its ValidationFailed into a proper Django admin
    form error, so an invalid barcode is now rejected before this
    row is ever saved, and image upload is never reached with bad
    data in the first place. An empty barcode remains valid, matching
    ProductVariant.barcode's own nullable field.
    """

    class Meta:
        model = orm.ProductVariant
        fields = "__all__"

    def clean_barcode(self) -> str:
        from apps.products.domain.value_objects import Barcode
        from common.exceptions import ValidationFailed as DomainValidationFailed

        value = self.cleaned_data.get("barcode")
        if not value:
            return value
        try:
            Barcode(value)
        except DomainValidationFailed as exc:
            raise forms.ValidationError(str(exc)) from exc
        return value

    def clean_sku(self) -> str:
        """
        Real, closed bug found live during this same phase's own
        testing: SKU has the exact same gap as barcode -- the domain's
        own SKU value object (uppercase alphanumeric, hyphen-separated)
        never ran here, so an invalid SKU saved without error and only
        crashed later during the identical get_by_id() reconstruction
        path barcode did. Same fix shape, same reused domain value
        object, required rather than optional (SKU is not nullable).
        """
        from apps.products.domain.value_objects import SKU
        from common.exceptions import ValidationFailed as DomainValidationFailed

        value = self.cleaned_data.get("sku")
        if not value:
            return value
        try:
            SKU(value)
        except DomainValidationFailed as exc:
            raise forms.ValidationError(str(exc)) from exc
        return value

    base_cost_price = forms.DecimalField(
        max_digits=14, decimal_places=2, required=False, label=_("Base price (cost)"),
        help_text=_("Internal acquisition/cost price -- never shown to customers. Optional; independent of Price/Old price."),
    )
    price = forms.DecimalField(max_digits=14, decimal_places=2, required=False, label=_("Price (selling price)"), help_text=_("Sets/updates this variant's real selling price in the default price list."))
    old_price = forms.DecimalField(max_digits=14, decimal_places=2, required=False, label=_("Old price (strike-through)"), help_text=_("Optional. Shown crossed out next to Price on the storefront when set and higher than Price."))
    stock = forms.IntegerField(
        min_value=0, max_value=100000, required=False, label=_("Opening stock"),
        help_text=_("Units already on hand: posted to the main warehouse as a goods receipt (Kirim) at the cost price above. Later changes go through Ombor documents only."),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        entry = _default_price_entry_for(self.instance.id) if self.instance and self.instance.pk else None
        if entry is not None:
            self.fields["base_cost_price"].initial = entry.cost_price_amount
            self.fields["price"].initial = entry.base_price_amount
            self.fields["old_price"].initial = entry.compare_at_price_amount

    def clean(self):
        cleaned = super().clean()
        price, old_price = cleaned.get("price"), cleaned.get("old_price")
        if price is not None and old_price is not None and old_price <= price:
            raise forms.ValidationError({"old_price": "Old price must be greater than Price (it's shown as the crossed-out, pre-discount amount)."})
        return cleaned

    def save(self, commit=True):
        is_new = self._nz_new = self.instance._state.adding
        instance = super().save(commit=False)
        if commit:
            if is_new:
                instance.save()
                self.save_m2m()
            else:
                # Real, closed bug: this form class is shared by two
                # separate TabularInlines over the identical
                # ProductVariant model (ProductVariantInline and
                # ProductPricingInline, see both classes' own
                # docstrings) -- Django admin constructs each inline's
                # formset from its own independent queryset, so both
                # hold their own stale in-memory copy of the same row.
                # A blind full-row `instance.save()` from whichever
                # inline's formset happens to save second would
                # silently overwrite whatever the OTHER inline had
                # just written (e.g. a newly assigned Package/weight
                # reverting to null) with its own stale values --
                # confirmed live via a real admin edit. Restricting the
                # UPDATE to only the real model fields THIS specific
                # bound form actually declares means neither inline can
                # ever clobber a field it doesn't own; version/updated_at
                # are always included so optimistic-locking/timestamps
                # still advance on every partial save.
                model_field_names = {f.name for f in instance._meta.concrete_fields if not f.primary_key}
                update_fields = {name for name in self.fields if name in model_field_names} | {"version", "updated_at"}
                instance.save(update_fields=update_fields)
                self.save_m2m()
            self._save_price(instance)
            self._save_stock(instance)
        return instance

    def _save_price(self, instance) -> None:
        """
        Real, closed bug: this previously wrote straight to
        PriceListEntryModel via a raw update_or_create AND silently did
        nothing at all (no error, price entered by the admin just
        discarded) whenever no active, region-less price list existed
        yet -- confirmed as the exact reason zero PriceListEntry rows
        existed anywhere in the database despite this form looking
        fully functional. Now routes through the real `SetPrice`
        Application Service (the same one apps.telegram_bot's pricing
        integration and the pricing REST admin endpoint use -- never a
        second, divergent write path), which also records a real
        PriceHistoryEntry and invalidates the pricing cache, and lazily
        creates+activates a default price list on first use instead of
        failing silently.

        Blank fields leave that specific value untouched (never erase
        an existing price by clearing an unrelated field) -- Price
        (the mandatory `base_amount` the domain requires) falls back to
        the existing entry's own base price if left blank; with no
        existing entry AND no Price entered, there is nothing to anchor
        a first-time price entry on, so nothing is saved (matching this
        form's own prior "blank Price means untouched" contract).
        """
        base_cost = self.cleaned_data.get("base_cost_price")
        price = self.cleaned_data.get("price")
        old_price = self.cleaned_data.get("old_price")
        if base_cost is None and price is None and old_price is None:
            return

        existing_list = _default_price_list()
        existing_entry = None
        if existing_list is not None:
            from apps.pricing.infrastructure.models import PriceListEntryModel

            existing_entry = PriceListEntryModel.objects.filter(price_list=existing_list, product_variant_id=instance.id).first()

        effective_base = price if price is not None else (existing_entry.base_price_amount if existing_entry else None)
        if effective_base is None:
            return  # No Price to anchor a first-time entry on -- nothing saved, matching this field's own "blank = untouched" contract.
        if existing_entry is not None and effective_base == existing_entry.base_price_amount \
                and (base_cost is None or base_cost == existing_entry.cost_price_amount) \
                and (old_price is None or old_price == existing_entry.compare_at_price_amount):
            return  # nothing changed: saving the product form again must not write a "180 000 → 180 000" history row

        from apps.pricing.domain.exceptions import PriceListArchived
        from apps.pricing.infrastructure import composition as pricing_composition
        from common.exceptions import ConflictError

        price_list = _get_or_create_default_price_list()
        try:
            pricing_composition.build_set_price().execute(
                price_list_id=price_list.id,
                product_variant_id=instance.id,
                base_amount=effective_base,
                currency=price_list.currency,
                cost_amount=base_cost if base_cost is not None else (existing_entry.cost_price_amount if existing_entry else None),
                sale_amount=existing_entry.sale_price_amount if existing_entry else None,
                compare_at_amount=old_price if old_price is not None else (existing_entry.compare_at_price_amount if existing_entry else None),
            )
        except (PriceListArchived, ConflictError) as exc:
            raise forms.ValidationError(str(exc)) from exc

    def _save_stock(self, instance) -> None:
        """
        Opening stock of a NEW variant becomes a real goods receipt (Kirim) at the main warehouse, through the WMS
        (stock_service.post_receipt: ledger row, batch, storefront availability) -- never a direct quantity write.
        An existing variant's stock is never edited here: it changes only through Ombor documents.
        """
        stock = self.cleaned_data.get("stock")
        if not stock or not getattr(self, "_nz_new", False):
            return
        from apps.stores.infrastructure import stock_service
        from apps.stores.infrastructure.online_fulfilment import fulfilment_store

        store = fulfilment_store()
        if store is None:
            return
        cost = self.cleaned_data.get("base_cost_price")
        stock_service.post_receipt(store, [{"variant_id": instance.id, "quantity": stock, "unit_cost": cost}], "Mahsulot kartasi",
                                   note=f"Boshlang'ich qoldiq: {instance.sku}")


def _default_price_list():
    from apps.pricing.infrastructure.models import PriceListModel

    return PriceListModel.objects.filter(status="active", region__isnull=True).order_by("created_at").first()


_DEFAULT_PRICE_LIST_CODE = "DEFAULT-UZS"  # Must match PriceListCode's real format rule (uppercase alphanumeric segments, hyphen-separated) -- confirmed directly against apps.pricing.domain.value_objects.PriceListCode.


def _get_or_create_default_price_list():
    """
    Real, closed gap: `_default_price_list()` (above) only ever *looked*
    for an active, region-less price list -- nothing anywhere ever
    *created* one, so on a fresh install (confirmed directly: zero
    PriceListModel rows existed) the very first attempt to set any
    product's price had nowhere to write to. Lazily creates+activates
    one "default" price list the first time any admin sets a price,
    via the same real CreatePriceList/ActivatePriceList Application
    Services the dedicated Pricing admin section itself would use --
    never a second, ad hoc price-list-creation path. Idempotent: a
    second call (any later price edit) finds the now-active list via
    the exact same query `_default_price_list()` uses and returns it
    unchanged.
    """
    from apps.pricing.infrastructure import composition as pricing_composition
    from apps.pricing.infrastructure.models import PriceListModel

    existing_active = _default_price_list()
    if existing_active is not None:
        return existing_active

    existing_any_status = PriceListModel.objects.filter(code=_DEFAULT_PRICE_LIST_CODE).first()
    if existing_any_status is not None:
        if existing_any_status.status != "active":
            activated = pricing_composition.build_activate_price_list().execute(existing_any_status.id)
            return PriceListModel.objects.get(id=activated.id)
        return existing_any_status

    created = pricing_composition.build_create_price_list().execute(code=_DEFAULT_PRICE_LIST_CODE, name="Default Price List", currency="UZS", region=None)
    activated = pricing_composition.build_activate_price_list().execute(created.id)
    return PriceListModel.objects.get(id=activated.id)


def _default_price_entry_for(variant_id):
    price_list = _default_price_list()
    if price_list is None:
        return None
    from apps.pricing.infrastructure.models import PriceListEntryModel

    return PriceListEntryModel.objects.filter(price_list=price_list, product_variant_id=variant_id).first()


PACKAGE_ICONS = {
    "jar": "fa-jar", "tub": "fa-bucket", "bottle": "fa-bottle-water", "pouch": "fa-bag-shopping", "bag": "fa-sack-xmark",
    "box": "fa-box", "sachet": "fa-envelope", "stick-pack": "fa-grip-lines-vertical", "blister": "fa-tablets",
    "capsule-bottle": "fa-prescription-bottle", "can": "fa-whiskey-glass", "shot": "fa-vial", "gel-pack": "fa-droplet",
    "bar-wrapper": "fa-cookie-bite", "multipack": "fa-boxes-stacked", "dropper-bottle": "fa-eye-dropper",
}


class PackagePickerSelect(forms.Select):
    """A plain <select> (works without JS) whose options carry icon / translations; nutrizone-catalog-form.js turns it into a searchable icon picker."""

    def __init__(self, attrs=None, choices=()):
        super().__init__({"class": "nzpk-select", **(attrs or {})}, choices)
        self._meta: dict = {}

    def _load_meta(self) -> None:
        if self._meta:
            return
        for pkg in orm.Package.objects.prefetch_related("translations"):
            names = {t.locale_code: t.name for t in pkg.translations.all()}
            self._meta[str(pkg.pk)] = {"slug": pkg.slug, "icon": PACKAGE_ICONS.get(pkg.slug, "fa-box"), "uz": names.get("uz") or names.get("en") or pkg.slug,
                                       "sub": " · ".join(v for v in (names.get("ru"), names.get("en")) if v)}

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        key = str(getattr(value, "value", value) or "")
        if key:
            self._load_meta()
            meta = self._meta.get(key)
            if meta:
                option["label"] = meta["uz"]
                option["attrs"].update({"data-icon": meta["icon"], "data-slug": meta["slug"], "data-sub": meta["sub"]})
        return option


def _package_formfield(db_field, request, **kwargs):
    kwargs["queryset"] = orm.Package.objects.filter(is_active=True).order_by("sort_order", "slug")
    kwargs["widget"] = PackagePickerSelect()
    kwargs["empty_label"] = "Qadoqsiz"
    return db_field.formfield(**kwargs)


class ProductVariantInline(admin.TabularInline):
    """
    Real, product-required simplification: this table used to show 11
    columns on one row (SKU/Flavor/Barcode/Status/Default/Weight/Base
    price/Price/Old price/Discount/Stock) -- wide enough to force
    horizontal scrolling and bury the identity/stock fields an admin
    actually scans this table for behind pricing columns they only
    rarely touch here. Pricing now lives in its own, separate
    `ProductPricingInline` section below (and in the dedicated Price
    List page) -- this table keeps only the fields that identify and
    stock a variant, never a second source for Base/Old/Price (which
    remain real PriceListEntry data, unchanged).
    """

    model = orm.ProductVariant
    form = ProductVariantAdminForm
    extra = 0
    # Flavour is now a Product-level tag (see ProductAdmin's own
    # `ProductFlavourInline` below), not a per-variant attribute --
    # this table keeps only what actually varies per variant: identity,
    # weight/measure, real packaging type, and stock.
    fields = ("sku", "barcode", "extra_codes", "status", "is_default", "weight_value", "weight_unit", "package", "stock")
    readonly_fields = ("id", "extra_codes", "wms_stock")
    ADD_PAGE_PRICE_FIELDS = ("base_cost_price", "price", "old_price")

    def get_fields(self, request, obj=None):
        """
        A new product has no variants yet, so the separate Pricing table below has nothing to price: on the add page
        each variant row carries its own cost / selling price / old price (same form, same SetPrice write path).
        On an existing product, prices are edited in the Pricing table (one place, no double writes).
        """
        fields = list(super().get_fields(request, obj))
        if obj is None:
            at = fields.index("stock") if "stock" in fields else len(fields)
            fields[at:at] = [f for f in self.ADD_PAGE_PRICE_FIELDS if f not in fields]
            for f in ("extra_codes", "wms_stock"):
                if f in fields:
                    fields.remove(f)
        elif "stock" in fields:
            # an existing variant's stock is read from the WMS and changed only through Ombor documents
            fields[fields.index("stock")] = "wms_stock"
        return fields

    @admin.display(description="Qoldiq")
    def wms_stock(self, obj) -> str:
        """Sellable units across active locations (on hand − reserved), linking to where they are."""
        if not obj or not obj.pk:
            return "—"
        from django.urls import reverse

        from apps.stores.infrastructure.availability import sellable

        units = sellable([obj.pk]).get(obj.pk)
        return format_html('<a href="{}" title="Qayerda va qancha bor">{} <small>dona</small></a>', reverse("admin:nz_wms_stock_product", args=[obj.pk]), units if units is not None else 0)

    @admin.display(description="Partiya kodlari")
    def extra_codes(self, obj) -> str:
        """Extra (batch) barcodes live on the variant's own page -- one click away from here."""
        if not obj or not obj.pk:
            return mark_safe('<span style="opacity:.6">saqlangandan keyin</span>')
        from django.urls import reverse

        n = obj.extra_barcodes.filter(is_active=True).count()
        url = reverse("admin:products_productvariant_change", args=[obj.pk]) + "#extra_barcodes-group"
        return format_html('<a href="{}" class="nzc-pill" style="--t:#0d9488;text-decoration:none"><i class="fas fa-barcode"></i> {}</a>', url, f"+{n} ta" if n else "Qo'shish")

    def get_extra(self, request, obj=None, **kwargs):
        return 1 if obj is None else 0  # a new product starts with one variant row ready to fill

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "package":
            return _package_formfield(db_field, request, **kwargs)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class ProductPricingInline(admin.TabularInline):
    """
    Real, product-required upgrade: Base/Old/Price used to be columns
    inside the main Variant identity table above -- split into their
    own "Pricing" section instead, so neither table forces horizontal
    scrolling and an editor scanning SKU/Flavor/Stock is never
    distracted by pricing they only occasionally touch here (the
    dedicated Price List dashboard page is the faster, product-name-
    searchable way to do that day to day). Same model, same real
    `ProductVariantAdminForm`/`SetPrice` write path as the identity
    table -- never a second, divergent price source. SKU is shown
    read-only here purely for row identification (it's already
    editable in the Variant table above); this inline can neither add
    nor delete a variant, only price the ones that already exist.
    """

    model = orm.ProductVariant
    form = ProductVariantAdminForm
    verbose_name_plural = _("Pricing")
    extra = 0
    can_delete = False
    fields = ("sku", "base_cost_price", "price", "old_price", "discount_display")
    readonly_fields = ("sku", "discount_display")

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def get_queryset(self, request):
        """ProductVariant itself has no price field (real, confirmed via direct model inspection) -- it lives in the separate pricing bounded context, linked only by a loose product_variant_id UUID, matching Category.image's own cross-app reference pattern. Bulk-loaded here, once per Product's variant set, avoiding N+1 across the small number of variants a single product typically has."""
        from apps.pricing.infrastructure.models import PriceListEntryModel

        qs = super().get_queryset(request)
        variant_ids = list(qs.values_list("id", flat=True))

        self._prices = {}
        for entry in PriceListEntryModel.objects.filter(product_variant_id__in=variant_ids).select_related("price_list").order_by("product_variant_id"):
            self._prices.setdefault(entry.product_variant_id, entry)

        return qs

    def discount_display(self, obj: orm.ProductVariant) -> str:
        """
        Real, product-required addition: the customer-facing discount
        percentage a catalog editor would otherwise have to compute by
        hand from Price/Old Price. Purely a read-only display of the
        same real PriceListEntry.compare_at_price_amount the storefront
        itself already uses to show the crossed-out old price -- never
        a second, independently-calculated discount value. "—" (not
        "0%") whenever there's genuinely no discount to show, matching
        this admin's own established `_direct_thumbnail_html`-style
        convention of never rendering a value that looks real but isn't.
        """
        entry = self._prices.get(obj.id)
        if entry is None or entry.compare_at_price_amount is None or not entry.base_price_amount:
            return "—"
        base, compare = entry.base_price_amount, entry.compare_at_price_amount
        if compare <= base:
            return "—"
        percent_off = round((1 - float(base) / float(compare)) * 100)
        return format_html('<span class="nz-badge nz-badge-danger">-{}%</span>', percent_off)

    discount_display.short_description = _("Discount")


class ProductMediaInlineForm(forms.ModelForm):
    file_upload = forms.FileField(required=False, label="Upload file", help_text="Image (JPEG/PNG/WebP) or video (MP4/MOV/WebM). Runs through the real media pipeline.")

    class Meta:
        model = orm.ProductMedia
        fields = ("media_role", "sort_order", "duration_seconds")


class ProductMediaInline(admin.TabularInline):
    model = orm.ProductMedia
    form = ProductMediaInlineForm
    extra = 0
    max_num = 8  # Real, explicit cap: up to 8 media items per product, per this phase's own requirement.
    fields = ("media_role", "sort_order", "file_upload", "duration_seconds", "preview")
    readonly_fields = ("id", "preview")

    def preview(self, obj: orm.ProductMedia) -> str:
        """Image/video/document preview -- per this phase's explicit Admin requirement. Renders an <img> for image roles, a filename+icon for video/document roles (no inline video/PDF player in the engineering-only admin, per Django Implementation Blueprint §13's 'thin debugging tool' scope -- a full media viewer belongs to the real Admin CRM frontend)."""
        if not obj.pk or not obj.storage_path:
            return "—"
        if obj.media_role in ("primary", "gallery", "nutrition_label", "certificate_scan"):
            return _direct_thumbnail_html(obj.storage_path, obj.thumbnail_paths)
        if obj.media_role == "video":
            return format_html('<i class="fas fa-film" aria-hidden="true"></i> {} ({}s)', obj.storage_path.rsplit("/", 1)[-1], obj.duration_seconds or "?")
        return format_html('<i class="fas fa-file" aria-hidden="true"></i> {}', obj.storage_path.rsplit("/", 1)[-1])

    preview.short_description = "Preview"


def _direct_thumbnail_html(storage_path: str, thumbnail_paths: dict) -> str:
    """
    Media Asset architecture removal (per explicit product decision):
    the direct-file-field replacement for the old _media_asset_thumbnail_html
    helper -- takes an entity's own storage_path/thumbnail_paths fields
    directly, with no ProductMediaAsset FK/lookup involved at all.
    """
    if not storage_path:
        return mark_safe('<div class="nz-thumb nz-thumb-empty"><i class="fas fa-image" aria-hidden="true"></i></div>')
    path = thumbnail_paths.get("small") or storage_path
    url = f"{settings.MEDIA_URL}{path}" if not path.startswith(("http://", "https://")) else path
    return format_html('<img src="{}" class="nz-thumb" alt="">', url)


def _display_name(translations, fallback_id) -> str:
    """
    Real, closed gap: brand_badge/category_badge previously looked up
    only the "en" locale -- if a brand/category had only a "uz"
    translation (the ordinary case for this Uzbekistan-targeted
    project), the list showed a bare UUID instead of a real name.
    Falls back through "uz" -> "en" -> whatever translation exists at
    all, before finally falling back to the id itself (never crashes
    on a translation-less row).
    """
    rows = list(translations)
    for locale in ("uz", "en"):
        match = next((tr for tr in rows if tr.locale_code == locale), None)
        if match:
            return match.name
    return rows[0].name if rows else str(fallback_id)


def _locales_pill(translations) -> str:
    """'3/3 til' -- how many of uz/ru/en carry a name."""
    have = {tr.locale_code for tr in translations if (tr.name or "").strip()}
    n = len(have & {"uz", "ru", "en"})
    return pill(f"{n}/3 til", "#16a34a" if n == 3 else "#f59e0b" if n else "#e11d48", "fa-language")


def _description_of(translations, limit: int = 140) -> str:
    rows = {tr.locale_code: tr for tr in translations}
    tr = rows.get("uz") or rows.get("ru") or rows.get("en")
    text = " ".join((getattr(tr, "description", "") or "").split()) if tr else ""
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


class ProductFlavourInline(admin.TabularInline):
    """
    Real, product-required capability: tags this Product with one or
    more Flavours -- `orm.Product.flavours` explicitly declares
    `through="ProductFlavour"` (see its own docstring), so Django Admin
    (admin.E013) requires this to be edited via the through model's own
    inline rather than a `filter_horizontal` widget on the M2M field
    directly.
    """

    model = orm.ProductFlavour
    extra = 0
    autocomplete_fields = ["flavour"]
    verbose_name = _("Flavour")
    verbose_name_plural = _("Flavours")


_CONTENT_LANGUAGES = (("uz", "🇺🇿 O'zbekcha"), ("ru", "🇷🇺 Русский"), ("en", "🇬🇧 English"))
_CONTENT_PLACEHOLDERS = {
    "supplement_facts": "Serving Size — 5 g\nServings Per Container — 50\nCreatine Monohydrate — 5 g",
    "warnings": "Keep out of reach of children.\nNot intended for persons under 18.",
    "directions": "Mix 1 scoop (5 g) with 250 ml of water or juice.\nTake once daily, preferably after training.",
}


def _content_field_meta(field_name: str) -> tuple[str, str] | None:
    """(language label, placeholder) for one of the 9 per-language content fields, else None."""
    for prefix, placeholder in _CONTENT_PLACEHOLDERS.items():
        for lang, label in _CONTENT_LANGUAGES:
            if field_name == f"{prefix}_text_{lang}":
                return label, placeholder
    return None


from apps.products.infrastructure import catalog_analytics as ca  # noqa: E402
from apps.products.infrastructure.catalog_admin_ui import (  # noqa: E402
    CatalogAnalyticsMixin,
    active_pill,
    kpi,
    pill,
    sales_cell,
    status_pill,
    stock_cell,
    titled,
)


def _product_excel_prepare(objs) -> None:
    from apps.products.infrastructure.selectors import bulk_variant_prices
    from apps.stores.infrastructure import availability

    variants: dict = {}
    for v in orm.ProductVariant.objects.filter(product__in=objs, status="active").values("id", "product_id", "sku", "barcode", "is_default"):
        variants.setdefault(v["product_id"], []).append(v)
    ids = [v["id"] for vs in variants.values() for v in vs]
    prices, stock = bulk_variant_prices(ids), availability.sellable(ids)
    names: dict = {}
    for t in orm.ProductTranslation.objects.filter(product__in=objs).values("product_id", "locale_code", "name"):
        names.setdefault(t["product_id"], {})[t["locale_code"]] = t["name"]
    for p in objs:
        vs = sorted(variants.get(p.id, []), key=lambda v: not v["is_default"])
        default = vs[0] if vs else {}
        price = prices.get(default.get("id"), {})
        n = names.get(p.id, {})
        p.x = {"uz": n.get("uz", ""), "ru": n.get("ru", ""), "en": n.get("en", ""), "sku": default.get("sku", ""), "barcode": default.get("barcode") or "",
               "variants": len(vs), "price": Decimal(price["amount"]) if price.get("amount") else None,
               "old": Decimal(price["compare_at_amount"]) if price.get("compare_at_amount") else None,
               "stock": sum(stock.get(v["id"], 0) for v in vs) if any(v["id"] in stock for v in vs) else None}


@admin.register(orm.Product)
class ProductAdmin(ExcelExportMixin, CatalogFormMixin, CatalogAnalyticsMixin, admin.ModelAdmin):
    excel_title = "Mahsulotlar"
    excel_select_related = ("brand", "category")
    excel_columns = [
        Col("Nomi (uz)", lambda p: p.x["uz"], 40), Col("Nomi (ru)", lambda p: p.x["ru"], 34), Col("Brend", lambda p: str(p.brand) if p.brand else "", 18),
        Col("Kategoriya", lambda p: str(p.category) if p.category else "", 18), Col("Holat", "status", 11), Col("SKU", lambda p: p.x["sku"], 16),
        Col("Shtrix-kod", lambda p: p.x["barcode"], 16), Col("Variantlar", lambda p: p.x["variants"], 10),
        Col("Narx (so'm)", lambda p: p.x["price"], 14, money=True), Col("Eski narx", lambda p: p.x["old"], 13, money=True),
        Col("Qoldiq (dona)", lambda p: p.x["stock"], 12, number=True), Col("Maqsadlar", "goals", 20), Col("Yaratilgan", "created_at", 17),
    ]

    def excel_prepare(self, objs):
        _product_excel_prepare(objs)

    hero_icon, hero_tone, hero_noun = "fa-box", "#10b981", "mahsulot"
    list_display = ("thumbnail_display", "product_col", "status_col", "price_col", "stock_col", "sales_col", "seo_col")
    list_display_links = ("thumbnail_display", "product_col")
    list_filter = (("status", titled("Holat")), ("brand", titled("Brend")), ("category", titled("Kategoriya")))
    analytics_title = "Mahsulotlar"  # Phase 08.3: brand/category filters were a genuine gap -- this phase's own explicit filter requirement
    search_fields = ("translations__name", "variants__sku")
    list_per_page = 25  # Phase 08.3's own explicit default pagination requirement
    # Product has no Meta.ordering (id is a random UUID, not
    # chronological), so without this the change list previously came
    # back in arbitrary DB order despite created_at being a visible column.
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at", "updated_at", "created_by", "updated_by", "version", "specifications_table", "nutrition_table", "stock_by_location")
    exclude = ("specifications", "nutrition_nutrients")  # real, closed gap: these are raw JSON -- specifications_table/nutrition_table render a real, readable preview instead
    inlines = [ProductTranslationInline, ProductVariantInline, ProductPricingInline, ProductFlavourInline, ProductMediaInline]
    autocomplete_fields = ["manufacturer_country"]

    def get_inline_instances(self, request, obj=None):
        """On the add page prices are entered in the variant rows themselves (see ProductVariantInline.get_fields)."""
        return [i for i in super().get_inline_instances(request, obj) if not (obj is None and isinstance(i, ProductPricingInline))]

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        from django.contrib import messages
        from django.urls import reverse

        from apps.pricing.infrastructure.models import PriceListEntryModel

        variants = list(orm.ProductVariant.objects.filter(product=form.instance).values_list("id", "sku"))
        priced = set(PriceListEntryModel.objects.filter(product_variant_id__in=[v for v, _s in variants]).values_list("product_variant_id", flat=True))
        missing = [sku for v, sku in variants if v not in priced]
        if missing:
            messages.warning(request, format_html(
                '{} <b>{}</b>. {} <a href="{}?q={}">{}</a>',
                _("No selling price yet for:"), ", ".join(missing), _("Customers can't buy a variant without a price -- set it in the Pricing table or"),
                reverse("admin:nz_price_list"), missing[0], _("the price list"),
            ))
    actions = ["publish_selected", "hide_selected", "archive_selected", "restore_selected", "delete_selected_via_service"]

    # Real, product-required organization: one semantic <fieldset> per
    # content type -- Supplement Facts, Warnings, Directions -- each with
    # its three language versions side by side (uz / ru / en), instead of
    # one collapsed block per language that made an editor open three
    # sections to compare a single translation. The "nz-fieldset" class
    # opts a group into the <fieldset>/<legend> renderer in
    # templates/admin/includes/fieldset.html.
    fieldsets = (
        (_("Basic Information"), {"fields": ("brand", "category", "status", "goals")}),
        (_("Manufacturing"), {"fields": ("manufacturer", "manufacturer_country", "expire_date")}),
        (
            _("Supplement Facts"),
            {
                "classes": ("nz-fieldset", "nz-fieldset--facts"),
                "description": _("One fact per line in the form <code>Label — value</code> (e.g. <code>Protein — 24 g</code>). The storefront turns these lines into the Supplement Facts table."),
                "fields": ("supplement_facts_text_uz", "supplement_facts_text_ru", "supplement_facts_text_en"),
            },
        ),
        (
            _("Warnings"),
            {
                "classes": ("nz-fieldset", "nz-fieldset--warnings"),
                "description": _("Safety notes shown to the customer — one per line."),
                "fields": ("warnings_text_uz", "warnings_text_ru", "warnings_text_en"),
            },
        ),
        (
            _("Directions"),
            {
                "classes": ("nz-fieldset", "nz-fieldset--directions"),
                "description": _("How to use the product — dosage, timing, mixing. One step per line."),
                "fields": ("directions_text_uz", "directions_text_ru", "directions_text_en"),
            },
        ),
        (
            "Porsiya",
            {
                "classes": ("nz-fieldset",),
                "description": "Mijozga «bir porsiya narxi»ni ko'rsatadi (solishtirish sahifasi) va xarid qachon tugashini hisoblab, "
                               "o'z vaqtida «qayta buyurtma» eslatmasini yuboradi. Qadoqdagi «Serving size» / «Servings per container» qatorlaridan oling.",
                "fields": ("nutrition_serving_size_grams", "nutrition_servings_per_container", "nutrition_calories"),
            },
        ),
        ("Ombordagi qoldiq", {"classes": ("nzp-stock-fs",), "fields": ("stock_by_location",)}),
        (_("Specifications & Nutrition"), {"classes": ("nzp-fold",), "fields": ("specifications_table", "nutrition_table")}),
        (_("Record Metadata"), {"classes": ("nzp-fold",), "fields": ("id", "created_at", "updated_at", "created_by", "updated_by", "version")}),
    )

    class Media:
        css = {"all": ("admin/css/nz-product-content.css",)}

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """
        Inside a content-type fieldset every field only needs its language
        as a label. Placeholders show the exact one-fact-per-line
        "Label — value" shape the storefront's parse-key-value-text.ts
        re-flows into a table -- a format hint, never saved as a value.
        """
        if db_field.name == "goals":  # "shop by goal": tick the training goals this product serves
            from apps.products.infrastructure.goals import CHOICES

            return forms.MultipleChoiceField(
                choices=CHOICES, required=False, widget=forms.CheckboxSelectMultiple(attrs={"class": "nz-goal-choices"}), label=_("Goals"),
                help_text=_("Which training goals this product serves -- it then appears under those goal cards on the home page and in the catalog's goal filter."),
            )
        serving = {
            "nutrition_serving_size_grams": ("Bir porsiya (gramm)", "30"),
            "nutrition_servings_per_container": ("Qadoqdagi porsiyalar soni", "74"),
            "nutrition_calories": ("Bir porsiya kaloriyasi (kkal)", "120"),
        }.get(db_field.name)
        if serving is not None:
            field = super().formfield_for_dbfield(db_field, request, **kwargs)
            if field is not None:
                field.label = serving[0]
                field.widget.attrs.update({"placeholder": serving[1], "min": "0", "inputmode": "decimal"})
            return field
        meta = _content_field_meta(db_field.name)
        if meta is not None:
            label, placeholder = meta
            lang = db_field.name.rsplit("_", 1)[-1]
            kwargs["widget"] = forms.Textarea(
                attrs={"rows": 8, "placeholder": placeholder, "lang": lang, "spellcheck": "true", "class": "vLargeTextField nz-content-textarea"}
            )
            field = super().formfield_for_dbfield(db_field, request, **kwargs)
            if field is not None:
                field.label = label
            return field
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def form_hero(self, request, obj):
        if obj is None:
            return {}
        from django.urls import reverse

        from apps.pricing.infrastructure.models import PriceListEntryModel

        snap = ca.snapshot(30)
        trs = list(obj.translations.all())
        variants = list(obj.variants.all())
        primary = next((m for m in obj.media.all() if m.media_role == "primary"), None)
        rep = next((v for v in variants if v.is_default), variants[0] if variants else None)
        prices = {e.product_variant_id: e for e in PriceListEntryModel.objects.filter(product_variant_id__in=[v.id for v in variants], price_list__status="active")}
        entry = prices.get(rep.id) if rep else None
        unpriced = sum(1 for v in variants if v.id not in prices)
        amounts = sorted(e.base_price_amount for e in prices.values())
        if not amounts:
            price = stat("Narx", "—", "#e11d48", "narx qo'yilmagan", "fa-tag")
        else:
            value = f"{ca.money(amounts[0])} so'm" if amounts[0] == amounts[-1] else f"{ca.compact(amounts[0])}–{ca.compact(amounts[-1])}"
            sub = f"{unpriced} variant narxsiz" if unpriced else (f"eski: {ca.money(entry.compare_at_price_amount)}" if entry and entry.compare_at_price_amount else "barcha variantlar narxlangan")
            price = stat("Narx", value, "#f59e0b" if unpriced else "#10b981", sub, "fa-tag")
        on_hand = snap.product_stock.get(obj.id, 0)
        seo = "To'liq" if obj.seo_meta_title and obj.seo_meta_description else "Chala" if (obj.seo_meta_title or obj.seo_meta_description) else "Yo'q"
        brand = _display_name(obj.brand.translations.all(), obj.brand_id) if obj.brand_id else "Brendsiz"
        category = _display_name(obj.category.translations.all(), obj.category_id) if obj.category_id else "Kategoriyasiz"
        slug = next((t.slug for t in sorted(trs, key=lambda t: ("uz", "ru", "en").index(t.locale_code) if t.locale_code in ("uz", "ru", "en") else 9)), "")
        site = storefront_url(f"/products/{slug}") if slug and obj.status == "published" else ""
        return {
            "title": _display_name(trs, obj.id), "subtitle": f"{brand} · {category}",
            "image": media_url(primary.storage_path, primary.thumbnail_paths) if primary else "",
            "chips": [
                status_pill(obj.status), _locales_pill(trs), pill(f"{len(variants)} variant", "#3b82f6", "fa-layer-group"),
                pill(f"{len(obj.media.all())} media", "#8b5cf6", "fa-images"),
                pill(f"SEO: {seo}", {"To'liq": "#16a34a", "Chala": "#f59e0b"}.get(seo, "#e11d48"), "fa-magnifying-glass"),
            ],
            "stats": [
                price,
                stat("Qoldiq", f"{on_hand} dona", "#e11d48" if on_hand <= 0 else "#f59e0b" if on_hand < 10 else "#16a34a", "barcha filial va omborlar", "fa-cubes"),
                sales_stat(snap.product_sales.get(obj.id)),
                stat("Variantlar", len(variants), "#3b82f6", f"asosiy: {rep.sku}" if rep else "variant yo'q", "fa-layer-group"),
            ],
            "links": [l for l in (
                {"label": "Saytda ko'rish", "url": site, "icon": "fa-arrow-up-right-from-square", "external": True, "primary": True} if site else None,
                {"label": "Qayerda bor", "url": reverse("admin:nz_wms_stock_product", args=[rep.pk]), "icon": "fa-map-location-dot"} if rep else None,
                {"label": "Narxlar", "url": reverse("admin:nz_price_list") + (f"?q={rep.sku}" if rep else ""), "icon": "fa-tags"},
            ) if l],
        }

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        return [fs for fs in fieldsets if obj is not None or "stock_by_location" not in fs[1]["fields"]]

    @admin.display(description="Filiallar bo'yicha")
    def stock_by_location(self, obj: orm.Product) -> str:
        """Variant x location table of available units (StoreProductStock, the WMS truth) -- each row opens the variant's stock page."""
        from django.urls import reverse

        from apps.stores.infrastructure import transfer_service
        from apps.stores.infrastructure.models import StoreProductStock

        variants = list(obj.variants.all().order_by("-is_default", "sku"))
        if not variants:
            return mark_safe('<span class="nzc-muted">Variant yo\'q</span>')
        locations = list(transfer_service.locations())
        grid = {(r.product_variant_id, r.store_id): r for r in StoreProductStock.objects.filter(product_variant__in=variants)}
        head = "".join(format_html('<th><i style="background:{}"></i>{}<small>{}</small></th>', s.color or "#94a3b8", s.name, "Sklad" if s.kind == "warehouse" else "Filial") for s in locations)
        body = []
        for v in variants:
            cells, total = [], 0
            for s in locations:
                r = grid.get((v.id, s.id))
                avail = (r.quantity - r.reserved_quantity) if r else 0
                total += avail
                tone = "zero" if avail <= 0 else "low" if avail <= 5 else "ok"
                res = format_html("<small>+{} band</small>", r.reserved_quantity) if r and r.reserved_quantity else ""
                cells.append(format_html('<td class="{}"><b>{}</b>{}</td>', tone, avail, res))
            size = f" · {v.weight_value:g} {v.weight_unit}" if v.weight_value is not None else ""
            url = reverse("admin:nz_wms_stock_product", args=[v.pk])
            body.append(format_html('<tr><td class="v"><a href="{}"><code>{}</code>{}</a></td>{}<td class="t"><b>{}</b></td><td class="a"><a href="{}" class="nzc-pill" style="--t:#10b981"><i class="fas fa-map-location-dot"></i> Batafsil</a></td></tr>',
                                    url, v.sku, size, mark_safe("".join(cells)), total, url))
        return format_html('<div class="nzp-stock"><table><thead><tr><th>Variant</th>{}<th>Jami</th><th></th></tr></thead><tbody>{}</tbody></table>'
                           '<p>Raqam — sotuvga mavjud dona (band qilinganlar ayirilgan). Qoldiq faqat ombor hujjatlari orqali o\'zgaradi: '
                           '<a href="{}">Kirim</a> · <a href="{}">Transfer</a> · <a href="{}">Inventarizatsiya</a>.</p></div>',
                           mark_safe(head), mark_safe("".join(body)), reverse("admin:stores_stockreceipt_new"), reverse("admin:stores_stocktransfer_new"), reverse("admin:stores_stockcount_new"))

    def specifications_table(self, obj: orm.Product) -> str:
        """Real, closed gap: `specifications` is a raw JSON list -- shown here as a real, readable table instead of an editable JSON textarea a manager could easily corrupt (e.g. a malformed dict crashing every future read of this product)."""
        specs = obj.specifications or []
        if not specs:
            return "No specifications recorded."
        rows = "".join(format_html("<tr><td>{}</td><td>{}</td></tr>", spec.get("key", ""), spec.get("value", "")) for spec in specs)
        return format_html('<table class="nz-settings-table"><thead><tr><th>Key</th><th>Value</th></tr></thead><tbody>{}</tbody></table>', mark_safe(rows))

    specifications_table.short_description = "Specifications"

    def nutrition_table(self, obj: orm.Product) -> str:
        """Real, closed gap: `nutrition_nutrients` is a raw JSON dict -- same rationale as specifications_table above."""
        nutrients = obj.nutrition_nutrients or {}
        if not nutrients:
            return "No nutrition facts recorded."
        rows = "".join(format_html("<tr><td>{}</td><td>{}</td></tr>", key, value) for key, value in nutrients.items())
        return format_html('<table class="nz-settings-table"><thead><tr><th>Nutrient</th><th>Amount</th></tr></thead><tbody>{}</tbody></table>', mark_safe(rows))

    nutrition_table.short_description = "Nutrition Facts"

    def get_queryset(self, request):
        from apps.pricing.infrastructure.models import PriceListEntryModel

        qs = super().get_queryset(request).prefetch_related("translations", "variants", "media", "brand__translations", "category__translations")

        # Phase B3: same rationale as ProductVariantInline above --
        # picks the is_default variant (or the first variant, if none
        # is marked default) to represent the product's price/stock
        # in the list view, since a Product may have multiple
        # variants with different prices/stock levels.
        variant_ids = []
        self._representative_variant = {}
        for product in qs:
            variants = list(product.variants.all())
            if not variants:
                continue
            representative = next((v for v in variants if v.is_default), variants[0])
            self._representative_variant[product.id] = representative.id
            variant_ids.append(representative.id)

        self._prices = {}
        for entry in PriceListEntryModel.objects.filter(product_variant_id__in=variant_ids).select_related("price_list").order_by("product_variant_id"):
            self._prices.setdefault(entry.product_variant_id, entry)

        from apps.stores.infrastructure.availability import sellable

        self._stock = sellable(variant_ids)  # the WMS stock (on hand − reserved at active locations)

        return qs

    def save_formset(self, request, form, formset, change):
        if formset.model is not orm.ProductMedia:
            super().save_formset(request, form, formset, change)
            return

        from apps.products.infrastructure.composition import build_upload_image, build_upload_video

        instances = formset.save(commit=False)
        for deleted in formset.deleted_objects:
            deleted.delete()

        for instance in instances:
            matching_form = next(f for f in formset.forms if f.instance == instance)
            uploaded = matching_form.cleaned_data.get("file_upload")
            if uploaded:
                content = uploaded.read()
                if instance.media_role == "video":
                    build_upload_video().execute(product_id=form.instance.id, filename=uploaded.name, content=content, mime_type=uploaded.content_type, duration_seconds=instance.duration_seconds or 0, variant_id=instance.variant_id)
                else:
                    build_upload_image().execute(product_id=form.instance.id, filename=uploaded.name, content=content, mime_type=uploaded.content_type, media_role=instance.media_role, variant_id=instance.variant_id)
                # The Application Service above already persisted the real ProductMedia via the domain repository -- this ORM instance (created only because the inline form required a value) must not also be saved, or a duplicate/invalid row would result.
            else:
                instance.save()
        formset.save_m2m()

    def analytics(self, request, snap):
        from collections import Counter

        qs = orm.Product.objects.all()
        total = qs.count()
        published = qs.filter(status="published").count()
        hidden = qs.exclude(status="published").count()
        pub_ids = set(qs.filter(status="published").values_list("id", flat=True))
        out_of_stock = sum(1 for pid in pub_ids if snap.product_stock.get(pid, 0) <= 0)
        names = {}
        live = set(orm.Product.objects.values_list("id", flat=True))
        for tr in orm.ProductTranslation.objects.values("product_id", "locale_code", "name"):
            if tr["locale_code"] == "uz" or tr["product_id"] not in names:
                names[tr["product_id"]] = tr["name"] + ("" if tr["product_id"] in live else " (o'chirilgan)")
        by_cat = Counter()
        cat_names = {c.id: _display_name(c.translations.all(), c.id) for c in orm.Category.objects.prefetch_related("translations")}
        for cid in qs.values_list("category_id", flat=True):
            by_cat[cat_names.get(cid, "Kategoriyasiz")] += 1
        rank = ca.ranking([(names.get(pid, "—"), n, ca.PALETTE[i % len(ca.PALETTE)]) for i, (pid, n) in enumerate(snap.product_sales.items())])
        for i, r in enumerate(rank):
            r["color"] = ca.PALETTE[i]
        return {
            "kpis": [
                kpi("Jami mahsulot", total, "fa-box", "#2563eb", f"{sum(1 for _ in orm.ProductVariant.objects.values('id'))} ta variant"),
                kpi("Sotuvda", published, "fa-store", "#16a34a", f"{round(published * 100 / total) if total else 0}% katalog"),
                kpi("Yashirin / qoralama", hidden, "fa-eye-slash", "#64748b", "saytda ko'rinmaydi"),
                kpi("Tugagan", out_of_stock, "fa-triangle-exclamation", "#e11d48" if out_of_stock else "#16a34a", "sotuvdagi, qoldig'i 0"),
                kpi("30 kunlik tushum", ca.compact(snap.total.revenue), "fa-sack-dollar", "#f59e0b", "so'm · POS + onlayn", snap.total.change_pct),
                kpi("Sotilgan", f"{snap.total.units} dona", "fa-cart-shopping", "#8b5cf6", "so'nggi 30 kun"),
            ],
            "ranking_title": "Eng ko'p sotilgan mahsulotlar", "ranking": {"rows": rank},
            "donut_title": "Kategoriyalar bo'yicha", "donut": ca.donut(list(by_cat.items())), "donut_unit": "mahsulot",
        }

    @admin.display(description="Mahsulot", ordering="created_at")
    def product_col(self, obj: orm.Product) -> str:
        name = _display_name(obj.translations.all(), obj.id)
        brand = _display_name(obj.brand.translations.all(), obj.brand_id) if obj.brand else "Brendsiz"
        category = _display_name(obj.category.translations.all(), obj.category_id) if obj.category else "Kategoriyasiz"
        variants = len(obj.variants.all())
        return format_html('<div class="nzc-name"><b>{}</b><small>{} · {} · {} variant</small></div>', name, brand, category, variants)

    @admin.display(description="Holat", ordering="status")
    def status_col(self, obj: orm.Product) -> str:
        return status_pill(obj.status)

    @admin.display(description="Narx")
    def price_col(self, obj: orm.Product) -> str:
        # A button: opens the quick price editor (every variant: cost, price, old price, margin) -- nutrizone-price-quick.js.
        variant_id = self._representative_variant.get(obj.id)
        entry = self._prices.get(variant_id) if variant_id else None
        if entry is None:
            return format_html('<button type="button" class="nzq-cell nzq-empty" data-nzq="{}" title="Narx qo\'yish"><i class="fas fa-tag"></i> Narx qo\'yish</button>', obj.id)
        raw = f"{entry.base_price_amount:f}".rstrip("0").rstrip(".")
        return format_html('<button type="button" class="nzq-cell nzc-price" data-nzq="{}" data-variant="{}" data-price="{}" title="Narxni tahrirlash"><b>{}</b> <small>{}</small><i class="fas fa-pen"></i></button>',
                           obj.id, variant_id, raw, ca.money(entry.base_price_amount), "so'm" if entry.price_list.currency == "UZS" else entry.price_list.currency)

    @admin.display(description="Qoldiq")
    def stock_col(self, obj: orm.Product) -> str:
        if obj.id in self.snap.product_stock:
            return stock_cell(self.snap.product_stock[obj.id])
        variant_id = self._representative_variant.get(obj.id)
        return stock_cell(self._stock.get(variant_id) if variant_id else None)

    @admin.display(description="30 kunlik savdo")
    def sales_col(self, obj: orm.Product) -> str:
        return sales_cell(self.snap.product_sales.get(obj.id))

    @admin.display(description="SEO")
    def seo_col(self, obj: orm.Product) -> str:
        if obj.seo_meta_title and obj.seo_meta_description:
            return mark_safe('<span class="nzc-seo" style="--t:#16a34a"><i></i>To\'liq</span>')
        if obj.seo_meta_title or obj.seo_meta_description:
            return mark_safe('<span class="nzc-seo" style="--t:#f59e0b"><i></i>Chala</span>')
        return mark_safe('<span class="nzc-seo" style="--t:#e11d48"><i></i>Yo\'q</span>')

    def price_display(self, obj: orm.Product) -> str:
        variant_id = self._representative_variant.get(obj.id)
        entry = self._prices.get(variant_id) if variant_id else None
        return f"{entry.base_price_amount} {entry.price_list.currency}" if entry else "—"

    price_display.short_description = "Price"

    def stock_display(self, obj: orm.Product) -> str:
        variant_id = self._representative_variant.get(obj.id)
        quantity = self._stock.get(variant_id) if variant_id else None
        return "—" if quantity is None else str(quantity)

    stock_display.short_description = "Stock"

    def thumbnail_display(self, obj: orm.Product) -> str:
        primary = next((m for m in obj.media.all() if m.media_role == "primary"), None)
        return _direct_thumbnail_html(primary.storage_path if primary else "", primary.thumbnail_paths if primary else {})

    thumbnail_display.short_description = ""

    def name_display(self, obj: orm.Product) -> str:
        t = next((tr for tr in obj.translations.all() if tr.locale_code == "en"), None)
        return t.name if t else str(obj.id)

    name_display.short_description = "Name"

    def status_badge(self, obj: orm.Product) -> str:
        tones = {"draft": "neutral", "pending_review": "warning", "published": "success", "unpublished": "warning", "archived": "danger"}
        return format_html('<span class="nz-badge nz-badge-{}">{}</span>', tones.get(obj.status, "neutral"), obj.status)

    status_badge.short_description = "Status"

    def brand_badge(self, obj: orm.Product) -> str:
        if not obj.brand:
            return "—"
        return _display_name(obj.brand.translations.all(), obj.brand_id)

    brand_badge.short_description = "Brand"

    def category_badge(self, obj: orm.Product) -> str:
        if not obj.category:
            return "—"
        return _display_name(obj.category.translations.all(), obj.category_id)

    category_badge.short_description = "Category"

    def variant_count(self, obj: orm.Product) -> int:
        return obj.variants.count()

    variant_count.short_description = "Variants"

    def media_count(self, obj: orm.Product) -> int:
        return obj.media.count()

    media_count.short_description = "Media"

    def nutrition_preview(self, obj: orm.Product) -> str:
        if obj.nutrition_calories is None:
            return "—"
        return f"{obj.nutrition_calories:.0f} kcal"

    nutrition_preview.short_description = "Nutrition"

    def seo_status_badge(self, obj: orm.Product) -> str:
        if obj.seo_meta_title and obj.seo_meta_description:
            return format_html('<span class="nz-badge nz-badge-success">{}</span>', "complete")
        if obj.seo_meta_title or obj.seo_meta_description:
            return format_html('<span class="nz-badge nz-badge-warning">{}</span>', "incomplete")
        return format_html('<span class="nz-badge nz-badge-danger">{}</span>', "missing")

    seo_status_badge.short_description = "SEO"

    @admin.action(description="Publish selected products")
    def publish_selected(self, request, queryset):
        service = PublishProduct(DjangoProductRepository(), DjangoCategoryRepository(), _admin_ctx(request))
        for product in queryset:
            try:
                service.execute(product.id)
            except Exception:  # noqa: BLE001 - a bulk action reports failures via the admin messages framework, not by crashing the whole batch
                self.message_user(request, f"Could not publish {product.id}: publish validation failed.", level="error")

    @admin.action(description="Hide selected products")
    def hide_selected(self, request, queryset):
        service = HideProduct(DjangoProductRepository(), _admin_ctx(request))
        for product in queryset:
            try:
                service.execute(product.id)
            except Exception:  # noqa: BLE001
                pass

    @admin.action(description="Archive selected products")
    def archive_selected(self, request, queryset):
        service = ArchiveProduct(DjangoProductRepository(), _admin_ctx(request))
        for product in queryset:
            try:
                service.execute(product.id)
            except Exception:  # noqa: BLE001
                pass

    @admin.action(description="Restore selected products")
    def restore_selected(self, request, queryset):
        service = RestoreProduct(DjangoProductRepository(), _admin_ctx(request))
        for product in queryset:
            try:
                service.execute(product.id)
            except Exception:  # noqa: BLE001
                pass

    @admin.action(description="Delete selected products (must already be archived)")
    def delete_selected_via_service(self, request, queryset):
        service = DeleteProduct(DjangoProductRepository(), _admin_ctx(request))
        for product in queryset:
            try:
                service.execute(product.id)
            except Exception:  # noqa: BLE001
                self.message_user(request, f"Could not delete {product.id}: it must be archived first.", level="error")

    def get_actions(self, request):
        """
        Removes Django's built-in `delete_selected` (a raw
        `queryset.delete()` that would bypass `DeleteProduct`'s
        business rule requiring ARCHIVED status first, per MIC §9's
        "bulk actions MUST call Application Services" rule) --
        `delete_selected_via_service` above is the only bulk-delete
        path this admin offers.
        """
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions


class ProductVariantBarcodeForm(forms.ModelForm):
    class Meta:
        model = orm.ProductVariantBarcode
        fields = ("barcode", "batch", "expires_at", "note", "is_active")
        widgets = {"expires_at": forms.DateInput(attrs={"type": "date"}), "barcode": forms.TextInput(attrs={"placeholder": "4780012345678", "autocomplete": "off", "inputmode": "numeric"})}

    def clean_barcode(self):
        from apps.products.infrastructure import barcodes

        code = barcodes.normalize(self.cleaned_data.get("barcode"))
        if not barcodes.CODE_RE.match(code):
            raise forms.ValidationError("Shtrix-kod 4–32 ta harf/raqamdan iborat bo'lishi kerak.")
        owner = barcodes.owner_of(code, exclude_extra_id=self.instance.pk)
        variant_id = self.instance.variant_id or getattr(getattr(self, "parent_variant", None), "pk", None)
        if owner is not None and owner.pk != variant_id:
            raise forms.ValidationError(f"Bu shtrix-kod boshqa mahsulotda ishlatilgan ({owner.sku}).")
        if owner is not None and owner.pk == variant_id and owner.barcode == code:
            raise forms.ValidationError("Bu — variantning asosiy shtrix-kodi.")
        return code


class ProductVariantBarcodeInline(admin.TabularInline):
    """Several barcodes for one product: every batch (partiya) may arrive with its own label."""

    model = orm.ProductVariantBarcode
    form = ProductVariantBarcodeForm
    extra = 1
    verbose_name = "Qo'shimcha shtrix-kod"
    verbose_name_plural = "Qo'shimcha shtrix-kodlar (partiyalar)"
    fields = ("barcode", "batch", "expires_at", "note", "is_active")


class ProductVariantPageForm(ProductVariantAdminForm):
    """The variant's own page: the inline form's SKU/barcode validation and SetPrice write path, with Uzbek labels.
    Stock is not edited here -- it moves only through the warehouse (Kirim / transfer / inventarizatsiya)."""

    LABELS = {
        "product": ("Mahsulot", ""), "sku": ("SKU", "Ichki artikul: KATTA lotin harflari, raqam va chiziqcha (masalan AN-CREA-250)."),
        "barcode": ("Asosiy shtrix-kod", "EAN-8 / EAN-13 / UPC — nazorat raqami tekshiriladi. Partiyalarning boshqa kodlari pastda."),
        "status": ("Holat", ""), "is_default": ("Asosiy variant", "Mahsulot kartochkasida birinchi bo'lib tanlangan turadi."),
        "weight_value": ("Hajm / og'irlik", ""), "weight_unit": ("O'lchov birligi", ""), "package": ("Qadoq turi", ""),
        "base_cost_price": ("Tannarx", "Faqat ichki — mijozga ko'rinmaydi."), "price": ("Sotuv narxi", "Asosiy narx ro'yxatiga yoziladi (narx tarixi saqlanadi)."),
        "old_price": ("Eski narx (chizilgan)", "Ixtiyoriy. Sotuv narxidan katta bo'lsa saytda chizib ko'rsatiladi."),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, (label, help_text) in self.LABELS.items():
            if name in self.fields:
                self.fields[name].label = label
                if help_text:
                    self.fields[name].help_text = help_text
        self.fields.pop("stock", None)


@admin.register(orm.ProductVariant)
class ProductVariantAdmin(CatalogFormMixin, CatalogAnalyticsMixin, admin.ModelAdmin):
    """
    Phase 08.3: standalone "Variants Workspace" -- previously only
    available as an inline on ProductAdmin, not as its own list view.

    No price column: ProductVariant has no price field (confirmed by
    direct model inspection) -- pricing lives in the separate Pricing
    bounded context, out of this phase's own explicit scope
    (Products/Categories/Brands/Flavours/Variants only). Displaying
    it here would mean either fabricating a field or reaching across
    a bounded-context boundary this phase wasn't scoped to cross.
    """

    list_display = ("variant_col", "product_col", "status_col", "size_col", "stock_col", "sales_col")
    list_display_links = ("variant_col",)
    inlines = [ProductVariantBarcodeInline]
    list_filter = (("status", titled("Holat")), ("is_default", titled("Asosiy variant")), ("weight_unit", titled("O'lchov birligi")), ("package", titled("Qadoq")))
    analytics_title = "Mahsulot variantlari"
    search_fields = ("sku", "barcode", "extra_barcodes__barcode", "product__translations__name")
    list_per_page = 25
    readonly_fields = ("id", "created_at", "updated_at")
    autocomplete_fields = ["product"]
    form = ProductVariantPageForm

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "package":
            return _package_formfield(db_field, request, **kwargs)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    hero_icon, hero_tone, hero_noun = "fa-layer-group", "#3b82f6", "variant"
    fieldsets = (
        ("Identifikatsiya", {"fields": ("product", "sku", "barcode", "status", "is_default")}),
        ("Hajm va qadoq", {"fields": (("weight_value", "weight_unit"), "package")}),
        ("Narx", {"fields": ("base_cost_price", "price", "old_price")}),
        ("Tizim ma'lumotlari", {"classes": ("nzp-fold",), "fields": ("id", "created_at", "updated_at")}),
    )

    def form_hero(self, request, obj):
        if obj is None:
            return {}
        from django.urls import reverse

        snap = ca.snapshot(30)
        product = obj.product
        primary = product.media.filter(media_role="primary").first()
        entry = _default_price_entry_for(obj.id)
        on_hand, reserved = snap.variant_stock.get(obj.id, (0, 0))
        price_stat = stat("Sotuv narxi", "—", "#e11d48", "narx qo'yilmagan", "fa-tag")
        margin_stat = stat("Marja", "—", "#64748b", "tannarx kiritilmagan", "fa-percent")
        if entry is not None:
            old = f"eski: {ca.money(entry.compare_at_price_amount)}" if entry.compare_at_price_amount else "chegirmasiz"
            price_stat = stat("Sotuv narxi", f"{ca.money(entry.base_price_amount)} so'm", "#10b981", old, "fa-tag")
            if entry.cost_price_amount and entry.base_price_amount:
                m = round((float(entry.base_price_amount) - float(entry.cost_price_amount)) * 100 / float(entry.base_price_amount))
                margin_stat = stat("Marja", f"{m}%", "#16a34a" if m >= 20 else "#f59e0b" if m >= 0 else "#e11d48",
                                   f"tannarx {ca.money(entry.cost_price_amount)}", "fa-percent")
        weight = f"{obj.weight_value:g} {obj.weight_unit}" if obj.weight_value is not None else ""
        chips = [status_pill(obj.status)]
        if obj.is_default:
            chips.append(pill("Asosiy variant", "#f59e0b", "fa-star"))
        if obj.package_id:
            chips.append(pill(str(obj.package), "#10b981", "fa-box-open"))
        chips.append(pill(obj.barcode, "#64748b", "fa-barcode") if obj.barcode else pill("Shtrix-kod yo'q", "#f97316", "fa-barcode"))
        return {
            "title": f"{_display_name(product.translations.all(), product.id)}{' · ' + weight if weight else ''}", "subtitle": f"SKU {obj.sku}",
            "image": media_url(primary.storage_path, primary.thumbnail_paths) if primary else "", "chips": chips,
            "stats": [
                price_stat, margin_stat,
                stat("Qoldiq", f"{on_hand} dona", "#e11d48" if on_hand <= 0 else "#f59e0b" if on_hand < 10 else "#16a34a", f"{reserved} band" if reserved else "barcha filial va omborlar", "fa-cubes"),
                sales_stat(snap.variant_sales.get(obj.id)),
            ],
            "links": [
                {"label": "Mahsulotga o'tish", "url": reverse("admin:products_product_change", args=[product.id]), "icon": "fa-box", "primary": True},
                {"label": "Qayerda bor", "url": reverse("admin:nz_wms_stock_product", args=[obj.pk]), "icon": "fa-map-location-dot"},
                {"label": "Narxlar ro'yxati", "url": reverse("admin:nz_price_list") + f"?q={obj.sku}", "icon": "fa-list"},
            ],
        }

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("product", "package").prefetch_related("product__translations", "extra_barcodes")

    def analytics(self, request, snap):
        qs = orm.ProductVariant.objects.all()
        total = qs.count()
        active = qs.filter(status="active").count()
        no_barcode = qs.filter(barcode__isnull=True).count() + qs.filter(barcode="").count()
        ids = list(qs.values_list("id", flat=True))
        on_hand = sum(snap.variant_stock.get(v, (0, 0))[0] for v in ids)
        reserved = sum(snap.variant_stock.get(v, (0, 0))[1] for v in ids)
        out = sum(1 for v in ids if snap.variant_stock.get(v, (0, 0))[0] <= 0)
        low = sum(1 for v in ids if 0 < snap.variant_stock.get(v, (0, 0))[0] < 10)
        labels = {}
        for v in qs.select_related("product").prefetch_related("product__translations"):
            labels[v.id] = f"{_display_name(v.product.translations.all(), v.product_id)} · {v.sku}"
        rank = ca.ranking([(labels.get(vid, "—"), n, "") for vid, n in snap.variant_sales.items()])
        for i, r in enumerate(rank):
            r["color"] = ca.PALETTE[i]
        return {
            "kpis": [
                kpi("Jami variant", total, "fa-layer-group", "#2563eb", f"{active} faol"),
                kpi("Omborda", f"{on_hand} dona", "fa-cubes", "#16a34a", "filiallar + omborlar"),
                kpi("Band qilingan", f"{reserved} dona", "fa-lock", "#8b5cf6", "transfer / buyurtmalarda"),
                kpi("Tugagan", out, "fa-circle-xmark", "#e11d48" if out else "#16a34a", "qoldig'i 0"),
                kpi("Kam qolgan", low, "fa-battery-quarter", "#f59e0b", "10 donadan kam"),
                kpi("Shtrix-kodsiz", no_barcode, "fa-barcode", "#f97316" if no_barcode else "#16a34a", "skaner bilan topilmaydi"),
            ],
            "ranking_title": "Eng ko'p sotilgan variantlar", "ranking": {"rows": rank},
            "donut_title": "Qoldiq holati", "donut_unit": "variant",
            "donut": ca.donut([("Yetarli", total - out - low), ("Kam qolgan", low), ("Tugagan", out)]),
        }

    @admin.display(description="Variant", ordering="sku")
    def variant_col(self, obj: orm.ProductVariant) -> str:
        star = mark_safe(' <i class="fas fa-star" style="color:#f59e0b" title="Asosiy variant"></i>') if obj.is_default else ""
        barcode = format_html('<i class="fas fa-barcode"></i> {}', obj.barcode) if obj.barcode else mark_safe('<span style="color:#f97316">shtrix-kod yo\'q</span>')
        extra = [b for b in obj.extra_barcodes.all() if b.is_active]
        more = format_html(' <span class="nzc-pill" style="--t:#0d9488" title="{}">+{} partiya kodi</span>', ", ".join(b.barcode for b in extra), len(extra)) if extra else ""
        return format_html('<div class="nzc-name"><b><code>{}</code>{}</b><small>{}{}</small></div>', obj.sku, star, barcode, more)

    @admin.display(description="Mahsulot")
    def product_col(self, obj: orm.ProductVariant) -> str:
        return _display_name(obj.product.translations.all(), obj.product_id)

    @admin.display(description="Holat", ordering="status")
    def status_col(self, obj: orm.ProductVariant) -> str:
        return status_pill(obj.status)

    @admin.display(description="Hajm / qadoq")
    def size_col(self, obj: orm.ProductVariant) -> str:
        weight = f"{obj.weight_value:g} {obj.weight_unit}" if obj.weight_value is not None else "—"
        return format_html('<div class="nzc-name"><b>{}</b><small>{}</small></div>', weight, obj.package or "qadoqsiz")

    @admin.display(description="Qoldiq")
    def stock_col(self, obj: orm.ProductVariant) -> str:
        on_hand, reserved = self.snap.variant_stock.get(obj.id, (None, 0))
        return stock_cell(on_hand, reserved)

    @admin.display(description="30 kunlik savdo")
    def sales_col(self, obj: orm.ProductVariant) -> str:
        return sales_cell(self.snap.variant_sales.get(obj.id))

    def product_name(self, obj: orm.ProductVariant) -> str:
        t = next((tr for tr in obj.product.translations.all() if tr.locale_code == "en"), None)
        return t.name if t else str(obj.product_id)

    product_name.short_description = "Product"

    def weight_display(self, obj: orm.ProductVariant) -> str:
        if obj.weight_value is None:
            return "—"
        return f"{obj.weight_value:g} {obj.weight_unit}"

    weight_display.short_description = "Weight"


class BrandTranslationInline(TranslationInlineMixin, admin.StackedInline):
    model = orm.BrandTranslation
    fields = ("locale_code", "name", "slug", "description")
    verbose_name = _("Tarjima")
    verbose_name_plural = _("Nomi va tavsifi (uz · ru · en)")


class BrandAdminForm(forms.ModelForm):
    logo_upload = forms.ImageField(required=False, label="Logotip", help_text="Oq yoki shaffof fonli kvadrat logo eng chiroyli chiqadi. Saqlanganda media pipeline orqali kichik o'lchamlari ham yaratiladi.")

    class Meta:
        model = orm.Brand
        fields = ["is_active", "is_manufacturer", "logo_upload"]  # logo_storage_path/logo_thumbnail_paths are internal implementation detail, never a real admin-editable field -- save_model() sets them directly from the upload.
        labels = {"is_active": "Faol", "is_manufacturer": "Ishlab chiqaruvchi"}
        help_texts = {"is_active": "O'chirilsa brend saytdagi brendlar ro'yxatida ko'rinmaydi.", "is_manufacturer": "Brend o'zi zavod / ishlab chiqaruvchi bo'lsa yoqing."}


@admin.register(orm.Brand)
class BrandAdmin(CatalogFormMixin, CatalogAnalyticsMixin, admin.ModelAdmin):
    form = BrandAdminForm
    hero_icon, hero_tone, hero_noun = "fa-tags", "#6366f1", "brend"
    fieldsets = (
        ("Holat", {"fields": ("is_active", "is_manufacturer")}),
        ("Logotip", {"fields": ("logo_upload",)}),
        ("Tizim ma'lumotlari", {"classes": ("nzp-fold",), "fields": ("id", "created_at", "updated_at")}),
    )

    def form_hero(self, request, obj):
        if obj is None:
            return {}
        from django.urls import reverse

        snap = ca.snapshot(30)
        products = list(orm.Product.objects.filter(brand=obj).values_list("id", "status"))
        live = sum(1 for _p, st in products if st == "published")
        units = sum(snap.product_stock.get(pid, 0) for pid, _st in products)
        sales = snap.brand_sales.get(obj.id)
        share = round(float(sales.revenue) * 100 / float(snap.total.revenue)) if sales and snap.total.revenue else 0
        chips = [active_pill(obj.is_active), _locales_pill(obj.translations.all())]
        if obj.is_manufacturer:
            chips.insert(1, pill("Ishlab chiqaruvchi", "#8b5cf6", "fa-industry"))
        site = storefront_url(f"/brands/{obj.id}")
        return {
            "title": _display_name(obj.translations.all(), obj.id), "subtitle": _description_of(obj.translations.all()),
            "image": media_url(obj.logo_storage_path, obj.logo_thumbnail_paths), "chips": chips,
            "stats": [
                stat("Mahsulotlar", f"{len(products)} ta", "#2563eb", f"{live} tasi sotuvda", "fa-box"),
                stat("Qoldiq", f"{units} dona", "#16a34a" if units else "#e11d48", "barcha filial va omborlar", "fa-cubes"),
                sales_stat(sales),
                stat("Savdodagi ulush", f"{share}%", "#f59e0b", "30 kunlik tushumdan", "fa-chart-pie"),
            ],
            "links": [l for l in (
                {"label": "Saytda ko'rish", "url": site, "icon": "fa-arrow-up-right-from-square", "external": True, "primary": True} if site else None,
                {"label": "Mahsulotlari", "url": reverse("admin:products_product_changelist") + f"?brand__id__exact={obj.id}", "icon": "fa-box"},
            ) if l],
        }
    list_display = ("logo_display", "brand_col", "products_col", "stock_col", "sales_col", "active_col")
    list_display_links = ("logo_display", "brand_col")
    analytics_title = "Brendlar"
    list_filter = (("is_manufacturer", titled("Ishlab chiqaruvchi")), ("is_active", titled("Faol")))
    search_fields = ("translations__name",)  # Phase 08.3: genuine gap, this phase's own explicit search requirement
    list_per_page = 25
    inlines = [BrandTranslationInline]
    readonly_fields = ("id", "created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        uploaded = form.cleaned_data.get("logo_upload")
        if uploaded:
            from apps.products.infrastructure.composition import build_media_pipeline
            from core.media import MediaType, MediaUploadRequest

            result = build_media_pipeline().process(MediaUploadRequest(filename=uploaded.name, content=uploaded.read(), mime_type=uploaded.content_type, media_type=MediaType.IMAGE))
            if result.is_failure:
                raise forms.ValidationError(result.errors[0].message)
            processed = result.value
            obj.logo_storage_path = processed.storage_path
            obj.logo_thumbnail_paths = processed.thumbnail_paths
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("translations")

    def analytics(self, request, snap):
        from django.db.models import Count, Q

        rows = list(orm.Brand.objects.prefetch_related("translations").annotate(n=Count("products", filter=Q(products__is_deleted=False))))
        self._brand_products = {b.id: b.n for b in rows}
        names = {b.id: _display_name(b.translations.all(), b.id) for b in rows}
        rank = ca.ranking([(names.get(bid, "—"), n, "") for bid, n in snap.brand_sales.items()])
        for i, r in enumerate(rank):
            r["color"] = ca.PALETTE[i]
        top = rank[0]["label"] if rank else "—"
        return {
            "kpis": [
                kpi("Jami brend", len(rows), "fa-tags", "#2563eb", f"{sum(1 for b in rows if b.is_active)} faol"),
                kpi("Ishlab chiqaruvchi", sum(1 for b in rows if b.is_manufacturer), "fa-industry", "#8b5cf6", "zavod / manufacturer"),
                kpi("Mahsulotsiz", sum(1 for b in rows if not b.n), "fa-box-open", "#f59e0b", "hali mahsulot qo'shilmagan"),
                kpi("Sotuvi bor", len([1 for n in snap.brand_sales.values() if n.units]), "fa-chart-line", "#16a34a", "so'nggi 30 kunda"),
                kpi("30 kunlik tushum", ca.compact(snap.total.revenue), "fa-sack-dollar", "#f59e0b", "so'm", snap.total.change_pct),
                kpi("Yetakchi brend", top, "fa-crown", "#db2777", rank[0]["revenue"] + " so'm" if rank else ""),
            ],
            "ranking_title": "Brendlar reytingi", "ranking": {"rows": rank},
            "donut_title": "Mahsulotlar soni bo'yicha", "donut_unit": "mahsulot", "donut": ca.donut([(names[b.id], b.n) for b in rows]),
        }

    def _products_of(self, obj) -> list:
        cache = getattr(self, "_brand_product_ids", None)
        if cache is None:
            cache = self._brand_product_ids = {}
            for pid, bid in orm.Product.objects.values_list("id", "brand_id"):
                cache.setdefault(bid, []).append(pid)
        return cache.get(obj.id, [])

    @admin.display(description="Brend")
    def brand_col(self, obj: orm.Brand) -> str:
        tag = mark_safe(' <span class="nzc-pill" style="--t:#8b5cf6"><i class="fas fa-industry"></i> Ishlab chiqaruvchi</span>') if obj.is_manufacturer else ""
        return format_html('<div class="nzc-name"><b>{}{}</b></div>', _display_name(obj.translations.all(), obj.id), tag)

    @admin.display(description="Mahsulotlar")
    def products_col(self, obj: orm.Brand) -> str:
        return format_html('<span class="nzc-count"><b>{}</b><small>ta</small></span>', len(self._products_of(obj)))

    @admin.display(description="Qoldiq")
    def stock_col(self, obj: orm.Brand) -> str:
        units = sum(self.snap.product_stock.get(pid, 0) for pid in self._products_of(obj))
        return format_html('<span class="nzc-count"><b>{}</b><small>dona</small></span>', units)

    @admin.display(description="30 kunlik savdo")
    def sales_col(self, obj: orm.Brand) -> str:
        return sales_cell(self.snap.brand_sales.get(obj.id), self.snap.total.revenue or None)

    @admin.display(description="Holat", ordering="is_active")
    def active_col(self, obj: orm.Brand) -> str:
        return active_pill(obj.is_active)

    def logo_display(self, obj: orm.Brand) -> str:
        return _direct_thumbnail_html(obj.logo_storage_path, obj.logo_thumbnail_paths)

    logo_display.short_description = ""

    def name_display(self, obj: orm.Brand) -> str:
        t = next((tr for tr in obj.translations.all() if tr.locale_code == "en"), None)
        return t.name if t else str(obj.id)

    name_display.short_description = "Name"


class CategoryTranslationInline(TranslationInlineMixin, admin.StackedInline):
    model = orm.CategoryTranslation
    fields = ("locale_code", "name", "slug", "description")
    verbose_name = _("Tarjima")
    verbose_name_plural = _("Nomi va tavsifi (uz · ru · en)")


class CategoryAdminForm(forms.ModelForm):
    image_upload = forms.ImageField(required=False, label="Rasm", help_text="Kategoriya kartochkasidagi rasm. Shaffof fonli PNG / WebP eng chiroyli chiqadi.")

    class Meta:
        model = orm.Category
        fields = ["parent", "sort_order", "is_active", "image_upload"]  # image_storage_path/image_thumbnail_paths are internal implementation detail, never a real admin-editable field.
        labels = {"parent": "Ota kategoriya", "sort_order": "Tartib raqami", "is_active": "Faol"}
        help_texts = {
            "parent": "Bo'sh qoldirilsa — asosiy (yuqori darajadagi) kategoriya.",
            "sort_order": "Kichik raqam ro'yxatda oldinroq chiqadi.",
            "is_active": "O'chirilsa kategoriya saytda ko'rinmaydi.",
        }


@admin.register(orm.Category)
class CategoryAdmin(CatalogFormMixin, CatalogAnalyticsMixin, admin.ModelAdmin):
    form = CategoryAdminForm
    hero_icon, hero_tone, hero_noun = "fa-sitemap", "#0ea5e9", "kategoriya"
    fieldsets = (
        ("Joylashuv va holat", {"fields": ("parent", "sort_order", "is_active")}),
        ("Rasm", {"fields": ("image_upload",)}),
        ("Tizim ma'lumotlari", {"classes": ("nzp-fold",), "fields": ("id", "created_at", "updated_at")}),
    )

    def form_hero(self, request, obj):
        if obj is None:
            return {}
        from django.urls import reverse

        snap = ca.snapshot(30)
        products = list(orm.Product.objects.filter(category=obj).values_list("id", "status"))
        live = sum(1 for _p, st in products if st == "published")
        units = sum(snap.product_stock.get(pid, 0) for pid, _st in products)
        children = orm.Category.objects.filter(parent=obj).count()
        chips = [active_pill(obj.is_active), _locales_pill(obj.translations.all())]
        chips.insert(1, pill(f"↳ {_display_name(obj.parent.translations.all(), obj.parent_id)}", "#64748b", "fa-folder") if obj.parent_id else pill("Asosiy kategoriya", "#0ea5e9", "fa-folder"))
        site = storefront_url(f"/categories/{obj.id}")
        return {
            "title": _display_name(obj.translations.all(), obj.id), "subtitle": _description_of(obj.translations.all()),
            "image": media_url(obj.image_storage_path, obj.image_thumbnail_paths), "chips": chips,
            "stats": [
                stat("Mahsulotlar", f"{len(products)} ta", "#2563eb", f"{live} tasi sotuvda", "fa-box"),
                stat("Ichki kategoriyalar", children, "#8b5cf6", "sub-kategoriya", "fa-folder-tree"),
                stat("Qoldiq", f"{units} dona", "#16a34a" if units else "#e11d48", "barcha filial va omborlar", "fa-cubes"),
                sales_stat(snap.category_sales.get(obj.id)),
            ],
            "links": [l for l in (
                {"label": "Saytda ko'rish", "url": site, "icon": "fa-arrow-up-right-from-square", "external": True, "primary": True} if site else None,
                {"label": "Mahsulotlari", "url": reverse("admin:products_product_changelist") + f"?category__id__exact={obj.id}", "icon": "fa-box"},
            ) if l],
        }
    list_display = ("image_display", "category_col", "products_col", "stock_col", "sales_col", "order_col", "active_col")
    list_display_links = ("image_display", "category_col")
    analytics_title = "Kategoriyalar"
    list_filter = (("is_active", titled("Faol")), ("parent", titled("Ota kategoriya")))  # Phase 08.3: parent filter surfaces the existing hierarchy (Category.parent is a real, self-referential FK, confirmed by direct model inspection)
    search_fields = ("translations__name",)
    list_per_page = 25
    inlines = [CategoryTranslationInline]
    readonly_fields = ("id", "created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        uploaded = form.cleaned_data.get("image_upload")
        if uploaded:
            from apps.products.infrastructure.composition import build_media_pipeline
            from core.media import MediaType, MediaUploadRequest

            result = build_media_pipeline().process(MediaUploadRequest(filename=uploaded.name, content=uploaded.read(), mime_type=uploaded.content_type, media_type=MediaType.IMAGE))
            if result.is_failure:
                raise forms.ValidationError(result.errors[0].message)
            processed = result.value
            obj.image_storage_path = processed.storage_path
            obj.image_thumbnail_paths = processed.thumbnail_paths
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("parent").prefetch_related("translations", "parent__translations")

    def analytics(self, request, snap):
        from django.db.models import Count, Q

        rows = list(orm.Category.objects.prefetch_related("translations").annotate(n=Count("products", filter=Q(products__is_deleted=False))))
        names = {c.id: _display_name(c.translations.all(), c.id) for c in rows}
        rank = ca.ranking([(names.get(cid, "—"), n, "") for cid, n in snap.category_sales.items()])
        for i, r in enumerate(rank):
            r["color"] = ca.PALETTE[i]
        return {
            "kpis": [
                kpi("Jami kategoriya", len(rows), "fa-sitemap", "#2563eb", f"{sum(1 for c in rows if c.is_active)} faol"),
                kpi("Asosiy", sum(1 for c in rows if not c.parent_id), "fa-folder", "#16a34a", "yuqori darajadagi"),
                kpi("Ichki", sum(1 for c in rows if c.parent_id), "fa-folder-tree", "#8b5cf6", "sub-kategoriyalar"),
                kpi("Bo'sh", sum(1 for c in rows if not c.n), "fa-box-open", "#f59e0b", "mahsulotsiz"),
                kpi("30 kunlik tushum", ca.compact(snap.total.revenue), "fa-sack-dollar", "#f59e0b", "so'm", snap.total.change_pct),
                kpi("Yetakchi", rank[0]["label"] if rank else "—", "fa-crown", "#db2777", rank[0]["revenue"] + " so'm" if rank else ""),
            ],
            "ranking_title": "Kategoriyalar reytingi", "ranking": {"rows": rank},
            "donut_title": "Mahsulotlar taqsimoti", "donut_unit": "mahsulot", "donut": ca.donut([(names[c.id], c.n) for c in rows]),
        }

    def _products_of(self, obj) -> list:
        cache = getattr(self, "_cat_product_ids", None)
        if cache is None:
            cache = self._cat_product_ids = {}
            for pid, cid in orm.Product.objects.values_list("id", "category_id"):
                cache.setdefault(cid, []).append(pid)
        return cache.get(obj.id, [])

    @admin.display(description="Kategoriya")
    def category_col(self, obj: orm.Category) -> str:
        parent = format_html('<small><i class="fas fa-level-up-alt fa-rotate-90"></i> {}</small>', _display_name(obj.parent.translations.all(), obj.parent_id)) if obj.parent else mark_safe("<small>Asosiy kategoriya</small>")
        return format_html('<div class="nzc-name"><b>{}</b>{}</div>', _display_name(obj.translations.all(), obj.id), parent)

    @admin.display(description="Mahsulotlar")
    def products_col(self, obj: orm.Category) -> str:
        return format_html('<span class="nzc-count"><b>{}</b><small>ta</small></span>', len(self._products_of(obj)))

    @admin.display(description="Qoldiq")
    def stock_col(self, obj: orm.Category) -> str:
        return format_html('<span class="nzc-count"><b>{}</b><small>dona</small></span>', sum(self.snap.product_stock.get(pid, 0) for pid in self._products_of(obj)))

    @admin.display(description="30 kunlik savdo")
    def sales_col(self, obj: orm.Category) -> str:
        return sales_cell(self.snap.category_sales.get(obj.id), self.snap.total.revenue or None)

    @admin.display(description="Tartib", ordering="sort_order")
    def order_col(self, obj) -> int:
        return obj.sort_order

    @admin.display(description="Holat", ordering="is_active")
    def active_col(self, obj: orm.Category) -> str:
        return active_pill(obj.is_active)

    def image_display(self, obj: orm.Category) -> str:
        return _direct_thumbnail_html(obj.image_storage_path, obj.image_thumbnail_paths)

    image_display.short_description = ""

    def name_display(self, obj: orm.Category) -> str:
        t = next((tr for tr in obj.translations.all() if tr.locale_code == "en"), None)
        return t.name if t else str(obj.id)

    name_display.short_description = "Name"


class TagTranslationInline(TranslationInlineMixin, admin.StackedInline):
    model = orm.TagTranslation
    verbose_name = _("Tarjima")
    verbose_name_plural = _("Nomi (uz · ru · en)")


class TagAdminForm(forms.ModelForm):
    class Meta:
        model = orm.Tag
        fields = ["code"]
        widgets = {"code": forms.TextInput(attrs={"placeholder": "sport-nutrition", "autocomplete": "off"})}
        labels = {"code": "Kod"}
        help_texts = {"code": "Lotincha, takrorlanmas: masalan <code>protein</code>, <code>vegan</code>, <code>new-arrival</code>. Saytda tarjima qilingan nomi chiqadi."}

    def clean_code(self):
        import re

        code = (self.cleaned_data.get("code") or "").strip().lower()
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", code):
            raise forms.ValidationError("Faqat kichik lotin harflari, raqamlar va chiziqcha: masalan sport-nutrition.")
        return code


@admin.register(orm.Tag)
class TagAdmin(CatalogFormMixin, CatalogAnalyticsMixin, admin.ModelAdmin):
    form = TagAdminForm
    hero_icon, hero_tone, hero_noun = "fa-hashtag", "#f59e0b", "teg"
    fieldsets = (("Asosiy", {"fields": ("code",)}),)
    inlines = [TagTranslationInline]
    list_display = ("tag_col", "names_col", "products_col", "langs_col")
    list_display_links = ("tag_col",)
    analytics_title = "Teglar"
    search_fields = ("code", "translations__name")
    list_per_page = 25
    ordering = ("code",)

    def get_queryset(self, request):
        from django.db.models import Count

        return super().get_queryset(request).prefetch_related("translations").annotate(n_products=Count("product_links", distinct=True))

    def analytics(self, request, snap):
        from django.db.models import Count

        rows = list(orm.Tag.objects.prefetch_related("translations").annotate(n=Count("product_links", distinct=True)))
        names = {t.id: _display_name(t.translations.all(), t.code) for t in rows}
        used = [t for t in rows if t.n]
        full = sum(1 for t in rows if {tr.locale_code for tr in t.translations.all() if tr.name} >= {"uz", "ru", "en"})
        top = max(used, key=lambda t: t.n) if used else None
        return {
            "kpis": [
                kpi("Jami teg", len(rows), "fa-hashtag", "#f59e0b", "mahsulot belgilari"),
                kpi("Ishlatilmoqda", len(used), "fa-link", "#16a34a", "mahsulotlarga biriktirilgan"),
                kpi("Ishlatilmagan", len(rows) - len(used), "fa-link-slash", "#64748b", "birorta mahsulotda yo'q"),
                kpi("Bog'lanishlar", sum(t.n for t in rows), "fa-diagram-project", "#8b5cf6", "mahsulot ↔ teg"),
                kpi("3 tilda", full, "fa-language", "#0d9488", "uz · ru · en to'liq"),
                kpi("Eng ko'p", names[top.id] if top else "—", "fa-crown", "#db2777", f"{top.n} mahsulotda" if top else ""),
            ],
            "donut_title": "Mahsulotlar teglar bo'yicha", "donut_unit": "bog'lanish",
            "donut": ca.donut([(names[t.id], t.n) for t in rows]) if used else None,
        }

    def form_hero(self, request, obj):
        if obj is None:
            return {}
        n = obj.product_links.count()
        names = {t.locale_code: t.name for t in obj.translations.all()}
        return {
            "title": names.get("uz") or names.get("en") or obj.code, "subtitle": f"#{obj.code}",
            "chips": [_locales_pill(obj.translations.all())],
            "stats": [stat("Mahsulotlarda", f"{n} ta", "#2563eb", "shu teg biriktirilgan", "fa-box")],
        }

    @admin.display(description="Teg", ordering="code")
    def tag_col(self, obj: orm.Tag) -> str:
        name = _display_name(obj.translations.all(), obj.code)
        return format_html('<div style="display:flex;align-items:center;gap:10px"><span style="width:34px;height:34px;border-radius:11px;display:grid;place-items:center;color:#f59e0b;background:rgba(245,158,11,.14)"><i class="fas fa-hashtag"></i></span><span class="nzc-name"><b>{}</b><small><code>{}</code></small></span></div>', name, obj.code)

    @admin.display(description="Tarjimalar")
    def names_col(self, obj: orm.Tag) -> str:
        names = {t.locale_code: t.name for t in obj.translations.all()}
        parts = [format_html('<span title="{}">{} {}</span>', code, flag, names[code]) for code, flag in (("ru", "🇷🇺"), ("en", "🇬🇧")) if names.get(code)]
        return format_html('<div class="nzc-name"><small>{}</small></div>', mark_safe(" · ".join(parts))) if parts else mark_safe('<span class="nzc-muted">—</span>')

    @admin.display(description="Mahsulotlar", ordering="n_products")
    def products_col(self, obj: orm.Tag) -> str:
        return format_html('<span class="nzc-count"><b>{}</b><small>ta</small></span>', obj.n_products)

    @admin.display(description="Tillar")
    def langs_col(self, obj: orm.Tag) -> str:
        return _locales_pill(obj.translations.all())


class FlavourTranslationInline(TranslationInlineMixin, admin.StackedInline):
    model = orm.FlavourTranslation
    verbose_name = _("Tarjima")
    verbose_name_plural = _("Nomi (uz · ru · en)")


class FlavourAdminForm(forms.ModelForm):
    """Mirrors BrandAdminForm's exact shape -- a non-model `image_upload` field processed by `save_model()` (see FlavourAdmin below), plus a real HTML5 color-picker widget for `color_hex` (never a free-text hex input, per explicit product decision)."""

    image_upload = forms.ImageField(required=False, label="Rasm", help_text="Saytdagi ta'm almashtirgichda ko'rinadi. Rasm bo'lmasa — tanlangan rang chiqadi.")

    class Meta:
        model = orm.Flavour
        fields = ["slug", "color_hex", "sort_order", "is_active", "image_upload"]  # image_storage_path/image_thumbnail_paths are internal implementation detail, never a real admin-editable field -- save_model() sets them directly from the upload.
        widgets = {"color_hex": forms.TextInput(attrs={"type": "color"}), "slug": forms.TextInput(attrs={"placeholder": "chocolate", "autocomplete": "off"})}
        labels = {"slug": "Kod (slug)", "color_hex": "Rang", "sort_order": "Tartib raqami", "is_active": "Faol"}
        help_texts = {
            "slug": "Lotincha, takrorlanmas: masalan <code>chocolate</code>, <code>vanilla</code>.",
            "color_hex": "Ta'mning belgisi — rasm bo'lmaganda chiqadigan rang.",
            "sort_order": "Kichik raqam ro'yxatda oldinroq chiqadi.",
            "is_active": "O'chirilsa yangi mahsulotlarga tanlab bo'lmaydi.",
        }


@admin.register(orm.Flavour)
class FlavourAdmin(CatalogFormMixin, CatalogAnalyticsMixin, admin.ModelAdmin):
    """Real, dedicated module replacing the old generic Attribute/AttributeValue "flavor" reservation -- mirrors BrandAdmin's exact save_model()/image-upload pattern, plus a real selectable color (see FlavourAdminForm's widgets) instead of a free-text hex input."""

    form = FlavourAdminForm
    hero_icon, hero_tone, hero_noun = "fa-ice-cream", "#ec4899", "ta'm"
    fieldsets = (
        ("Asosiy", {"fields": ("slug", "sort_order", "is_active")}),
        ("Rang va rasm", {"fields": ("color_hex", "image_upload")}),
        ("Tizim ma'lumotlari", {"classes": ("nzp-fold",), "fields": ("id", "created_at", "updated_at")}),
    )
    list_display = ("image_display", "flavour_col", "products_col", "sales_col", "order_col", "active_col")
    list_display_links = ("image_display", "flavour_col")
    analytics_title = "Ta'mlar"
    list_filter = (("is_active", titled("Faol")),)
    search_fields = ("translations__name", "slug")
    list_per_page = 25
    inlines = [FlavourTranslationInline]
    readonly_fields = ("id", "created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        uploaded = form.cleaned_data.get("image_upload")
        if uploaded:
            from apps.products.infrastructure.composition import build_media_pipeline
            from core.media import MediaType, MediaUploadRequest

            result = build_media_pipeline().process(MediaUploadRequest(filename=uploaded.name, content=uploaded.read(), mime_type=uploaded.content_type, media_type=MediaType.IMAGE))
            if result.is_failure:
                raise forms.ValidationError(result.errors[0].message)
            processed = result.value
            obj.image_storage_path = processed.storage_path
            obj.image_thumbnail_paths = processed.thumbnail_paths
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("translations")

    def form_hero(self, request, obj):
        if obj is None:
            return {"swatch": "#ec4899"}
        snap = ca.snapshot(30)
        links = list(orm.ProductFlavour.objects.filter(flavour=obj).values_list("product_id", flat=True))
        live = orm.Product.objects.filter(id__in=links, status="published").count()
        sales = snap.flavour_sales.get(obj.id)
        image = media_url(obj.image_storage_path, obj.image_thumbnail_paths)
        return {
            "title": _display_name(obj.translations.all(), obj.id), "subtitle": f"Kod: {obj.slug} · rang {obj.color_hex.upper()}",
            "image": image, "swatch": "" if image else obj.color_hex, "tone": obj.color_hex or "#ec4899",
            "chips": [active_pill(obj.is_active), _locales_pill(obj.translations.all()), pill("Rasm bor" if image else "Rasmsiz", "#16a34a" if image else "#64748b", "fa-image")],
            "stats": [
                stat("Mahsulotlarda", f"{len(links)} ta", "#2563eb", f"{live} tasi sotuvda", "fa-link"),
                sales_stat(sales),
                stat("Tartib", obj.sort_order, "#8b5cf6", "ro'yxatdagi o'rni", "fa-arrow-down-1-9"),
            ],
        }

    def image_display(self, obj: orm.Flavour) -> str:
        return _direct_thumbnail_html(obj.image_storage_path, obj.image_thumbnail_paths)

    image_display.short_description = ""

    def analytics(self, request, snap):
        from django.db.models import Count

        rows = list(orm.Flavour.objects.prefetch_related("translations").annotate(n=Count("product_links")))
        self._flavour_products = {f.id: f.n for f in rows}
        names = {f.id: _display_name(f.translations.all(), f.id) for f in rows}
        colors = {f.id: f.color_hex for f in rows}
        rank = ca.ranking([(names.get(fid, "—"), n, "") for fid, n in snap.flavour_sales.items()])
        by_label = {names[fid]: colors[fid] for fid in names}
        for i, r in enumerate(rank):
            r["color"] = by_label.get(r["label"]) or ca.PALETTE[i]
        used = sum(1 for f in rows if f.n)
        donut = ca.donut([(names[f.id], f.n) for f in rows])
        for item in donut["legend"]:  # a flavour's own colour reads better than the generic palette
            item["color"] = by_label.get(item["label"], item["color"])
        stops, acc, total = [], 0.0, donut["total"] or 1
        for item in donut["legend"]:
            start, acc = acc, acc + item["value"] * 100 / total
            stops.append(f"{item['color']} {start:.2f}% {acc:.2f}%")
        donut["gradient"] = f"conic-gradient({', '.join(stops)})" if stops else ""
        return {
            "kpis": [
                kpi("Jami ta'm", len(rows), "fa-ice-cream", "#ec4899", f"{sum(1 for f in rows if f.is_active)} faol"),
                kpi("Ishlatilmoqda", used, "fa-link", "#16a34a", "mahsulotlarga biriktirilgan"),
                kpi("Ishlatilmagan", len(rows) - used, "fa-link-slash", "#f59e0b", "birorta mahsulotda yo'q"),
                kpi("Rasmsiz", sum(1 for f in rows if not f.image_storage_path), "fa-image", "#64748b", "saytda rang bilan chiqadi"),
                kpi("30 kunlik tushum", ca.compact(sum((n.revenue for n in snap.flavour_sales.values()), ca.Decimal("0"))), "fa-sack-dollar", "#f59e0b", "ta'mli mahsulotlardan"),
                kpi("Eng sevimli", rank[0]["label"] if rank else "—", "fa-heart", "#e11d48", f"{rank[0]['units']} dona sotildi" if rank else ""),
            ],
            "ranking_title": "Eng ko'p sotilgan ta'mlar", "ranking": {"rows": rank},
            "donut_title": "Mahsulotlardagi ta'mlar", "donut_unit": "bog'lanish", "donut": donut,
        }

    @admin.display(description="Ta'm")
    def flavour_col(self, obj: orm.Flavour) -> str:
        return format_html('<div class="nzc-name" style="display:flex;align-items:center;gap:10px"><span class="nzc-swatch" style="background:{}"></span><span><b>{}</b><small>{}</small></span></div>', obj.color_hex, _display_name(obj.translations.all(), obj.id), obj.slug)

    @admin.display(description="Mahsulotlar")
    def products_col(self, obj: orm.Flavour) -> str:
        n = getattr(self, "_flavour_products", {}).get(obj.id)
        if n is None:
            n = obj.product_links.count()
        return format_html('<span class="nzc-count"><b>{}</b><small>ta</small></span>', n)

    @admin.display(description="30 kunlik savdo")
    def sales_col(self, obj: orm.Flavour) -> str:
        return sales_cell(self.snap.flavour_sales.get(obj.id))

    @admin.display(description="Tartib", ordering="sort_order")
    def order_col(self, obj) -> int:
        return obj.sort_order

    @admin.display(description="Holat", ordering="is_active")
    def active_col(self, obj: orm.Flavour) -> str:
        return active_pill(obj.is_active)

    def color_swatch(self, obj: orm.Flavour) -> str:
        return format_html('<span class="nz-thumb" style="background-color:{}; display:inline-block; width:24px; height:24px; border-radius:6px;"></span>', obj.color_hex)

    color_swatch.short_description = "Color"

    def name_display(self, obj: orm.Flavour) -> str:
        return _display_name(obj.translations.all(), obj.id)

    name_display.short_description = "Name"


class PackageTranslationInline(TranslationInlineMixin, admin.StackedInline):
    model = orm.PackageTranslation
    verbose_name = _("Tarjima")
    verbose_name_plural = _("Nomi (uz · ru · en)")


class PackageAdminForm(forms.ModelForm):
    class Meta:
        model = orm.Package
        fields = ["slug", "sort_order", "is_active"]
        widgets = {"slug": forms.TextInput(attrs={"placeholder": "bottle", "autocomplete": "off"})}
        labels = {"slug": "Kod (slug)", "sort_order": "Tartib raqami", "is_active": "Faol"}
        help_texts = {
            "slug": "Lotincha, takrorlanmas: <code>jar</code>, <code>bottle</code>, <code>pouch</code> … — belgi (ikonka) shu koddan tanlanadi.",
            "sort_order": "Kichik raqam tanlov ro'yxatida oldinroq chiqadi.",
            "is_active": "O'chirilsa variantlarga yangidan tanlab bo'lmaydi.",
        }


@admin.register(orm.Package)
class PackageAdmin(CatalogFormMixin, admin.ModelAdmin):
    """Real, dedicated module for a variant's real container/packaging type (box/bottle/pouch/...) -- referenced by a single FK on ProductVariant, never a Product-level tag like Flavour (see domain/aggregates.py::Package's own docstring)."""

    form = PackageAdminForm
    hero_icon, hero_tone, hero_noun = "fa-box-open", "#10b981", "qadoq"
    fieldsets = (
        ("Asosiy", {"fields": ("slug", "sort_order", "is_active")}),
        ("Tizim ma'lumotlari", {"classes": ("nzp-fold",), "fields": ("id", "created_at", "updated_at")}),
    )
    list_display = ("package_col", "slug_col", "variants_col", "order_col", "active_col")
    list_display_links = ("package_col",)
    list_filter = (("is_active", titled("Faol")),)
    search_fields = ("translations__name", "slug")
    list_per_page = 25
    inlines = [PackageTranslationInline]
    readonly_fields = ("id", "created_at", "updated_at")
    change_list_template = "admin/products/analytics_change_list.html"

    ICONS = PACKAGE_ICONS

    def get_queryset(self, request):
        from django.db.models import Count, Q

        return super().get_queryset(request).prefetch_related("translations").annotate(n_variants=Count("variants", filter=Q(variants__is_deleted=False)))

    def changelist_view(self, request, extra_context=None):
        from django.db.models import Count, Q

        rows = list(orm.Package.objects.prefetch_related("translations").annotate(n=Count("variants", filter=Q(variants__is_deleted=False))))
        uz = {p.id: _display_name(p.translations.all(), p.id) for p in rows}
        full = sum(1 for p in rows if {t.locale_code for t in p.translations.all()} >= {"uz", "ru", "en"})
        used = [p for p in rows if p.n]
        nzc = {
            "kpis": [
                kpi("Qadoq turlari", len(rows), "fa-box-open", "#2563eb", f"{sum(1 for p in rows if p.is_active)} faol"),
                kpi("Ishlatilmoqda", len(used), "fa-link", "#16a34a", "variantlarga biriktirilgan"),
                kpi("Variantlar", sum(p.n for p in rows), "fa-layer-group", "#8b5cf6", "qadog'i ko'rsatilgan"),
                kpi("Qadoqsiz variant", orm.ProductVariant.objects.filter(package__isnull=True).count(), "fa-circle-question", "#f59e0b", "qadoq tanlanmagan"),
                kpi("3 tilda", full, "fa-language", "#0d9488", "uz · ru · en to'liq"),
                kpi("Eng ko'p", uz[max(used, key=lambda p: p.n).id] if used else "—", "fa-crown", "#db2777", f"{max(used, key=lambda p: p.n).n} variant" if used else ""),
            ],
            "donut_title": "Variantlar qadoq bo'yicha", "donut_unit": "variant",
            "donut": ca.donut([(uz[p.id], p.n) for p in rows]),
        }
        return super().changelist_view(request, {**(extra_context or {}), "nzc": nzc, "title": "Qadoqlar"})

    def form_hero(self, request, obj):
        if obj is None:
            return {}
        from django.urls import reverse

        variants = orm.ProductVariant.objects.filter(package=obj)
        n = variants.count()
        products = variants.values("product_id").distinct().count()
        names = {t.locale_code: t.name for t in obj.translations.all()}
        return {
            "title": names.get("uz") or names.get("en") or obj.slug, "subtitle": " · ".join(v for v in (names.get("ru"), names.get("en")) if v) or f"Kod: {obj.slug}",
            "icon": self.ICONS.get(obj.slug, "fa-box"), "chips": [active_pill(obj.is_active), _locales_pill(obj.translations.all()), pill(obj.slug, "#64748b", "fa-code")],
            "stats": [
                stat("Variantlar", f"{n} ta", "#2563eb", "shu qadoqdagi", "fa-layer-group"),
                stat("Mahsulotlar", f"{products} ta", "#8b5cf6", "turli mahsulot", "fa-box"),
                stat("Tartib", obj.sort_order, "#f59e0b", "tanlov ro'yxatidagi o'rni", "fa-arrow-down-1-9"),
            ],
            "links": [{"label": "Variantlari", "url": reverse("admin:products_productvariant_changelist") + f"?package__id__exact={obj.id}", "icon": "fa-layer-group"}] if n else [],
        }

    @admin.display(description="Qadoq")
    def package_col(self, obj: orm.Package) -> str:
        names = {t.locale_code: t.name for t in obj.translations.all()}
        main = names.get("uz") or names.get("en") or obj.slug
        sub = " · ".join(v for v in (names.get("ru"), names.get("en")) if v and v != main)
        return format_html('<div style="display:flex;align-items:center;gap:10px"><span style="width:34px;height:34px;border-radius:11px;display:grid;place-items:center;color:#10b981;background:rgba(16,185,129,.14)"><i class="fas {}"></i></span><span class="nzc-name"><b>{}</b><small>{}</small></span></div>', self.ICONS.get(obj.slug, "fa-box"), main, sub)

    @admin.display(description="Kod", ordering="slug")
    def slug_col(self, obj: orm.Package) -> str:
        return format_html('<code>{}</code>', obj.slug)

    @admin.display(description="Variantlar", ordering="n_variants")
    def variants_col(self, obj: orm.Package) -> str:
        return format_html('<span class="nzc-count"><b>{}</b><small>ta</small></span>', obj.n_variants)

    @admin.display(description="Tartib", ordering="sort_order")
    def order_col(self, obj) -> int:
        return obj.sort_order

    @admin.display(description="Holat", ordering="is_active")
    def active_col(self, obj: orm.Package) -> str:
        return active_pill(obj.is_active)

    def name_display(self, obj: orm.Package) -> str:
        return _display_name(obj.translations.all(), obj.id)

    name_display.short_description = "Name"


# Real, product-required simplification: removed from Dashboard -- read-only, system-internal (event-log) data an admin never creates or edits by hand.
# @admin.register(orm.ProductsOutboxEvent)
class ProductsOutboxEventAdmin(admin.ModelAdmin):
    """Read-only -- append-only/Outbox tables are never editable in admin, per MIC §9."""

    list_display = ("event_type", "event_version", "created_at", "published_at", "publish_attempts")
    list_filter = ("event_type",)
    readonly_fields = [f.name for f in orm.ProductsOutboxEvent._meta.fields]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
