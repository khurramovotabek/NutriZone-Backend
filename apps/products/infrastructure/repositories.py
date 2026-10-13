"""
Products repositories.

Concrete implementations of application/ports.py's Protocols. Every
method translates between the ORM row shape and the plain domain
dataclasses (domain/aggregates.py, domain/entities.py), and catches
ORM-level exceptions, re-raising as the matching domain exception --
matching the pattern established by
`apps/identity/infrastructure/repositories.py`.

Locale handling: `_DEFAULT_LOCALE` ("en") is the working locale
`ProductRepository`/`CategoryRepository`/etc. hydrate a domain
aggregate's `name`/`slug` from when loading for a *write* operation
(an Application Service mutating a product doesn't need every locale
loaded into memory). Locale-aware, multi-language read models are a
selector-layer concern (infrastructure/selectors.py), not this
repository layer's job -- this mirrors the Database Blueprint's own
translation-table design, where the base table has no `name` column at
all and every locale is equally "the" data.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from django.db import IntegrityError
from django.db.models import Q

from apps.products.domain.aggregates import (
    Brand as BrandAgg,
)
from apps.products.domain.aggregates import (
    Category as CategoryAgg,
)
from apps.products.domain.aggregates import (
    Flavour as FlavourAgg,
)
from apps.products.domain.aggregates import (
    Package as PackageAgg,
)
from apps.products.domain.aggregates import (
    Product,
    ProductVariant,
)
from apps.products.domain.aggregates import (
    Tag as TagAgg,
)
from apps.products.domain.entities import Certificate, ProductMedia
from apps.products.domain.enums import CertificateType, MediaRole, ProductStatus, VariantStatus, WeightUnit
from apps.products.domain.value_objects import (
    SKU,
    Barcode,
    DocumentMetadata,
    ImageMetadata,
    NutritionFacts,
    SEOData,
    ServingSize,
    Slug,
    VideoMetadata,
)
from apps.products.infrastructure import models as orm
from common.exceptions import ConflictError

_DEFAULT_LOCALE = "en"


# --- mapping helpers -------------------------------------------------


def _product_to_domain(row: orm.Product) -> Product:
    translation = row.translations.filter(locale_code=_DEFAULT_LOCALE).first()
    name = translation.name if translation else ""
    slug_value = translation.slug if translation else str(row.id)
    description = translation.description if translation else None

    variants = {}
    for v in row.variants.all():
        variants[v.id] = ProductVariant(
            id=v.id, sku=SKU(v.sku), status=VariantStatus(v.status),
            barcode=Barcode(v.barcode) if v.barcode else None, weight_value=v.weight_value,
            weight_unit=WeightUnit(v.weight_unit), package_id=v.package_id, is_default=v.is_default,
        )

    media = {}
    for m in row.media.all():
        image_meta = None
        video_meta = None
        if m.media_role in (MediaRole.PRIMARY.value, MediaRole.GALLERY.value) and m.width_px:
            image_meta = ImageMetadata(width_px=m.width_px, height_px=m.height_px or 0, checksum_sha256=m.checksum_sha256)
        elif m.media_role == MediaRole.VIDEO.value and m.duration_seconds:
            video_meta = VideoMetadata(duration_seconds=m.duration_seconds, checksum_sha256=m.checksum_sha256)
        media[m.id] = ProductMedia(
            id=m.id, media_id=m.id, media_role=MediaRole(m.media_role), storage_path=m.storage_path, thumbnail_paths=m.thumbnail_paths, sort_order=m.sort_order,
            variant_id=m.variant_id, image_metadata=image_meta, video_metadata=video_meta,
        )

    certificates = tuple(
        Certificate(
            id=link.certificate.id, certificate_type=CertificateType(link.certificate.certificate_type),
            issuing_body=link.certificate.issuing_body, document_media_id=link.certificate.id,
            valid_from=link.certificate.valid_from, valid_until=link.certificate.valid_until,
        )
        for link in row.certificate_links.select_related("certificate").all()
    )

    nutrition_facts = None
    if row.nutrition_calories is not None and row.nutrition_serving_size_grams is not None:
        nutrition_facts = NutritionFacts(
            serving_size=ServingSize(amount_grams=row.nutrition_serving_size_grams, servings_per_container=row.nutrition_servings_per_container or 1),
            calories=row.nutrition_calories, nutrients=row.nutrition_nutrients or {},
        )

    tag_ids = frozenset(row.tag_links.values_list("tag_id", flat=True))
    flavour_ids = frozenset(row.flavour_links.values_list("flavour_id", flat=True))

    return Product(
        id=row.id, slug=Slug(slug_value), name=name, brand_id=row.brand_id, category_id=row.category_id,
        status=ProductStatus(row.status), description=description, tag_ids=tag_ids, flavour_ids=flavour_ids, certificates=certificates,
        nutrition_facts=nutrition_facts,
        supplement_facts_text_uz=row.supplement_facts_text_uz, supplement_facts_text_ru=row.supplement_facts_text_ru, supplement_facts_text_en=row.supplement_facts_text_en,
        warnings_text_uz=row.warnings_text_uz, warnings_text_ru=row.warnings_text_ru, warnings_text_en=row.warnings_text_en,
        directions_text_uz=row.directions_text_uz, directions_text_ru=row.directions_text_ru, directions_text_en=row.directions_text_en,
        seo=SEOData(meta_title=row.seo_meta_title, meta_description=row.seo_meta_description, canonical_slug=Slug(slug_value)),
        variants=variants, media=media, created_at=row.created_at,
    )


class DjangoProductRepository:
    def get_by_id(self, product_id: uuid.UUID) -> Product | None:
        row = orm.Product.objects.filter(id=product_id).prefetch_related(
            "translations", "variants", "media", "certificate_links__certificate", "tag_links", "flavour_links"
        ).first()
        return _product_to_domain(row) if row else None

    def get_by_slug(self, slug: str) -> Product | None:
        translation = orm.ProductTranslation.objects.filter(slug=slug).select_related("product").first()
        return self.get_by_id(translation.product_id) if translation else None

    def save(self, product: Product) -> Product:
        try:
            row, _created = orm.Product.objects.update_or_create(
                id=product.id,
                defaults={
                    "brand_id": product.brand_id, "category_id": product.category_id, "status": product.status.value,
                    "supplement_facts_text_uz": product.supplement_facts_text_uz, "supplement_facts_text_ru": product.supplement_facts_text_ru, "supplement_facts_text_en": product.supplement_facts_text_en,
                    "warnings_text_uz": product.warnings_text_uz, "warnings_text_ru": product.warnings_text_ru, "warnings_text_en": product.warnings_text_en,
                    "directions_text_uz": product.directions_text_uz, "directions_text_ru": product.directions_text_ru, "directions_text_en": product.directions_text_en,
                    "nutrition_serving_size_grams": product.nutrition_facts.serving_size.amount_grams if product.nutrition_facts else None,
                    "nutrition_servings_per_container": product.nutrition_facts.serving_size.servings_per_container if product.nutrition_facts else None,
                    "nutrition_calories": product.nutrition_facts.calories if product.nutrition_facts else None,
                    "nutrition_nutrients": product.nutrition_facts.nutrients if product.nutrition_facts else {},
                    "seo_meta_title": product.seo.meta_title, "seo_meta_description": product.seo.meta_description,
                },
            )
        except IntegrityError as exc:
            raise ConflictError("A product with conflicting unique fields already exists.") from exc

        orm.ProductTranslation.objects.update_or_create(
            product=row, locale_code=_DEFAULT_LOCALE,
            defaults={"name": product.name, "description": product.description or "", "slug": product.slug.value},
        )

        self._sync_variants(row, product)
        self._sync_media(row, product)
        self._sync_tags(row, product)
        self._sync_flavours(row, product)

        return product

    def _sync_variants(self, row: orm.Product, product: Product) -> None:
        existing_ids = set(row.variants.values_list("id", flat=True))
        current_ids = set(product.variants.keys())

        for stale_id in existing_ids - current_ids:
            orm.ProductVariant.objects.filter(id=stale_id).delete()

        for variant in product.variants.values():
            orm.ProductVariant.objects.update_or_create(
                id=variant.id,
                defaults={
                    "product": row, "sku": variant.sku.value, "barcode": variant.barcode.value if variant.barcode else None,
                    "status": variant.status.value, "weight_value": variant.weight_value, "weight_unit": variant.weight_unit.value,
                    "package_id": variant.package_id, "is_default": variant.is_default,
                },
            )

    def _sync_media(self, row: orm.Product, product: Product) -> None:
        existing_ids = set(row.media.values_list("id", flat=True))
        current_ids = set(product.media.keys())

        for stale_id in existing_ids - current_ids:
            orm.ProductMedia.objects.filter(id=stale_id).delete()

        for media in product.media.values():
            duration = media.video_metadata.duration_seconds if media.video_metadata else None
            width_px = media.image_metadata.width_px if media.image_metadata else None
            height_px = media.image_metadata.height_px if media.image_metadata else None
            checksum = (media.image_metadata.checksum_sha256 if media.image_metadata else None) or (media.video_metadata.checksum_sha256 if media.video_metadata else None) or ""
            orm.ProductMedia.objects.update_or_create(
                id=media.id,
                defaults={
                    "product": row, "variant_id": media.variant_id, "storage_path": media.storage_path, "thumbnail_paths": media.thumbnail_paths,
                    "width_px": width_px, "height_px": height_px, "checksum_sha256": checksum,
                    "media_role": media.media_role.value, "sort_order": media.sort_order, "duration_seconds": duration,
                },
            )

    def _sync_tags(self, row: orm.Product, product: Product) -> None:
        row.tag_links.exclude(tag_id__in=product.tag_ids).delete()
        for tag_id in product.tag_ids:
            orm.ProductTag.objects.get_or_create(product=row, tag_id=tag_id)

    def _sync_flavours(self, row: orm.Product, product: Product) -> None:
        row.flavour_links.exclude(flavour_id__in=product.flavour_ids).delete()
        for flavour_id in product.flavour_ids:
            orm.ProductFlavour.objects.get_or_create(product=row, flavour_id=flavour_id)

    def slug_exists(self, slug: str, exclude_product_id: uuid.UUID | None = None) -> bool:
        qs = orm.ProductTranslation.objects.filter(slug=slug, locale_code=_DEFAULT_LOCALE)
        if exclude_product_id is not None:
            qs = qs.exclude(product_id=exclude_product_id)
        return qs.exists()

    def sku_exists(self, sku: str, exclude_product_id: uuid.UUID | None = None) -> bool:
        qs = orm.ProductVariant.objects.filter(sku=sku)
        if exclude_product_id is not None:
            qs = qs.exclude(product_id=exclude_product_id)
        return qs.exists()

    def barcode_exists(self, barcode: str, exclude_product_id: uuid.UUID | None = None) -> bool:
        """A main barcode may not reuse a code that is already a variant's main barcode or any extra (batch) barcode."""
        qs = orm.ProductVariant.objects.filter(barcode=barcode)
        extra = orm.ProductVariantBarcode.objects.filter(barcode=barcode)
        if exclude_product_id is not None:
            qs = qs.exclude(product_id=exclude_product_id)
            extra = extra.exclude(variant__product_id=exclude_product_id)
        return qs.exists() or extra.exists()

    def list_public(self, category_id=None, brand_id=None, tag_ids=None, query=None, page=1, page_size=20, ordering="-created_at") -> tuple[list[Product], int]:
        qs = orm.Product.objects.filter(status=ProductStatus.PUBLISHED.value)
        if category_id:
            qs = qs.filter(category_id=category_id)
        if brand_id:
            qs = qs.filter(brand_id=brand_id)
        if tag_ids:
            qs = qs.filter(tag_links__tag_id__in=tag_ids).distinct()
        if query:
            qs = qs.filter(translations__locale_code=_DEFAULT_LOCALE, translations__name__icontains=query)
        total = qs.count()
        start = (page - 1) * page_size
        rows = qs.order_by(ordering)[start : start + page_size]
        return [self.get_by_id(r.id) for r in rows], total

    def list_for_admin(self, status=None, query=None, page=1, page_size=20) -> tuple[list[Product], int]:
        qs = orm.Product.objects.all()
        if status:
            qs = qs.filter(status=status)
        if query:
            qs = qs.filter(translations__locale_code=_DEFAULT_LOCALE, translations__name__icontains=query)
        total = qs.count()
        start = (page - 1) * page_size
        rows = qs.order_by("-created_at")[start : start + page_size]
        return [self.get_by_id(r.id) for r in rows], total

    def delete(self, product_id: uuid.UUID) -> None:
        row = orm.Product.objects.filter(id=product_id).first()
        if row is not None:
            row.delete()  # soft delete, per common/models/base.py


