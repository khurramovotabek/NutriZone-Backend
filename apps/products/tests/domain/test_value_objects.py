from __future__ import annotations

import pytest

from apps.products.domain.value_objects import (
    Barcode,
    Dimension,
    DisplayOrder,
    DocumentMetadata,
    ImageMetadata,
    NutritionFacts,
    ProductCode,
    SEOData,
    SKU,
    ServingSize,
    Slug,
    VideoMetadata,
    Weight,
)
from common.exceptions import ValidationFailed

pytestmark = pytest.mark.unit


class TestSKU:
    def test_accepts_valid_sku(self):
        assert SKU("WHEY-CHOC-2KG").value == "WHEY-CHOC-2KG"

    @pytest.mark.parametrize("bad", ["whey-choc", "WHEY CHOC", "", "WHEY_CHOC"])
    def test_rejects_invalid_sku(self, bad):
        with pytest.raises(ValidationFailed):
            SKU(bad)


class TestBarcode:
    def test_accepts_valid_ean13_with_correct_checksum(self):
        # 4006381333931 is a well-known valid EAN-13 test barcode.
        assert Barcode("4006381333931").value == "4006381333931"

    def test_rejects_wrong_length(self):
        with pytest.raises(ValidationFailed):
            Barcode("123")

    def test_rejects_bad_checksum(self):
        with pytest.raises(ValidationFailed):
            Barcode("4006381333930")  # last digit tampered

    def test_rejects_non_numeric(self):
        with pytest.raises(ValidationFailed):
            Barcode("400638133393A")


class TestSlug:
    def test_accepts_valid_slug(self):
        assert Slug("whey-protein-2kg").value == "whey-protein-2kg"

    @pytest.mark.parametrize("bad", ["Whey Protein", "whey_protein", ""])
    def test_rejects_invalid_slug(self, bad):
        with pytest.raises(ValidationFailed):
            Slug(bad)

    def test_from_text_normalizes(self):
        assert Slug.from_text("Whey Protein 2KG!!").value == "whey-protein-2kg"

    def test_from_text_rejects_empty_result(self):
        with pytest.raises(ValidationFailed):
            Slug.from_text("!!!")

    def test_slug_max_length_enforced(self):
        with pytest.raises(ValidationFailed):
            Slug("a" * 221)


class TestServingSize:
    def test_accepts_valid_serving_size(self):
        ServingSize(amount_grams=30, servings_per_container=20)

    def test_rejects_non_positive_amount(self):
        with pytest.raises(ValidationFailed):
            ServingSize(amount_grams=0, servings_per_container=20)

    def test_rejects_non_positive_servings(self):
        with pytest.raises(ValidationFailed):
            ServingSize(amount_grams=30, servings_per_container=0)


class TestNutritionFacts:
    def test_accepts_valid_facts(self):
        NutritionFacts(serving_size=ServingSize(30, 20), calories=120, nutrients={"protein_g": 24})

    def test_rejects_negative_calories(self):
        with pytest.raises(ValidationFailed):
            NutritionFacts(serving_size=ServingSize(30, 20), calories=-1)

    def test_rejects_negative_nutrient(self):
        with pytest.raises(ValidationFailed):
            NutritionFacts(serving_size=ServingSize(30, 20), calories=100, nutrients={"protein_g": -5})


class TestWeight:
    def test_accepts_positive_weight(self):
        assert Weight(500).value == 500

    def test_defaults_to_grams(self):
        from apps.products.domain.enums import WeightUnit

        assert Weight(500).unit == WeightUnit.GRAM

    def test_accepts_kilograms(self):
        from apps.products.domain.enums import WeightUnit

        assert Weight(2.27, WeightUnit.KILOGRAM).unit == WeightUnit.KILOGRAM

    def test_rejects_non_positive_weight(self):
        with pytest.raises(ValidationFailed):
            Weight(0)


class TestDimension:
    def test_accepts_valid_dimension(self):
        Dimension(length_cm=10, width_cm=5, height_cm=15)

    @pytest.mark.parametrize("field", ["length_cm", "width_cm", "height_cm"])
    def test_rejects_non_positive_dimension(self, field):
        kwargs = {"length_cm": 10, "width_cm": 5, "height_cm": 15, field: 0}
        with pytest.raises(ValidationFailed):
            Dimension(**kwargs)


class TestSEOData:
    def test_accepts_valid_seo_data(self):
        SEOData(meta_title="Whey Protein", meta_description="Best protein.")

    def test_accepts_all_none(self):
        SEOData()

    def test_rejects_meta_title_too_long(self):
        with pytest.raises(ValidationFailed):
            SEOData(meta_title="x" * 71)

    def test_rejects_meta_description_too_long(self):
        with pytest.raises(ValidationFailed):
            SEOData(meta_description="x" * 161)


class TestImageMetadata:
    def test_accepts_valid_image(self):
        ImageMetadata(width_px=800, height_px=600, checksum_sha256="abc")

    def test_rejects_too_small_image(self):
        with pytest.raises(ValidationFailed):
            ImageMetadata(width_px=100, height_px=100, checksum_sha256="abc")


class TestVideoMetadata:
    def test_accepts_valid_video(self):
        VideoMetadata(duration_seconds=60, checksum_sha256="abc")

    def test_rejects_non_positive_duration(self):
        with pytest.raises(ValidationFailed):
            VideoMetadata(duration_seconds=0, checksum_sha256="abc")

    def test_rejects_too_long_video(self):
        with pytest.raises(ValidationFailed):
            VideoMetadata(duration_seconds=601, checksum_sha256="abc")


class TestDocumentMetadata:
    def test_accepts_valid_document(self):
        DocumentMetadata(page_count=5, checksum_sha256="abc")

    def test_accepts_null_page_count(self):
        DocumentMetadata(page_count=None, checksum_sha256="abc")

    def test_rejects_non_positive_page_count(self):
        with pytest.raises(ValidationFailed):
            DocumentMetadata(page_count=0, checksum_sha256="abc")


class TestProductCode:
    def test_accepts_valid_code(self):
        assert ProductCode("ABC123").value == "ABC123"

    def test_rejects_too_short(self):
        with pytest.raises(ValidationFailed):
            ProductCode("AB")


class TestDisplayOrder:
    def test_accepts_non_negative(self):
        assert DisplayOrder(0).value == 0

    def test_rejects_negative(self):
        with pytest.raises(ValidationFailed):
            DisplayOrder(-1)
