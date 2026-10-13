"""
Products domain value objects.

Immutable, self-validating -- structural rules live here (domain), not
duplicated in the serializer layer, per MIC §6's "a business rule is
implemented in exactly one place" rule. `Money` is deliberately NOT
redefined here -- it is one of the two items the Domain Architecture
Specification approves as Shared Kernel (§5 there), imported from
`shared.value_objects.money` exactly as `identity` and every other
future module must.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from apps.products.domain.enums import WeightUnit
from common.exceptions import ValidationFailed
from shared.value_objects.money import (
    Money,  # noqa: F401 -- re-exported for convenience; Shared Kernel, not redefined
)

_SKU_RE = re.compile(r"^[A-Z0-9]+(?:-[A-Z0-9]+)*$")
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_BARCODE_RE = re.compile(r"^\d{8,14}$")  # EAN-8 through EAN-14 / UPC-A range


@dataclass(frozen=True, slots=True)
class SKU:
    value: str

    def __post_init__(self) -> None:
        if not _SKU_RE.match(self.value):
            raise ValidationFailed(
                "SKU must be uppercase alphanumeric, hyphen-separated (e.g. WHEY-CHOC-2KG).",
                details={"fields": [{"field": "sku", "code": "INVALID_FORMAT"}]},
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Barcode:
    """EAN/UPC barcode -- Database Blueprint §4.2 `product_variants.barcode`."""

    value: str

    def __post_init__(self) -> None:
        if not _BARCODE_RE.match(self.value):
            raise ValidationFailed(
                "Barcode must be 8-14 digits (EAN-8 through EAN-14/UPC-A).",
                details={"fields": [{"field": "barcode", "code": "INVALID_FORMAT"}]},
            )
        if not self._checksum_valid():
            raise ValidationFailed(
                "Barcode failed checksum validation.",
                details={"fields": [{"field": "barcode", "code": "INVALID_CHECKSUM"}]},
            )

    def _checksum_valid(self) -> bool:
        """Standard GTIN mod-10 checksum, applied to EAN-8/12/13/14."""
        digits = [int(d) for d in self.value]
        payload, check_digit = digits[:-1], digits[-1]
        total = 0
        for i, digit in enumerate(reversed(payload)):
            total += digit * (3 if i % 2 == 0 else 1)
        computed_check = (10 - (total % 10)) % 10
        return computed_check == check_digit

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Slug:
    value: str

    def __post_init__(self) -> None:
        if not _SLUG_RE.match(self.value):
            raise ValidationFailed(
                "Slug must be lowercase, alphanumeric, hyphen-separated.",
                details={"fields": [{"field": "slug", "code": "INVALID_FORMAT"}]},
            )
        if len(self.value) > 220:
            raise ValidationFailed("Slug must not exceed 220 characters.", details={"fields": [{"field": "slug", "code": "TOO_LONG"}]})

    @staticmethod
    def from_text(text: str) -> Slug:
        """Deterministic slugification -- ASCII-fold, lowercase, hyphenate. Collision resolution (appending -2, -3, ...) is an application-layer concern (needs a repository lookup), not this pure function's job."""
        normalized = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
        if not normalized:
            raise ValidationFailed("Cannot derive a slug from empty or non-alphanumeric text.")
        return Slug(normalized[:220].rstrip("-"))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ServingSize:
    amount_grams: float
    servings_per_container: int

    def __post_init__(self) -> None:
        if self.amount_grams <= 0:
            raise ValidationFailed("Serving size must be a positive number of grams.", details={"fields": [{"field": "serving_size_grams", "code": "NON_POSITIVE"}]})
        if self.servings_per_container <= 0:
            raise ValidationFailed("Servings per container must be positive.", details={"fields": [{"field": "servings_per_container", "code": "NON_POSITIVE"}]})


@dataclass(frozen=True, slots=True)
class NutritionFacts:
    """Database Blueprint §4.2 `catalog.nutrition_facts` -- `nutrients` stays an open dict deliberately (JSONB in the DB), per that table's own documented rationale."""

    serving_size: ServingSize
    calories: float
    nutrients: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.calories < 0:
            raise ValidationFailed("Calories must not be negative.", details={"fields": [{"field": "calories", "code": "NEGATIVE"}]})
        for nutrient, amount in self.nutrients.items():
            if amount < 0:
                raise ValidationFailed(
                    f"Nutrient '{nutrient}' amount must not be negative.",
                    details={"fields": [{"field": f"nutrients.{nutrient}", "code": "NEGATIVE"}]},
                )