class DjangoBrandRepository:
    def get_by_id(self, brand_id: uuid.UUID) -> BrandAgg | None:
        row = orm.Brand.objects.filter(id=brand_id, is_manufacturer=False).first()
        return self._to_domain(row) if row else None

    def get_by_slug(self, slug: str) -> BrandAgg | None:
        translation = orm.BrandTranslation.objects.filter(slug=slug).select_related("brand").first()
        return self._to_domain(translation.brand) if translation else None

    def save(self, brand: BrandAgg) -> BrandAgg:
        row, _ = orm.Brand.objects.update_or_create(id=brand.id, defaults={"is_active": brand.is_active, "is_manufacturer": brand.is_manufacturer})
        orm.BrandTranslation.objects.update_or_create(brand=row, locale_code=_DEFAULT_LOCALE, defaults={"name": brand.name, "slug": brand.slug.value})
        return brand

    def slug_exists(self, slug: str, exclude_brand_id: uuid.UUID | None = None) -> bool:
        qs = orm.BrandTranslation.objects.filter(slug=slug, locale_code=_DEFAULT_LOCALE)
        if exclude_brand_id is not None:
            qs = qs.exclude(brand_id=exclude_brand_id)
        return qs.exists()

    def list_active(self) -> list[BrandAgg]:
        return [self._to_domain(r) for r in orm.Brand.objects.filter(is_active=True, is_manufacturer=False)]

    def _to_domain(self, row: orm.Brand) -> BrandAgg:
        t = row.translations.filter(locale_code=_DEFAULT_LOCALE).first()
        return BrandAgg(id=row.id, slug=Slug(t.slug if t else str(row.id)), name=t.name if t else "", is_active=row.is_active, is_manufacturer=row.is_manufacturer)


