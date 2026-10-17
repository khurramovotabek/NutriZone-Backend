"""
Products ORM models.

Maps 1:1 onto Enterprise Database Blueprint §4.2 (`catalog` schema),
plus the documented, justified additions/reconciliations already
recorded in domain/aggregates.py's module docstrings (the extended
MediaRole set, Flavour as a dedicated module replacing the old
generic Attribute/AttributeValue "flavor" reservation). Every
model composes from exactly one of common/models/'s three base mixins
per the model-category decision tree in the Universal Module
Implementation Contract §3. No business logic lives here -- these are
pure persistence shapes; infrastructure/repositories.py is the only
code that constructs or reads them on behalf of application/.

Localization: Category/Brand/Product/Tag/Flavour all follow the
Database Blueprint §4.2 translation-table pattern (name/description/
slug live in a `*_translations` table, not on the parent row) -- the
same pattern the Blueprint applies platform-wide, not a
Products-specific invention.
"""
from __future__ import annotations

import uuid

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.products.domain.enums import (
    CertificateType,
    MediaRole,
    ProductStatus,
    RelationType,
    VariantStatus,
    WeightUnit,
)
from common.models import AllObjectsManager, AppendOnlyModel, BaseModel, SoftDeleteModel
from common.utils import LOCALE_CHOICES, enum_field_kwargs
from core.outbox import AbstractOutboxEvent

# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


class Category(SoftDeleteModel):
    """Database Blueprint §4.2 `catalog.categories`."""

    parent = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="children")
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    # Media Asset architecture removed per explicit product decision --
    # direct file storage fields, populated by core.media.MediaPipeline
    # (same pattern as Brand.logo_storage_path/logo_thumbnail_paths).
    image_storage_path = models.CharField(max_length=500, blank=True, default="")
    image_thumbnail_paths = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "catalog_categories"
        verbose_name = _("Category")
        verbose_name_plural = _("Categories")
        indexes = [models.Index(fields=["parent", "sort_order"])]

    def __str__(self) -> str:  # pragma: no cover
        # In the dashboard's language (pickers, filters, history), then Uzbek, then English.
        from django.utils.translation import get_language

        rows = {t.locale_code: t.name for t in self.translations.all()}
        lang = (get_language() or "uz")[:2]
        return rows.get(lang) or rows.get("uz") or rows.get("en") or next(iter(rows.values()), str(self.id))


class CategoryTranslation(models.Model):
    """Database Blueprint §4.2 `catalog.category_translations` -- junction-shaped (no independent lifecycle), hard-deleted with its parent Category."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="translations")
    locale_code = models.CharField(max_length=5, choices=LOCALE_CHOICES)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    slug = models.SlugField(max_length=220)

    objects = AllObjectsManager()

    def __str__(self) -> str:  # pragma: no cover
        return self.name or str(self.id)

    class Meta:
        db_table = "catalog_category_translations"
        constraints = [
            models.UniqueConstraint(fields=["category", "locale_code"], name="uq_category_translations_category_locale"),
            models.UniqueConstraint(fields=["locale_code", "slug"], name="uq_category_translations_locale_slug"),
        ]
        indexes = [models.Index(fields=["locale_code", "slug"])]


# ---------------------------------------------------------------------------
# Brands (Brand + Manufacturer share this table -- is_manufacturer flag)
# ---------------------------------------------------------------------------


class Brand(SoftDeleteModel):
    """Database Blueprint §4.2 `catalog.brands`. `is_manufacturer` backs `domain/aggregates.py::Manufacturer`'s typed-factory-over-Brand pattern."""

    is_active = models.BooleanField(default=True)
    is_manufacturer = models.BooleanField(default=False, db_index=True)
    country = models.ForeignKey("geo.Country", on_delete=models.SET_NULL, null=True, blank=True, related_name="brands", verbose_name=_("Country of origin"))
    # Media Asset architecture removed per explicit product decision --
    # direct file storage fields, populated by core.media.MediaPipeline
    # (validation/thumbnail generation kept; only the shared
    # ProductMediaAsset table/FK-selection abstraction is gone).
    logo_storage_path = models.CharField(max_length=500, blank=True, default="")
    logo_thumbnail_paths = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "catalog_brands"
        verbose_name = _("Brand")
        verbose_name_plural = _("Brands")

    def __str__(self) -> str:  # pragma: no cover
        from django.utils.translation import get_language

        rows = {t.locale_code: t.name for t in self.translations.all()}
        lang = (get_language() or "uz")[:2]
        return rows.get(lang) or rows.get("uz") or rows.get("en") or next(iter(rows.values()), str(self.id))


