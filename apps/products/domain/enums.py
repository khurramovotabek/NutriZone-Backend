"""
Products domain enums.

Each mirrors a Postgres native ENUM type 1:1, per Enterprise Database
Blueprint §2/§4.2 and Django Implementation Blueprint §6 -- matching
the pattern established by `apps/identity/domain/enums.py`.

Reconciliation note (documented per MIC §1 step 4's "must match the
Database Blueprint 1:1" rule): the Database Blueprint's
`catalog.products.status` only names four values
(draft/published/unpublished/archived). This module's brief asks for a
richer workflow (Draft/PendingReview/Published/Hidden/Archived). Both
are reconciled below: `ProductStatus` keeps the Blueprint's four
values as the authoritative persisted state (so the DB schema is not
silently diverged from), and `PENDING_REVIEW` is added as a fifth,
additive value -- an editorial sub-state before DRAFT becomes eligible
for publish -- rather than replacing "unpublished" with "hidden"
(same underlying meaning, Blueprint's name kept as the source of truth,
"Hidden" used only as the public-facing/service-layer vocabulary
where this module's brief uses it).
"""
from __future__ import annotations

from common.utils import DomainStrEnum


class ProductStatus(DomainStrEnum):
    """Database Blueprint §4.2 `catalog.products.status` (+ PENDING_REVIEW, additive)."""

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    PUBLISHED = "published"
    UNPUBLISHED = "unpublished"  # a.k.a. "Hidden" in this module's brief -- same state, Blueprint's persisted name kept authoritative
    ARCHIVED = "archived"


class ProductType(DomainStrEnum):
    """
    Not in the Database Blueprint as a distinct column -- modeled here
    as a domain-level classification derived from a product's variant
    count/bundle-membership (SIMPLE = exactly one variant, VARIABLE =
    more than one, BUNDLE = a `Bundle` aggregate, DIGITAL = reserved
    for future non-physical goods) rather than a stored field that
    could drift from the actual variant data -- see
    `domain/services.py::classify_product_type`.
    """

    SIMPLE = "simple"
    VARIABLE = "variable"
    BUNDLE = "bundle"
    DIGITAL = "digital"


class VariantStatus(DomainStrEnum):
    """Database Blueprint §4.2 `catalog.product_variants.status`."""

    ACTIVE = "active"
    INACTIVE = "inactive"


class NutritionCategory(DomainStrEnum):
    """Merchandising classification -- not itself a Database Blueprint column; realized as a Category tree entry (`categories.slug` in the seeded taxonomy) rather than a second, competing classification system. Enumerated here for domain-level validation of category-seeding/service inputs."""

    PROTEIN = "protein"
    CREATINE = "creatine"
    GAINER = "gainer"
    AMINO = "amino"
    VITAMIN = "vitamin"
    MINERAL = "mineral"
    ACCESSORY = "accessory"
    CLOTHING = "clothing"


class Gender(DomainStrEnum):
    MALE = "male"
    FEMALE = "female"
    UNISEX = "unisex"


class AgeGroup(DomainStrEnum):
    ADULT = "adult"
    TEEN = "teen"
    ALL_AGES = "all_ages"


class Availability(DomainStrEnum):
    """Product-level merchandising signal, distinct from Inventory's real-time `AvailabilityBoard` (Domain Architecture Specification §2.4) -- this is descriptive product data ("pre-order," "coming soon"), never the source of truth for sellable quantity, which stays exclusively Inventory's."""

    IN_STOCK = "in_stock"
    PRE_ORDER = "pre_order"
    COMING_SOON = "coming_soon"
    DISCONTINUED = "discontinued"


class StockPolicy(DomainStrEnum):
    """Merchandising-level policy hint consumed by Inventory when it's implemented; Products does not itself track quantity (Domain Architecture Specification §2.4 owns that exclusively)."""

    DENY_BACKORDER = "deny_backorder"
    ALLOW_BACKORDER = "allow_backorder"


class TaxType(DomainStrEnum):
    """Placeholder classification -- actual tax computation is out of this module's scope (Architecture Review §11 flags tax/fiscalization as a still-open integration)."""

    STANDARD = "standard"
    ZERO_RATED = "zero_rated"
    EXEMPT = "exempt"


class MediaType(DomainStrEnum):
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"


class MediaRole(DomainStrEnum):
    """
    Database Blueprint §4.2 `catalog.product_media.media_role`,
    extended (documented, additive) to cover video/document/
    nutrition-label roles this module's brief requires explicitly.
    """

    PRIMARY = "primary"
    GALLERY = "gallery"
    VIDEO = "video"
    DOCUMENT = "document"
    NUTRITION_LABEL = "nutrition_label"
    CERTIFICATE_SCAN = "certificate_scan"


class ImageType(DomainStrEnum):
    PRODUCT_SHOT = "product_shot"
    LIFESTYLE = "lifestyle"
    NUTRITION_LABEL = "nutrition_label"
    SIZE_CHART = "size_chart"


class VideoType(DomainStrEnum):
    DEMO = "demo"
    REVIEW = "review"
    UNBOXING = "unboxing"


class DocumentType(DomainStrEnum):
    CERTIFICATE = "certificate"
    SPEC_SHEET = "spec_sheet"
    MANUAL = "manual"


class CertificateType(DomainStrEnum):
    """Database Blueprint §4.2 `catalog.certificates.certificate_type`."""

    GMP = "gmp"
    HALAL = "halal"
    ISO = "iso"
    ORGANIC = "organic"
    OTHER = "other"


class WeightUnit(DomainStrEnum):
    """
    Real, product-required distinction: a variant's real-world measure
    label is genuinely expressed in grams for some products (250 g),
    kilograms for others (2.27 kg), volume for liquids (500 ml/1 l),
    or a plain unit count for tablets/capsules/gummies/chewables (60
    tablets) -- the admin picks the unit a given variant is actually
    labelled in, never an auto-converted display.
    `ProductVariant.weight_value` is a plain positive number in
    whichever of these this field says, never silently normalized or
    converted between units internally.
    """

    GRAM = "g"
    KILOGRAM = "kg"
    MILLILITER = "ml"
    LITER = "l"
    TABLET = "tablet"
    CAPSULE = "capsule"
    GUMMY = "gummy"
    CHEWABLE = "chewable"


class SpecificationType(DomainStrEnum):
    """Free-form key/value product specifications (e.g. "Protein per serving": "24g") -- distinct from the structured `NutritionFacts` value object, for attributes that don't fit the fixed nutrition-label shape."""

    TEXT = "text"
    NUMBER = "number"
    BOOLEAN = "boolean"


class SEOStatus(DomainStrEnum):
    """Editorial completeness signal for a product's SEO fields -- computed, not independently stored (see `domain/services.py::SEOGenerator`)."""

    MISSING = "missing"
    INCOMPLETE = "incomplete"
    COMPLETE = "complete"


class RelationType(DomainStrEnum):
    """Database Blueprint §4.2 `catalog.product_recommendations.relation_type`."""

    MANUAL_CURATED = "manual_curated"
    SIMILAR_CATEGORY = "similar_category"