@dataclass(frozen=True, slots=True)
class Weight:
    value: float
    unit: WeightUnit = WeightUnit.GRAM

    def __post_init__(self) -> None:
        if self.value <= 0:
            raise ValidationFailed("Weight must be a positive number.", details={"fields": [{"field": "weight_value", "code": "NON_POSITIVE"}]})


@dataclass(frozen=True, slots=True)
class Dimension:
    """Package dimensions in centimeters -- used for shipping-cost estimation by the future Fulfillment context, exposed here as descriptive product data."""

    length_cm: float
    width_cm: float
    height_cm: float

    def __post_init__(self) -> None:
        for name, value in (("length_cm", self.length_cm), ("width_cm", self.width_cm), ("height_cm", self.height_cm)):
            if value <= 0:
                raise ValidationFailed(f"{name} must be positive.", details={"fields": [{"field": name, "code": "NON_POSITIVE"}]})


@dataclass(frozen=True, slots=True)
class SEOData:
    """
    Not a separate `catalog.product_seo` table in the Database
    Blueprint (no such table exists there) -- SEO fields are part of
    `product_translations` (meta title/description) per that
    Blueprint's actual schema. Modeled here as a value object embedded
    on the Product aggregate rather than inventing an unapproved table,
    per MIC §1 step 5's "a table that doesn't exist yet in the
    Blueprint is a Blueprint amendment, not a model-layer decision."
    """

    meta_title: str | None = None
    meta_description: str | None = None
    canonical_slug: Slug | None = None

    def __post_init__(self) -> None:
        if self.meta_title and len(self.meta_title) > 70:
            raise ValidationFailed("meta_title should not exceed 70 characters for SEO display.", details={"fields": [{"field": "meta_title", "code": "TOO_LONG"}]})
        if self.meta_description and len(self.meta_description) > 160:
            raise ValidationFailed("meta_description should not exceed 160 characters for SEO display.", details={"fields": [{"field": "meta_description", "code": "TOO_LONG"}]})


@dataclass(frozen=True, slots=True)
class ImageMetadata:
    width_px: int
    height_px: int
    checksum_sha256: str

    def __post_init__(self) -> None:
        if self.width_px < 200 or self.height_px < 200:
            raise ValidationFailed(
                "Product images must be at least 200x200px.",
                details={"fields": [{"field": "image", "code": "TOO_SMALL"}]},
            )


@dataclass(frozen=True, slots=True)
class VideoMetadata:
    duration_seconds: float
    checksum_sha256: str

    def __post_init__(self) -> None:
        if self.duration_seconds <= 0:
            raise ValidationFailed("Video duration must be positive.", details={"fields": [{"field": "video", "code": "INVALID_DURATION"}]})
        if self.duration_seconds > 600:
            raise ValidationFailed(
                "Product videos must not exceed 10 minutes.",
                details={"fields": [{"field": "video", "code": "TOO_LONG"}]},
            )


@dataclass(frozen=True, slots=True)
class DocumentMetadata:
    """Metadata for spec sheets/manuals/certificates -- Document media (MediaType.DOCUMENT)."""

    page_count: int | None
    checksum_sha256: str

    def __post_init__(self) -> None:
        if self.page_count is not None and self.page_count <= 0:
            raise ValidationFailed("page_count must be positive when known.", details={"fields": [{"field": "document", "code": "INVALID_PAGE_COUNT"}]})


@dataclass(frozen=True, slots=True)
class ProductCode:
    """
    Internal merchandising code (distinct from SKU, which is
    variant-level and customer/receipt-facing) -- a product-level
    identifier used in internal catalog management tooling/imports.
    """

    value: str

    def __post_init__(self) -> None:
        if not (3 <= len(self.value) <= 32):
            raise ValidationFailed("Product code must be 3-32 characters.", details={"fields": [{"field": "product_code", "code": "INVALID_LENGTH"}]})

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class DisplayOrder:
    """A non-negative sort-order value -- used for media ordering, variant listing order, and category sort_order alike, so ordering validation is defined once."""

    value: int

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValidationFailed("Display order must not be negative.", details={"fields": [{"field": "sort_order", "code": "NEGATIVE"}]})