class BrandTranslation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE, related_name="translations")
    locale_code = models.CharField(max_length=5, choices=LOCALE_CHOICES)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    slug = models.SlugField(max_length=220)

    objects = AllObjectsManager()

    def __str__(self) -> str:  # pragma: no cover
        return self.name or str(self.id)

    class Meta:
        db_table = "catalog_brand_translations"
        constraints = [
            models.UniqueConstraint(fields=["brand", "locale_code"], name="uq_brand_translations_brand_locale"),
            models.UniqueConstraint(fields=["locale_code", "slug"], name="uq_brand_translations_locale_slug"),
        ]
        indexes = [models.Index(fields=["locale_code", "slug"])]


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


class Tag(SoftDeleteModel):
    code = models.CharField(max_length=64, unique=True)

    class Meta:
        db_table = "catalog_tags"
        verbose_name = _("Tag")
        verbose_name_plural = _("Tags")

    def __str__(self) -> str:  # pragma: no cover
        translation = self.translations.first()
        return translation.name if translation is not None else self.code


class TagTranslation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name="translations")
    locale_code = models.CharField(max_length=5, choices=LOCALE_CHOICES)
    name = models.CharField(max_length=128)

    objects = AllObjectsManager()

    def __str__(self) -> str:  # pragma: no cover
        return self.name or str(self.id)

    class Meta:
        db_table = "catalog_tag_translations"
        constraints = [models.UniqueConstraint(fields=["tag", "locale_code"], name="uq_tag_translations_tag_locale")]


# ---------------------------------------------------------------------------
# Flavours (dedicated module -- replaces the old generic
# Attribute/AttributeValue "flavor" reservation per explicit product
# decision; linked to Product by a plain many-to-many, see
# ProductFlavour below)
# ---------------------------------------------------------------------------


class Flavour(SoftDeleteModel):
    """Database Blueprint §4.2 amendment `catalog.flavours` -- see domain/aggregates.py::Flavour's docstring."""

    slug = models.SlugField(max_length=220, unique=True)
    color_hex = models.CharField(max_length=7)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    # Media Asset architecture removed per explicit product decision --
    # direct file storage fields, populated by core.media.MediaPipeline
    # (same pattern as Brand.logo_storage_path/logo_thumbnail_paths).
    image_storage_path = models.CharField(max_length=500, blank=True, default="")
    image_thumbnail_paths = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "catalog_flavours"
        verbose_name = _("Flavour")
        verbose_name_plural = _("Flavours")
        ordering = ["sort_order", "-created_at"]

    def __str__(self) -> str:  # pragma: no cover
        from django.utils.translation import get_language

        rows = {t.locale_code: t.name for t in self.translations.all()}
        lang = (get_language() or "uz")[:2]
        return rows.get(lang) or rows.get("uz") or rows.get("en") or next(iter(rows.values()), str(self.id))


class FlavourTranslation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    flavour = models.ForeignKey(Flavour, on_delete=models.CASCADE, related_name="translations")
    locale_code = models.CharField(max_length=5, choices=LOCALE_CHOICES)
    name = models.CharField(max_length=128)

    objects = AllObjectsManager()

    def __str__(self) -> str:  # pragma: no cover
        return self.name or str(self.id)

    class Meta:
        db_table = "catalog_flavour_translations"
        constraints = [models.UniqueConstraint(fields=["flavour", "locale_code"], name="uq_flavour_translations_flavour_locale")]