class DjangoManufacturerRepository:
    """Scoped to `is_manufacturer=True` -- see domain/aggregates.py::Manufacturer."""

    def get_by_id(self, manufacturer_id: uuid.UUID) -> BrandAgg | None:
        row = orm.Brand.objects.filter(id=manufacturer_id, is_manufacturer=True).first()
        return DjangoBrandRepository()._to_domain(row) if row else None

    def save(self, manufacturer: BrandAgg) -> BrandAgg:
        return DjangoBrandRepository().save(manufacturer)

    def list_active(self) -> list[BrandAgg]:
        return [DjangoBrandRepository()._to_domain(r) for r in orm.Brand.objects.filter(is_active=True, is_manufacturer=True)]


class DjangoCategoryRepository:
    def get_by_id(self, category_id: uuid.UUID) -> CategoryAgg | None:
        row = orm.Category.objects.filter(id=category_id).first()
        return self._to_domain(row) if row else None

    def get_by_slug(self, slug: str) -> CategoryAgg | None:
        t = orm.CategoryTranslation.objects.filter(slug=slug).select_related("category").first()
        return self._to_domain(t.category) if t else None

    def save(self, category: CategoryAgg) -> CategoryAgg:
        row, _ = orm.Category.objects.update_or_create(
            id=category.id, defaults={"parent_id": category.parent_id, "sort_order": category.sort_order, "is_active": category.is_active}
        )
        orm.CategoryTranslation.objects.update_or_create(category=row, locale_code=_DEFAULT_LOCALE, defaults={"name": category.name, "slug": category.slug.value})
        return category

    def slug_exists(self, slug: str, exclude_category_id: uuid.UUID | None = None) -> bool:
        qs = orm.CategoryTranslation.objects.filter(slug=slug, locale_code=_DEFAULT_LOCALE)
        if exclude_category_id is not None:
            qs = qs.exclude(category_id=exclude_category_id)
        return qs.exists()

    def list_tree(self) -> list[CategoryAgg]:
        return [self._to_domain(r) for r in orm.Category.objects.filter(is_active=True).order_by("sort_order")]

    def _to_domain(self, row: orm.Category) -> CategoryAgg:
        t = row.translations.filter(locale_code=_DEFAULT_LOCALE).first()
        return CategoryAgg(id=row.id, slug=Slug(t.slug if t else str(row.id)), name=t.name if t else "", parent_id=row.parent_id, sort_order=row.sort_order, is_active=row.is_active)


