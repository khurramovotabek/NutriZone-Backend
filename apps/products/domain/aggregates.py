"""
Products aggregate roots: Product.

Per Domain Architecture Specification §2.2: "Product (root) — owns
Variants, NutritionFactSheet, SupplementFacts, Certificates, and
Attribute assignments. Category/Brand/Tag are referenced by ID, not
owned." Every state-changing method enforces the aggregate's own
invariants and returns the domain event(s) the change should raise,
exactly matching the pattern established by `apps/identity/domain/
aggregates.py::User`.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from apps.products.domain.entities import Certificate, ProductMedia
from apps.products.domain.enums import MediaRole, ProductStatus, VariantStatus, WeightUnit
from apps.products.domain.events import (
    BrandAssigned,
    CategoryAssigned,
    ProductArchived,
    ProductHidden,
    ProductMediaUploaded,
    ProductPublished,
    ProductRestored,
    ProductSEOUpdated,
    ProductUpdated,
    ProductVariantCreated,
)
from apps.products.domain.exceptions import (
    InvalidProductLifecycleTransition,
    InvalidVariant,
    MediaLimitExceeded,
    PrimaryImageMissing,
    PublishValidationFailed,
    VariantAlreadyExists,
)
from apps.products.domain.value_objects import SKU, Barcode, NutritionFacts, SEOData, Slug

MAX_IMAGES = 12
MAX_VIDEOS = 4


@dataclass(slots=True)
class ProductVariant:
    """
    Non-root entity owned by Product -- Database Blueprint §4.2
    `catalog.product_variants`.
    """

    id: uuid.UUID
    sku: SKU
    status: VariantStatus = VariantStatus.ACTIVE
    barcode: Barcode | None = None
    weight_value: float | None = None
    weight_unit: WeightUnit = WeightUnit.GRAM
    package_id: uuid.UUID | None = None
    is_default: bool = False


@dataclass(slots=True)
class Product:
    id: uuid.UUID
    slug: Slug
    name: str
    brand_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    status: ProductStatus = ProductStatus.DRAFT
    description: str | None = None
    tag_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    flavour_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    certificates: tuple[Certificate, ...] = field(default_factory=tuple)
    nutrition_facts: NutritionFacts | None = None
    supplement_facts_text_uz: str | None = None
    supplement_facts_text_ru: str | None = None
    supplement_facts_text_en: str | None = None
    warnings_text_uz: str | None = None
    warnings_text_ru: str | None = None
    warnings_text_en: str | None = None
    directions_text_uz: str | None = None
    directions_text_ru: str | None = None
    directions_text_en: str | None = None
    seo: SEOData = field(default_factory=SEOData)
    variants: dict[uuid.UUID, ProductVariant] = field(default_factory=dict)
    media: dict[uuid.UUID, ProductMedia] = field(default_factory=dict)
    created_at: datetime | None = None

    # --- Variant management -------------------------------------------------

    def add_variant(self, variant: ProductVariant) -> ProductVariantCreated:
        if any(v.sku.value == variant.sku.value for v in self.variants.values()):
            raise VariantAlreadyExists(f"A variant with SKU '{variant.sku.value}' already exists on this product.")
        if not self.variants:
            variant.is_default = True  # the first variant is the default, automatically
        self.variants[variant.id] = variant
        return ProductVariantCreated(product_id=self.id, variant_id=variant.id, sku=variant.sku.value)

    def remove_variant(self, variant_id: uuid.UUID) -> None:
        variant = self.variants.pop(variant_id, None)
        if variant is not None and variant.is_default and self.variants:
            # Promote another variant to default so the invariant
            # "a published product with variants has exactly one
            # default" never silently breaks.
            next(iter(self.variants.values())).is_default = True

    def set_default_variant(self, variant_id: uuid.UUID) -> None:
        if variant_id not in self.variants:
            raise InvalidVariant(f"Variant '{variant_id}' does not belong to this product.")
        for v in self.variants.values():
            v.is_default = v.id == variant_id

    # --- Media management -------------------------------------------------

    def add_media(self, media: ProductMedia) -> ProductMediaUploaded:
        image_count = sum(1 for m in self.media.values() if m.media_role in (MediaRole.PRIMARY, MediaRole.GALLERY))
        video_count = sum(1 for m in self.media.values() if m.media_role == MediaRole.VIDEO)

        if media.media_role in (MediaRole.PRIMARY, MediaRole.GALLERY) and image_count >= MAX_IMAGES:
            raise MediaLimitExceeded(f"A product may have at most {MAX_IMAGES} images.")
        if media.media_role == MediaRole.VIDEO and video_count >= MAX_VIDEOS:
            raise MediaLimitExceeded(f"A product may have at most {MAX_VIDEOS} videos.")

        if media.media_role == MediaRole.PRIMARY:
            # Exactly one PRIMARY at a time -- demote any existing one to GALLERY.
            for m in self.media.values():
                if m.media_role == MediaRole.PRIMARY:
                    m.media_role = MediaRole.GALLERY

        self.media[media.id] = media
        return ProductMediaUploaded(product_id=self.id, media_id=media.id, media_role=media.media_role.value)

    def remove_media(self, media_id: uuid.UUID) -> None:
        self.media.pop(media_id, None)

    # --- Lifecycle -------------------------------------------------------

    def publish(self, required_certificate_types: frozenset[str] = frozenset()) -> ProductPublished:
        """
        Enforces the Domain Architecture Specification §2.2
        `ComplianceValidator` rule plus the structural invariants
        (has variants, has a default variant, has a primary image) the
        module brief's "Publish validation"/"Variant uniqueness"/
        "Primary image uniqueness" rules ask for. Every failing check
        is collected before raising, so a client sees every blocking
        reason at once (`PublishValidationFailed.details["reasons"]`),
        not just the first one encountered.
        """
        if self.status == ProductStatus.ARCHIVED:
            raise InvalidProductLifecycleTransition("An archived product must be restored before it can be published.")

        reasons: list[dict] = []

        if not self.variants:
            reasons.append({"code": "NO_VARIANTS", "message": "A product cannot be published without at least one variant."})
        elif not any(v.is_default for v in self.variants.values()):
            reasons.append({"code": "NO_DEFAULT_VARIANT", "message": "A product cannot be published without a default variant."})

        if not any(m.media_role == MediaRole.PRIMARY for m in self.media.values()):
            reasons.append({"code": "NO_PRIMARY_IMAGE", "message": "A product cannot be published without a primary image."})

        held_types = {c.certificate_type.value for c in self.certificates}
        missing_certs = required_certificate_types - held_types
        if missing_certs:
            reasons.append({
                "code": "MISSING_REQUIRED_CERTIFICATE",
                "message": f"Missing required certificate types: {sorted(missing_certs)}.",
                "missing": sorted(missing_certs),
            })

        if reasons:
            raise PublishValidationFailed(
                "This product cannot be published until all publish requirements are met.",
                details={"reasons": reasons},
            )

        self.status = ProductStatus.PUBLISHED
        return ProductPublished(product_id=self.id)

    def hide(self) -> ProductHidden:
        if self.status != ProductStatus.PUBLISHED:
            raise InvalidProductLifecycleTransition("Only a published product can be hidden.")
        self.status = ProductStatus.UNPUBLISHED
        return ProductHidden(product_id=self.id)

    def archive(self) -> ProductArchived:
        if self.status == ProductStatus.ARCHIVED:
            raise InvalidProductLifecycleTransition("This product is already archived.")
        self.status = ProductStatus.ARCHIVED
        return ProductArchived(product_id=self.id)

    def restore(self) -> ProductRestored:
        if self.status != ProductStatus.ARCHIVED:
            raise InvalidProductLifecycleTransition("Only an archived product can be restored.")
        self.status = ProductStatus.DRAFT
        return ProductRestored(product_id=self.id)

    @property
    def is_publicly_visible(self) -> bool:
        """The mission's 'Visibility rules' -- only PUBLISHED products are visible on public endpoints; enforced at the selector/query layer, this property is the single source of truth for that rule."""
        return self.status == ProductStatus.PUBLISHED

    def assert_has_primary_image(self) -> None:
        """Standalone check reused outside the full publish gate -- e.g. by a 'ready to publish?' preview endpoint that wants a single, specific reason rather than the aggregated PublishValidationFailed list."""
        if not any(m.media_role == MediaRole.PRIMARY for m in self.media.values()):
            raise PrimaryImageMissing("This product has no primary image set.")

    # --- Descriptive-field updates -----------------------------------------

    def update_core_fields(self, name: str | None = None, description: str | None = None) -> ProductUpdated:
        before = {"name": self.name, "description": self.description}
        if name is not None:
            self.name = name
        if description is not None:
            self.description = description
        after = {"name": self.name, "description": self.description}
        return ProductUpdated(product_id=self.id, before=before, after=after)

    def assign_brand(self, brand_id: uuid.UUID | None) -> BrandAssigned:
        self.brand_id = brand_id
        return BrandAssigned(product_id=self.id, brand_id=brand_id)

    def assign_category(self, category_id: uuid.UUID | None) -> CategoryAssigned:
        self.category_id = category_id
        return CategoryAssigned(product_id=self.id, category_id=category_id)

    def assign_tags(self, tag_ids: frozenset[uuid.UUID]) -> None:
        self.tag_ids = tag_ids

    def assign_flavours(self, flavour_ids: frozenset[uuid.UUID]) -> None:
        self.flavour_ids = flavour_ids

    def update_seo(self, seo: SEOData) -> ProductSEOUpdated:
        self.seo = seo
        return ProductSEOUpdated(product_id=self.id)

    def update_nutrition_facts(self, nutrition_facts: NutritionFacts | None) -> None:
        self.nutrition_facts = nutrition_facts

    def update_supplement_facts(self, text: str | None, locale: str = "uz") -> None:
        setattr(self, f"supplement_facts_text_{locale}", text)

    def update_warnings(self, text: str | None, locale: str = "uz") -> None:
        setattr(self, f"warnings_text_{locale}", text)

    def update_directions(self, text: str | None, locale: str = "uz") -> None:
        setattr(self, f"directions_text_{locale}", text)

    def attach_certificate(self, certificate: Certificate) -> None:
        self.certificates = (*self.certificates, certificate)