# ---------------------------------------------------------------------------
# Packages (real container/packaging type -- box/bottle/pouch/... --
# per explicit product decision; linked from ProductVariant.package by
# a single FK, never a many-to-many like Flavour, see
# domain/aggregates.py::Package's own docstring)
# ---------------------------------------------------------------------------


class Package(SoftDeleteModel):
    """Database Blueprint §4.2 amendment `catalog.packages` -- see domain/aggregates.py::Package's docstring."""

    slug = models.SlugField(max_length=220, unique=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "catalog_packages"
        verbose_name = _("Package")
        verbose_name_plural = _("Packages")
        ordering = ["sort_order", "-created_at"]

    def __str__(self) -> str:  # pragma: no cover
        from django.utils.translation import get_language

        rows = {t.locale_code: t.name for t in self.translations.all()}
        lang = (get_language() or "uz")[:2]
        return rows.get(lang) or rows.get("uz") or rows.get("en") or next(iter(rows.values()), str(self.id))


class PackageTranslation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name="translations")
    locale_code = models.CharField(max_length=5, choices=LOCALE_CHOICES)
    name = models.CharField(max_length=128)

    objects = AllObjectsManager()

    def __str__(self) -> str:  # pragma: no cover
        return self.name or str(self.id)

    class Meta:
        db_table = "catalog_package_translations"
        constraints = [models.UniqueConstraint(fields=["package", "locale_code"], name="uq_package_translations_package_locale")]


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------