class DjangoVariantRepository:
    def get_product_id_for_variant(self, variant_id: uuid.UUID) -> uuid.UUID | None:
        row = orm.ProductVariant.objects.filter(id=variant_id).only("product_id").first()
        return row.product_id if row else None

    def get_by_sku(self, sku: str) -> tuple[uuid.UUID, uuid.UUID] | None:
        row = orm.ProductVariant.objects.filter(sku=sku).only("id", "product_id").first()
        return (row.product_id, row.id) if row else None

    def get_by_barcode(self, barcode: str) -> tuple[uuid.UUID, uuid.UUID] | None:
        """Mirrors `get_by_sku()` exactly -- added for the POS Search module's explicitly authorized minimal cross-context extension. `barcode` already has `unique=True` and a dedicated index (`Meta.indexes`), re-verified directly before this change; no new index was added."""
        row = orm.ProductVariant.objects.filter(barcode=barcode).only("id", "product_id").first()
        if row is None:  # an extra (batch) barcode of the variant
            extra = orm.ProductVariantBarcode.objects.filter(barcode=barcode, is_active=True, variant__is_deleted=False).select_related("variant").first()
            row = extra.variant if extra else None
        return (row.product_id, row.id) if row else None


class DjangoFlavourRepository:
    def get_by_id(self, flavour_id: uuid.UUID) -> FlavourAgg | None:
        row = orm.Flavour.objects.filter(id=flavour_id).first()
        return self._to_domain(row) if row else None

    def get_by_slug(self, slug: str) -> FlavourAgg | None:
        row = orm.Flavour.objects.filter(slug=slug).first()
        return self._to_domain(row) if row else None

    def get_many_by_ids(self, flavour_ids: frozenset[uuid.UUID]) -> list[FlavourAgg]:
        return [self._to_domain(r) for r in orm.Flavour.objects.filter(id__in=flavour_ids)]

    def save(self, flavour: FlavourAgg) -> FlavourAgg:
        row, _ = orm.Flavour.objects.update_or_create(
            id=flavour.id,
            defaults={"slug": flavour.slug.value, "color_hex": flavour.color_hex, "sort_order": flavour.sort_order, "is_active": flavour.is_active},
        )
        orm.FlavourTranslation.objects.update_or_create(flavour=row, locale_code=_DEFAULT_LOCALE, defaults={"name": flavour.name})
        return flavour

    def list_active(self) -> list[FlavourAgg]:
        return [self._to_domain(r) for r in orm.Flavour.objects.filter(is_active=True)]

    def _to_domain(self, row: orm.Flavour) -> FlavourAgg:
        t = row.translations.filter(locale_code=_DEFAULT_LOCALE).first()
        return FlavourAgg(id=row.id, slug=Slug(row.slug), name=t.name if t else row.slug, color_hex=row.color_hex, sort_order=row.sort_order, is_active=row.is_active)