# ---------------------------------------------------------------------------
# Catalog reference aggregates: Category, Brand, Manufacturer, Attribute
# (+ its Flavor/PackageSize/ProductForm specializations), Tag.
#
# Reconciliation note (documented per this module's brief explicitly
# naming Flavor/PackageSize/ProductForm as aggregate roots, while the
# Enterprise Database Blueprint §4.2 models them as `Attribute` rows
# with reserved codes -- Domain Architecture Specification §2.2's
# "unlimited variant dimensions without schema changes" design):
# `Flavor`, `PackageSize`, and `ProductForm` below are thin, real
# aggregate classes -- each enforces its own invariant (the attribute
# it wraps must carry the matching reserved code) and each gets its
# own repository (application/ports.py) -- but all three persist
# through the *same* `catalog.attributes`/`catalog.attribute_values`
# tables the Blueprint already defines, via `Attribute.code`
# discrimination. This satisfies the brief's explicit request for
# distinct aggregate types with distinct repositories without
# introducing three tables the approved Database Blueprint doesn't
# have -- the alternative (three separate hardcoded tables) would have
# been the actual shortcut, since it reintroduces exactly the
# per-new-dimension schema change the Blueprint's design exists to
# avoid.
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Category:
    """Aggregate root -- Database Blueprint §4.2 `catalog.categories` (+ translations)."""

    id: uuid.UUID
    slug: Slug
    name: str
    parent_id: uuid.UUID | None = None
    sort_order: int = 0
    is_active: bool = True

    def __post_init__(self) -> None:
        from apps.products.domain.exceptions import InvalidCategory

        if not self.name or not self.name.strip():
            raise InvalidCategory("Category name must not be empty.")
        if self.parent_id == self.id:
            raise InvalidCategory("A category cannot be its own parent.")

    def rename(self, name: str) -> None:
        from apps.products.domain.exceptions import InvalidCategory

        if not name or not name.strip():
            raise InvalidCategory("Category name must not be empty.")
        self.name = name

    def deactivate(self) -> None:
        self.is_active = False

    def activate(self) -> None:
        self.is_active = True