class Product(SoftDeleteModel):
    """Database Blueprint §4.2 `catalog.products`."""

    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, null=True, blank=True, related_name="products")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, null=True, blank=True, related_name="products")
    status = models.CharField(default=ProductStatus.DRAFT.value, db_index=True, **enum_field_kwargs(ProductStatus))

    # Descriptive text content (domain/entities.py::ProductSpecification's
    # docstring rationale applies identically here: no independent
    # identity/query pattern that would justify a dedicated table).
    # Descriptive text content, per-language (UZ/RU/EN) -- real,
    # product-required capability: these are label-facing legal/usage
    # texts customers read in their own language, not internal-only
    # data. Same "plain field, no dedicated table" architecture
    # decision as before (domain/entities.py::ProductSpecification's
    # docstring rationale applies identically here).
    supplement_facts_text_uz = models.TextField(null=True, blank=True)
    supplement_facts_text_ru = models.TextField(null=True, blank=True)
    supplement_facts_text_en = models.TextField(null=True, blank=True)
    warnings_text_uz = models.TextField(null=True, blank=True)
    warnings_text_ru = models.TextField(null=True, blank=True)
    warnings_text_en = models.TextField(null=True, blank=True)
    directions_text_uz = models.TextField(null=True, blank=True)
    directions_text_ru = models.TextField(null=True, blank=True)
    directions_text_en = models.TextField(null=True, blank=True)
    specifications = models.JSONField(default=list, blank=True)  # list[{"key","value","spec_type","sort_order"}]

    # Real, product-required capability: who made it, where, and how
    # long it stays good for -- distinct from Brand (a marketing/retail
    # identity, e.g. "Optimum Nutrition") vs the actual manufacturing
    # company, which may differ (contract manufacturing is common in
    # this industry). manufacturer_country links to geo.Country
    # (already has a flag icon, see geo/infrastructure/models.py) so
    # the Dashboard can offer a real dropdown instead of free text.
    manufacturer = models.CharField(max_length=255, null=True, blank=True, verbose_name=_("Manufacturer"))
    # Tax codes for fiscal receipts (O'zbekiston: MXIK / IKPU and the package (qadoq) code from tasnif.soliq.uz)
    mxik_code = models.CharField("MXIK (IKPU) kodi", max_length=32, blank=True, default="", help_text="tasnif.soliq.uz dan: fiskal chek uchun majburiy.")
    package_code = models.CharField("Qadoq kodi", max_length=32, blank=True, default="", help_text="MXIK bo'yicha o'lchov/qadoq kodi (tasnif.soliq.uz).")
    manufacturer_country = models.ForeignKey("geo.Country", on_delete=models.SET_NULL, null=True, blank=True, related_name="manufactured_products", verbose_name=_("Country of manufacture"))
    expire_date = models.DateField(null=True, blank=True, verbose_name=_("Product expiry date"))

    # Nutrition facts, embedded (Database Blueprint §4.2 `nutrition_facts`
    # is technically its own table keyed by variant_id; embedded here as
    # JSONB at the product level for this phase since Phase 1's domain
    # model attaches NutritionFacts to Product, not per-variant -- a
    # documented simplification, flagged in the completion report).
    nutrition_serving_size_grams = models.FloatField(null=True, blank=True)
    nutrition_servings_per_container = models.PositiveIntegerField(null=True, blank=True)
    nutrition_calories = models.FloatField(null=True, blank=True)
    nutrition_nutrients = models.JSONField(default=dict, blank=True)

    # SEO (embedded value object -- no separate `product_seo` table in
    # the Blueprint, per domain/value_objects.py::SEOData's docstring).
    seo_meta_title = models.CharField(max_length=70, null=True, blank=True)
    seo_meta_description = models.CharField(max_length=160, null=True, blank=True)

    # Real, product-required relationship: one Flavour tags many
    # Products, one Product carries many Flavours -- `through=
    # ProductFlavour` keeps the same explicit junction table every
    # other Products M2M (ProductTag) already uses, while still giving
    # Django Admin a real, standard `filter_horizontal` widget (the
    # through model carries no fields beyond its own id/created_at, so
    # Django permits this despite the explicit `through=`).
    flavours = models.ManyToManyField("Flavour", through="ProductFlavour", related_name="products", blank=True)
    # Set when this product was grouped into another one (Dashboard → Guruhlash): its old address redirects there.
    merged_into = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="merged_products", editable=False)
    merged_variant_ids = models.JSONField(default=list, blank=True, editable=False)  # the variants that moved with it
    # Training goals this product serves (codes from goals.py) -- "shop by goal" on the storefront.
    goals = models.JSONField(default=list, blank=True, verbose_name=_("Goals"))

    class Meta:
        db_table = "catalog_products"
        verbose_name = _("Product")
        verbose_name_plural = _("Products")
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["brand"]),
            models.Index(fields=["category"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        from django.utils.translation import get_language

        rows = {t.locale_code: t.name for t in self.translations.all()}
        lang = (get_language() or "uz")[:2]
        return rows.get(lang) or rows.get("uz") or rows.get("en") or next(iter(rows.values()), str(self.id))


class ProductTag(models.Model):
    """Database Blueprint §4.2 `catalog.product_tags` -- junction, no independent lifecycle."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="tag_links")
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name="product_links")

    objects = AllObjectsManager()

    class Meta:
        db_table = "catalog_product_tags"
        constraints = [models.UniqueConstraint(fields=["product", "tag"], name="uq_product_tags_product_tag")]


class ProductFlavour(models.Model):
    """Database Blueprint §4.2 amendment `catalog.product_flavours` -- junction, no independent lifecycle. One Flavour tags many Products; one Product carries many Flavours."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="flavour_links")
    flavour = models.ForeignKey(Flavour, on_delete=models.CASCADE, related_name="product_links")

    objects = AllObjectsManager()

    class Meta:
        db_table = "catalog_product_flavours"
        constraints = [models.UniqueConstraint(fields=["product", "flavour"], name="uq_product_flavours_product_flavour")]


class ProductTranslation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="translations")
    locale_code = models.CharField(max_length=5, choices=LOCALE_CHOICES)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    slug = models.SlugField(max_length=220)

    # Real search engine, not a placeholder: kept current by a Postgres
    # trigger (migration 0024), never written from application code --
    # this way it stays correct even for admin bulk edits, data fixes,
    # or migrations that touch `name`/`description` directly in SQL,
    # which an app-level signal would silently miss. `setweight('A')`
    # on name / `('B')` on description (see the trigger body) is what
    # SearchRank below actually ranks by; GinIndex makes that a real
    # index scan instead of a sequential scan over every translation.
    search_vector = SearchVectorField(null=True, editable=False)

    objects = AllObjectsManager()

    def __str__(self) -> str:  # pragma: no cover
        return self.name or str(self.id)

    class Meta:
        db_table = "catalog_product_translations"
        constraints = [
            models.UniqueConstraint(fields=["product", "locale_code"], name="uq_product_translations_product_locale"),
            models.UniqueConstraint(fields=["locale_code", "slug"], name="uq_product_translations_locale_slug"),
        ]
        indexes = [
            models.Index(fields=["locale_code", "slug"]),
            GinIndex(fields=["search_vector"], name="prod_trans_search_gin"),
            # Trigram index on the raw name -- typo-tolerant fallback
            # (e.g. "creatin" / "creatine") for when the tsvector match
            # (exact tokens/stems only) finds nothing.
            GinIndex(fields=["name"], name="prod_trans_name_trgm_gin", opclasses=["gin_trgm_ops"]),
        ]


class ProductVariant(SoftDeleteModel):
    """Database Blueprint §4.2 `catalog.product_variants`."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    sku = models.CharField(max_length=64, unique=True, db_index=True)
    barcode = models.CharField(max_length=14, null=True, blank=True, unique=True)
    status = models.CharField(default=VariantStatus.ACTIVE.value, **enum_field_kwargs(VariantStatus))
    weight_value = models.FloatField(null=True, blank=True)
    weight_unit = models.CharField(default=WeightUnit.GRAM.value, **enum_field_kwargs(WeightUnit))
    package = models.ForeignKey(Package, on_delete=models.SET_NULL, null=True, blank=True, related_name="variants")
    # A product is one family ("Olimp Complex Whey"); each purchasable variant is one size x one flavour, with its
    # own SKU, barcode, price, stock and photos. Product.flavours is kept in step with the variants' flavours.
    flavour = models.ForeignKey(Flavour, on_delete=models.SET_NULL, null=True, blank=True, related_name="variants", verbose_name=_("Flavour"))
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = "catalog_product_variants"
        verbose_name = _("Product Variant")
        verbose_name_plural = _("Product Variants")
        indexes = [models.Index(fields=["product"]), models.Index(fields=["barcode"])]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.product} — {self.sku}"


class ProductVariantBarcode(models.Model):
    """
    Extra barcodes of one product variant. The same product arrives in batches (partiyalar) that often carry a
    different barcode -- a new label from the distributor, a different factory run, a regional pack. Each one points
    to the same variant; the variant's own `barcode` stays the main one. A barcode may be optionally tied to its
    batch number and expiry date, which the goods receipt (Kirim) then fills in automatically when it's scanned.
    Lookups everywhere go through `apps.products.infrastructure.barcodes` (main barcode, then these, then SKU).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name="extra_barcodes", verbose_name=_("Variant"))
    barcode = models.CharField(_("Shtrix-kod"), max_length=32, unique=True, db_index=True)
    batch = models.CharField(_("Partiya raqami"), max_length=64, blank=True, help_text=_("Ixtiyoriy. Kirimda shu shtrix-kod skanerlansa partiya avtomatik yoziladi."))
    expires_at = models.DateField(_("Yaroqlilik muddati"), null=True, blank=True)
    note = models.CharField(_("Izoh"), max_length=120, blank=True, help_text=_("Masalan: 2026-yil mart partiyasi, yangi dizayn qadoq"))
    is_active = models.BooleanField(_("Faol"), default=True)
    added_by = models.CharField(max_length=150, blank=True)

    class Meta:
        db_table = "catalog_product_variant_barcodes"
        verbose_name = _("Qo'shimcha shtrix-kod")
        verbose_name_plural = _("Qo'shimcha shtrix-kodlar")
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover
        return self.barcode