class DjangoPackageRepository:
    def get_by_id(self, package_id: uuid.UUID) -> PackageAgg | None:
        row = orm.Package.objects.filter(id=package_id).first()
        return self._to_domain(row) if row else None

    def get_by_slug(self, slug: str) -> PackageAgg | None:
        row = orm.Package.objects.filter(slug=slug).first()
        return self._to_domain(row) if row else None

    def save(self, package: PackageAgg) -> PackageAgg:
        row, _ = orm.Package.objects.update_or_create(
            id=package.id, defaults={"slug": package.slug.value, "sort_order": package.sort_order, "is_active": package.is_active},
        )
        orm.PackageTranslation.objects.update_or_create(package=row, locale_code=_DEFAULT_LOCALE, defaults={"name": package.name})
        return package

    def list_active(self) -> list[PackageAgg]:
        return [self._to_domain(r) for r in orm.Package.objects.filter(is_active=True)]

    def _to_domain(self, row: orm.Package) -> PackageAgg:
        t = row.translations.filter(locale_code=_DEFAULT_LOCALE).first()
        return PackageAgg(id=row.id, slug=Slug(row.slug), name=t.name if t else row.slug, sort_order=row.sort_order, is_active=row.is_active)


class DjangoMediaRepository:
    def get_product_id_for_media(self, media_id: uuid.UUID) -> uuid.UUID | None:
        row = orm.ProductMedia.objects.filter(id=media_id).only("product_id").first()
        return row.product_id if row else None


class DjangoTagRepository:
    def get_by_code(self, code: str) -> TagAgg | None:
        row = orm.Tag.objects.filter(code=code).first()
        return self._to_domain(row) if row else None

    def get_many_by_ids(self, tag_ids: frozenset[uuid.UUID]) -> list[TagAgg]:
        return [self._to_domain(r) for r in orm.Tag.objects.filter(id__in=tag_ids)]

    def save(self, tag: TagAgg) -> TagAgg:
        row, _ = orm.Tag.objects.update_or_create(id=tag.id, defaults={"code": tag.code})
        orm.TagTranslation.objects.update_or_create(tag=row, locale_code=_DEFAULT_LOCALE, defaults={"name": tag.name})
        return tag

    def list_all(self) -> list[TagAgg]:
        return [self._to_domain(r) for r in orm.Tag.objects.all()]

    def _to_domain(self, row: orm.Tag) -> TagAgg:
        t = row.translations.filter(locale_code=_DEFAULT_LOCALE).first()
        return TagAgg(id=row.id, code=row.code, name=t.name if t else row.code)


class DjangoSpecificationRepository:
    def list_distinct_keys(self) -> list[str]:
        keys: set[str] = set()
        for specs in orm.Product.objects.exclude(specifications=[]).values_list("specifications", flat=True):
            keys.update(spec.get("key") for spec in specs if isinstance(spec, dict) and spec.get("key"))
        return sorted(keys)