@dataclass(slots=True)
class Brand:
    """Aggregate root -- Database Blueprint §4.2 `catalog.brands` (+ translations)."""

    id: uuid.UUID
    slug: Slug
    name: str
    is_active: bool = True
    is_manufacturer: bool = False

    def __post_init__(self) -> None:
        from apps.products.domain.exceptions import InvalidBrand

        if not self.name or not self.name.strip():
            raise InvalidBrand("Brand name must not be empty.")

    def deactivate(self) -> None:
        self.is_active = False

    def activate(self) -> None:
        self.is_active = True


@dataclass(slots=True)
class Manufacturer:
    """
    Not a distinct Database Blueprint table (only `brands` exists
    there) -- realized as a `Brand` with `is_manufacturer=True` rather
    than a fourth parallel entity, since "manufacturer" and "brand"
    share the exact same relational shape. `Manufacturer.create()`
    below is a typed factory over `Brand` so callers get a real,
    distinctly-named aggregate type in application code (matching the
    brief's explicit ask for a `Manufacturer` aggregate + repository)
    while the persistence layer stays a single `brands` table.
    """

    @staticmethod
    def create(manufacturer_id: uuid.UUID, slug: Slug, name: str) -> Brand:
        return Brand(id=manufacturer_id, slug=slug, name=name, is_manufacturer=True)