# ---------------------------------------------------------------------------
# Media
# ---------------------------------------------------------------------------


class ProductMedia(BaseModel):
    """
    Database Blueprint §4.2 `catalog.product_media` -- unifies Image/
    Video/Document per that table's actual schema (domain/entities.py
    ::ProductMedia's docstring). Media Asset architecture removed per
    explicit product decision -- direct file storage fields, same
    pattern as Brand/Category/Banner/BlogPost.
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="media")
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, null=True, blank=True, related_name="media")
    storage_path = models.CharField(max_length=500)
    thumbnail_paths = models.JSONField(default=dict, blank=True)
    has_webp_variant = models.BooleanField(default=False)
    width_px = models.PositiveIntegerField(null=True, blank=True)
    height_px = models.PositiveIntegerField(null=True, blank=True)
    checksum_sha256 = models.CharField(max_length=64, blank=True, default="")
    media_role = models.CharField(db_index=True, **enum_field_kwargs(MediaRole))
    sort_order = models.PositiveIntegerField(default=0)
    duration_seconds = models.FloatField(null=True, blank=True)  # video-only
    page_count = models.PositiveIntegerField(null=True, blank=True)  # document-only

    class Meta:
        db_table = "catalog_product_media"
        indexes = [models.Index(fields=["product", "media_role", "sort_order"])]


# ---------------------------------------------------------------------------
# Certificates
# ---------------------------------------------------------------------------


class Certificate(BaseModel):
    """Database Blueprint §4.2 `catalog.certificates`."""

    certificate_type = models.CharField(**enum_field_kwargs(CertificateType))
    issuing_body = models.CharField(max_length=255)
    # Media Asset architecture removed per explicit product decision --
    # direct file storage fields (same pattern as Brand/Category/Banner/
    # BlogPost/ProductMedia).
    document_storage_path = models.CharField(max_length=500, blank=True, default="")
    document_thumbnail_paths = models.JSONField(default=dict, blank=True)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "catalog_certificates"
        indexes = [models.Index(fields=["valid_until"])]


class ProductCertificate(models.Model):
    """Database Blueprint §4.2 `catalog.product_certificates` -- junction."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="certificate_links")
    certificate = models.ForeignKey(Certificate, on_delete=models.CASCADE, related_name="product_links")

    objects = AllObjectsManager()

    class Meta:
        db_table = "catalog_product_certificates"
        constraints = [models.UniqueConstraint(fields=["product", "certificate"], name="uq_product_certificates_product_certificate")]


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------


