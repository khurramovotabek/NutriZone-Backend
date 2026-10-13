"""
Products domain (business) validators.

Structural, single-value-object validation already lives in the value
objects' own `__post_init__` (domain/value_objects.py) -- these
functions are named to match this module's brief explicitly
(SlugValidator, SKUValidator, etc.) and are thin, intention-revealing
wrappers over that same value-object validation for call sites that
want to validate a raw string/number without constructing the full
value object, plus the handful of genuinely multi-field business rules
(nutrition consistency) that don't belong to any single value object.
"""
from __future__ import annotations

from apps.products.domain.enums import WeightUnit
from apps.products.domain.value_objects import (
    SKU,
    Barcode,
    Dimension,
    NutritionFacts,
    SEOData,
    Slug,
    Weight,
)
from common.exceptions import ValidationFailed


def SlugValidator(value: str) -> Slug:  # noqa: N802 - intentional PascalCase to match this module's brief's naming
    return Slug(value)


def SKUValidator(value: str) -> SKU:  # noqa: N802
    return SKU(value)


def BarcodeValidator(value: str) -> Barcode:  # noqa: N802
    return Barcode(value)


def WeightValidator(value: float, unit: WeightUnit = WeightUnit.GRAM) -> Weight:  # noqa: N802
    return Weight(value, unit)


def DimensionValidator(length_cm: float, width_cm: float, height_cm: float) -> Dimension:  # noqa: N802
    return Dimension(length_cm=length_cm, width_cm=width_cm, height_cm=height_cm)


def SEOValidator(meta_title: str | None, meta_description: str | None) -> SEOData:  # noqa: N802
    return SEOData(meta_title=meta_title, meta_description=meta_description)


def NutritionValidator(facts: NutritionFacts | None) -> None:  # noqa: N802
    """Delegates to the multi-field macro/calorie consistency rule -- see validate_nutrition_consistency below for why this can't live in NutritionFacts' own constructor (it needs the full nutrients dict + calories together, which the value object already carries, but the rule is a soft data-quality guard rather than a hard invariant, kept separate so NutritionFacts can be constructed with 'implausible but not impossible' data during, e.g., data migration/import flows that call this validator explicitly instead)."""
    validate_nutrition_consistency(facts)


def MediaValidator(media_role: str, current_count: int, limit: int) -> None:  # noqa: N802
    if current_count >= limit:
        raise ValidationFailed(
            f"Cannot add another '{media_role}' media item -- limit of {limit} reached.",
            details={"fields": [{"field": "media", "code": "LIMIT_REACHED"}]},
        )


def validate_nutrition_consistency(facts: NutritionFacts | None) -> None:
    """A supplement product with macronutrient data should have calories roughly consistent with protein/fat/carb content -- a data-quality guard, not a strict physics check (rounding/fiber/sugar-alcohol adjustments make exact equality wrong)."""
    if facts is None:
        return
    macros = facts.nutrients
    protein = macros.get("protein_g", 0)
    fat = macros.get("fat_g", 0)
    carbs = macros.get("carbs_g", 0)
    estimated_calories = protein * 4 + fat * 9 + carbs * 4
    if estimated_calories > 0 and abs(estimated_calories - facts.calories) > max(50, estimated_calories * 0.35):
        raise ValidationFailed(
            "Declared calories are inconsistent with the declared macronutrients.",
            details={"fields": [{"field": "calories", "code": "INCONSISTENT_WITH_MACROS"}]},
        )


def validate_variant_count(variant_count: int, max_variants: int = 200) -> None:
    if variant_count > max_variants:
        raise ValidationFailed(
            f"A product may not have more than {max_variants} variants.",
            details={"fields": [{"field": "variants", "code": "TOO_MANY"}]},
        )