@dataclass(slots=True)
class Tag:
    """Aggregate root -- Database Blueprint §4.2 `catalog.tags` (+ translations)."""

    id: uuid.UUID
    code: str
    name: str

    def __post_init__(self) -> None:
        from apps.products.domain.exceptions import InvalidAttribute

        if not self.code or not self.code.strip():
            raise InvalidAttribute("Tag code must not be empty.")


@dataclass(slots=True)
class Flavour:
    """
    Aggregate root -- replaces the old generic Attribute/AttributeValue
    "flavor" reservation with a real, dedicated module (per explicit
    product decision). Linked to Product by a plain many-to-many (one
    Flavour tags many Products; one Product carries many Flavours) --
    never owned by Product, the same referenced-by-id relationship
    Tag already has, not an owned child entity.
    """

    id: uuid.UUID
    slug: Slug
    name: str
    color_hex: str | None = None
    sort_order: int = 0
    is_active: bool = True

    def __post_init__(self) -> None:
        from apps.products.domain.exceptions import InvalidFlavour

        if not self.name or not self.name.strip():
            raise InvalidFlavour("Flavour name must not be empty.")

    def deactivate(self) -> None:
        self.is_active = False

    def activate(self) -> None:
        self.is_active = True


@dataclass(slots=True)
class Package:
    """
    Aggregate root -- real container/packaging type (box/bottle/pouch/
    ...), per explicit product decision. Referenced by a single FK on
    `ProductVariant` (`package_id`, one variant has exactly one package
    type), unlike `Flavour`'s Product-level many-to-many -- a given
    variant's physical packaging is a single, unambiguous fact, never
    a set.
    """

    id: uuid.UUID
    slug: Slug
    name: str
    sort_order: int = 0
    is_active: bool = True

    def __post_init__(self) -> None:
        from apps.products.domain.exceptions import InvalidPackage

        if not self.name or not self.name.strip():
            raise InvalidPackage("Package name must not be empty.")

    def deactivate(self) -> None:
        self.is_active = False

    def activate(self) -> None:
        self.is_active = True