class ProductRecommendation(BaseModel):
    """Database Blueprint §4.2 `catalog.product_recommendations`."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="recommendations")
    related_product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="recommended_by")
    relation_type = models.CharField(**enum_field_kwargs(RelationType))
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "catalog_product_recommendations"
        constraints = [
            models.UniqueConstraint(fields=["product", "related_product"], name="uq_product_recommendations_product_related"),
            models.CheckConstraint(condition=~models.Q(product=models.F("related_product")), name="ck_product_recommendations_not_self"),
        ]


# ---------------------------------------------------------------------------
# Wishlist
# ---------------------------------------------------------------------------


class WishlistItem(models.Model):
    """A customer's saved-for-later product. No independent lifecycle -- a simple bookmark, not a domain aggregate with business rules (unlike Cart/Order). `customer_id` is a loose reference to `apps.identity.User`, matching this build's own established cross-app convention (e.g. Review.customer_id, ProductRecommendation) rather than a cross-app FK."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer_id = models.UUIDField(db_index=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlist_links")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AllObjectsManager()

    class Meta:
        db_table = "catalog_wishlist_items"
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["customer_id", "product"], name="uq_wishlist_items_customer_product")]

    def __str__(self) -> str:  # pragma: no cover
        return f"WishlistItem(customer={self.customer_id}, product={self.product_id})"


# ---------------------------------------------------------------------------
# Outbox
# ---------------------------------------------------------------------------


class ProductsOutboxEvent(AbstractOutboxEvent):
    """Concrete Outbox table for the `catalog` schema (Database Blueprint §6's 'note on the Outbox table itself')."""

    class Meta:
        db_table = "catalog_outbox_events"
        ordering = ["created_at"]
