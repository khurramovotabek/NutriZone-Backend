from __future__ import annotations

import pytest

from apps.products.domain.enums import ProductType, SEOStatus
from apps.products.domain.services import (
    ComplianceValidator,
    MediaPolicy,
    NutritionPolicy,
    PublicationPolicy,
    SEOGenerator,
    SKUGenerator,
    SlugGenerator,
    SpecificationPolicy,
    VariantMatrixBuilder,
    VariantPolicy,
)
from apps.products.domain.value_objects import NutritionFacts, ServingSize, Slug
from common.exceptions import ConflictError, ValidationFailed

pytestmark = pytest.mark.unit


class TestComplianceValidator:
    def test_supplement_category_requires_gmp(self):
        assert "gmp" in ComplianceValidator.required_certificate_types(is_supplement_category=True)

    def test_non_supplement_category_requires_nothing(self):
        assert ComplianceValidator.required_certificate_types(is_supplement_category=False) == frozenset()


class TestSKUGenerator:
    def test_generate_combines_parts(self):
        assert SKUGenerator.generate("on", "whey", "2kg") == "ON-WHEY-2KG"

    def test_generate_skips_empty_variant_suffix(self):
        assert SKUGenerator.generate("on", "whey", None) == "ON-WHEY"


class TestSlugGenerator:
    def test_generate_unique_returns_base_when_available(self):
        slug = SlugGenerator.generate_unique("Whey Protein", is_taken=lambda s: False)
        assert slug.value == "whey-protein"

    def test_generate_unique_appends_suffix_on_collision(self):
        taken = {"whey-protein"}
        slug = SlugGenerator.generate_unique("Whey Protein", is_taken=lambda s: s in taken)
        assert slug.value == "whey-protein-2"

    def test_generate_unique_raises_after_max_attempts(self):
        with pytest.raises(ValueError):
            SlugGenerator.generate_unique("Whey Protein", is_taken=lambda s: True, max_attempts=3)


class TestPublicationPolicy:
    def test_check_returns_can_publish_true_when_all_met(self):
        result = PublicationPolicy.check(has_variants=True, has_default_variant=True, has_primary_image=True, missing_certificate_types=frozenset())
        assert result.can_publish is True
        assert result.reasons == ()

    def test_check_returns_reasons_when_not_met(self):
        result = PublicationPolicy.check(has_variants=False, has_default_variant=False, has_primary_image=False, missing_certificate_types=frozenset({"gmp"}))
        assert result.can_publish is False
        codes = {r["code"] for r in result.reasons}
        assert "NO_VARIANTS" in codes
        assert "NO_PRIMARY_IMAGE" in codes
        assert "MISSING_REQUIRED_CERTIFICATE" in codes


class TestVariantPolicy:
    def test_within_limit_does_not_raise(self):
        VariantPolicy.assert_within_limit(5)

    def test_at_limit_raises(self):
        with pytest.raises(Exception):
            VariantPolicy.assert_within_limit(200)

    def test_classify_simple(self):
        assert VariantPolicy.classify_product_type(1, is_bundle=False) == ProductType.SIMPLE

    def test_classify_variable(self):
        assert VariantPolicy.classify_product_type(3, is_bundle=False) == ProductType.VARIABLE

    def test_classify_bundle(self):
        assert VariantPolicy.classify_product_type(1, is_bundle=True) == ProductType.BUNDLE


class TestMediaPolicy:
    def test_remaining_image_slots(self):
        assert MediaPolicy.remaining_image_slots(10) == 2

    def test_remaining_image_slots_never_negative(self):
        assert MediaPolicy.remaining_image_slots(20) == 0

    def test_remaining_video_slots(self):
        assert MediaPolicy.remaining_video_slots(1) == 3


class TestNutritionPolicy:
    def test_validate_none_does_not_raise(self):
        NutritionPolicy.validate(None)

    def test_validate_consistent_facts_does_not_raise(self):
        facts = NutritionFacts(serving_size=ServingSize(30, 20), calories=120, nutrients={"protein_g": 24, "fat_g": 1, "carbs_g": 3})
        NutritionPolicy.validate(facts)

    def test_validate_inconsistent_facts_raises(self):
        facts = NutritionFacts(serving_size=ServingSize(30, 20), calories=5, nutrients={"protein_g": 24, "fat_g": 10, "carbs_g": 20})
        with pytest.raises(ValidationFailed):
            NutritionPolicy.validate(facts)


class TestSEOGenerator:
    def test_generate_truncates_to_valid_lengths(self):
        seo = SEOGenerator.generate(name="x" * 100, description="y" * 200, slug=Slug("test"))
        assert len(seo.meta_title) <= 70
        assert len(seo.meta_description) <= 160

    def test_generate_falls_back_to_name_when_no_description(self):
        seo = SEOGenerator.generate(name="Whey Protein", description=None, slug=Slug("whey"))
        assert seo.meta_description == "Whey Protein"

    def test_completeness_complete(self):
        from apps.products.domain.value_objects import SEOData

        assert SEOGenerator.completeness(SEOData(meta_title="T", meta_description="D")) == SEOStatus.COMPLETE

    def test_completeness_incomplete(self):
        from apps.products.domain.value_objects import SEOData

        assert SEOGenerator.completeness(SEOData(meta_title="T")) == SEOStatus.INCOMPLETE

    def test_completeness_missing(self):
        from apps.products.domain.value_objects import SEOData

        assert SEOGenerator.completeness(SEOData()) == SEOStatus.MISSING


class TestSpecificationPolicy:
    def test_within_limit_does_not_raise(self):
        SpecificationPolicy.assert_within_limit(10)

    def test_at_limit_raises(self):
        with pytest.raises(ValidationFailed):
            SpecificationPolicy.assert_within_limit(50)

    def test_unique_key_does_not_raise(self):
        SpecificationPolicy.assert_unique_key(frozenset({"a", "b"}), "c")

    def test_duplicate_key_raises(self):
        with pytest.raises(ConflictError):
            SpecificationPolicy.assert_unique_key(frozenset({"a", "b"}), "a")


class TestVariantMatrixBuilder:
    def test_build_combinations_cartesian_product(self):
        combos = VariantMatrixBuilder.build_combinations({"flavor": ["chocolate", "vanilla"], "package_size": ["1kg", "2kg"]})
        assert len(combos) == 4
        assert {"flavor": "chocolate", "package_size": "1kg"} in combos
        assert {"flavor": "vanilla", "package_size": "2kg"} in combos

    def test_build_combinations_empty_dimensions(self):
        assert VariantMatrixBuilder.build_combinations({}) == []

    def test_build_combinations_single_dimension(self):
        combos = VariantMatrixBuilder.build_combinations({"flavor": ["chocolate", "vanilla", "unflavored"]})
        assert len(combos) == 3
