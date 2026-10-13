from __future__ import annotations

import pytest

from apps.products.domain.validators import (
    BarcodeValidator,
    DimensionValidator,
    MediaValidator,
    NutritionValidator,
    SEOValidator,
    SKUValidator,
    SlugValidator,
    WeightValidator,
    validate_nutrition_consistency,
    validate_variant_count,
)
from apps.products.domain.value_objects import NutritionFacts, ServingSize
from common.exceptions import ValidationFailed

pytestmark = pytest.mark.unit


def test_slug_validator_returns_value_object():
    assert SlugValidator("whey-protein").value == "whey-protein"


def test_sku_validator_returns_value_object():
    assert SKUValidator("WHEY-1").value == "WHEY-1"


def test_barcode_validator_rejects_invalid():
    with pytest.raises(ValidationFailed):
        BarcodeValidator("123")


def test_weight_validator_rejects_non_positive():
    with pytest.raises(ValidationFailed):
        WeightValidator(0)


def test_dimension_validator_returns_value_object():
    dim = DimensionValidator(10, 5, 15)
    assert dim.length_cm == 10


def test_seo_validator_returns_value_object():
    seo = SEOValidator("Title", "Description")
    assert seo.meta_title == "Title"


def test_nutrition_validator_delegates_to_consistency_check():
    facts = NutritionFacts(serving_size=ServingSize(30, 20), calories=5, nutrients={"protein_g": 24, "fat_g": 10, "carbs_g": 20})
    with pytest.raises(ValidationFailed):
        NutritionValidator(facts)


def test_media_validator_within_limit():
    MediaValidator("gallery", current_count=5, limit=12)  # should not raise


def test_media_validator_at_limit_raises():
    with pytest.raises(ValidationFailed):
        MediaValidator("gallery", current_count=12, limit=12)


def test_validate_nutrition_consistency_none_is_noop():
    validate_nutrition_consistency(None)


def test_validate_variant_count_within_limit():
    validate_variant_count(50, max_variants=200)


def test_validate_variant_count_exceeds_limit_raises():
    with pytest.raises(ValidationFailed):
        validate_variant_count(201, max_variants=200)
