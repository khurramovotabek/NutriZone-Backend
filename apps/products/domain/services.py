"""
Products domain services.

Pure business rules with no I/O, per MIC §4 -- handed data by the
calling Application Service, never fetching it themselves. Matches the
pattern established by `apps/identity/domain/services.py::OTPPolicy`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from apps.products.domain.enums import CertificateType, ProductType, SEOStatus
from apps.products.domain.value_objects import SEOData, Slug

MAX_SPECIFICATIONS = 50
MAX_VARIANTS = 200

# Category -> required certificate types. A placeholder, deliberately
# small mapping (not a full category taxonomy, which belongs to actual
# seeded Category data) demonstrating the ComplianceValidator rule
# structurally -- extended by application/services as real category
# compliance requirements are defined by the business.
_SUPPLEMENT_CATEGORY_REQUIRED_CERTS: frozenset[str] = frozenset({CertificateType.GMP.value})


class ComplianceValidator:
    """
    Domain Architecture Specification §2.2's `ComplianceValidator`:
    "product cannot publish without required certificates for its
    category." Resolving *which* certificates a given category
    requires is handed to this service by the caller.
    """

    @staticmethod
    def required_certificate_types(is_supplement_category: bool) -> frozenset[str]:
        return _SUPPLEMENT_CATEGORY_REQUIRED_CERTS if is_supplement_category else frozenset()


class SKUGenerator:
    """Deterministic SKU derivation from brand/product/variant descriptors -- collision resolution (does this SKU already exist) is an application-layer concern requiring a repository lookup, kept out of this pure function."""

    @staticmethod
    def generate(brand_code: str, product_code: str, variant_suffix: str | None = None) -> str:
        parts = [p.strip().upper() for p in (brand_code, product_code, variant_suffix) if p and p.strip()]
        return "-".join(parts)


class SlugGenerator:
    """
    Pure slug generation with caller-supplied collision checking
    (mirrors `apps/identity/domain/services.py::OTPPolicy`'s
    hasher-injection pattern) -- `is_taken` is a callable the
    Application Service supplies (backed by a repository lookup), so
    this stays a pure function of its arguments.
    """

    @staticmethod
    def generate_unique(text: str, is_taken: Callable[[str], bool], max_attempts: int = 50) -> Slug:
        base = Slug.from_text(text)
        candidate = base
        attempt = 1
        while is_taken(candidate.value):
            attempt += 1
            if attempt > max_attempts:
                raise ValueError(f"Could not generate a unique slug for '{text}' after {max_attempts} attempts.")
            candidate = Slug(f"{base.value}-{attempt}")
        return candidate


@dataclass(frozen=True, slots=True)
class PublishCheckResult:
    can_publish: bool
    reasons: tuple[dict, ...]


class PublicationPolicy:
    """
    Read-only "can this product publish, and why not" check -- used by
    a preview/checklist endpoint that wants the same reasoning
    `Product.publish()` applies without actually mutating state. Kept
    in sync with `Product.publish()`'s checks by construction: both
    read from the same aggregate snapshot fields, this service just
    doesn't raise or mutate.
    """

    @staticmethod
    def check(has_variants: bool, has_default_variant: bool, has_primary_image: bool, missing_certificate_types: frozenset[str]) -> PublishCheckResult:
        reasons: list[dict] = []
        if not has_variants:
            reasons.append({"code": "NO_VARIANTS", "message": "Product has no variants."})
        elif not has_default_variant:
            reasons.append({"code": "NO_DEFAULT_VARIANT", "message": "Product has no default variant."})
        if not has_primary_image:
            reasons.append({"code": "NO_PRIMARY_IMAGE", "message": "Product has no primary image."})
        if missing_certificate_types:
            reasons.append({"code": "MISSING_REQUIRED_CERTIFICATE", "missing": sorted(missing_certificate_types)})
        return PublishCheckResult(can_publish=not reasons, reasons=tuple(reasons))


class VariantPolicy:
    @staticmethod
    def assert_within_limit(current_count: int) -> None:
        from apps.products.domain.exceptions import InvalidVariant

        if current_count >= MAX_VARIANTS:
            raise InvalidVariant(f"A product may not have more than {MAX_VARIANTS} variants.")

    @staticmethod
    def classify_product_type(variant_count: int, is_bundle: bool) -> ProductType:
        if is_bundle:
            return ProductType.BUNDLE
        return ProductType.VARIABLE if variant_count > 1 else ProductType.SIMPLE


class MediaPolicy:
    """Mirrors the limits `Product.add_media()` (aggregates.py) enforces -- exposed here as pure functions for pre-flight validation (e.g. a bulk-upload endpoint checking capacity before running the Media Pipeline on N files)."""

    MAX_IMAGES = 12
    MAX_VIDEOS = 4

    @classmethod
    def remaining_image_slots(cls, current_image_count: int) -> int:
        return max(cls.MAX_IMAGES - current_image_count, 0)

    @classmethod
    def remaining_video_slots(cls, current_video_count: int) -> int:
        return max(cls.MAX_VIDEOS - current_video_count, 0)


class NutritionPolicy:
    """Wraps the macro/calorie consistency rule (domain/validators.py::validate_nutrition_consistency) under the domain-service vocabulary this module's brief names explicitly."""

    @staticmethod
    def validate(nutrition_facts) -> None:
        from apps.products.domain.validators import validate_nutrition_consistency

        validate_nutrition_consistency(nutrition_facts)


class SEOGenerator:
    """Auto-derives SEOData from a product's name/description when no explicit SEO fields were supplied -- truncation rules match SEOData's own constructor validation (70/160 chars) so a generated value never fails its own value object's checks."""

    @staticmethod
    def generate(name: str, description: str | None, slug: Slug) -> SEOData:
        meta_title = name[:70]
        meta_description = (description or name)[:160]
        return SEOData(meta_title=meta_title, meta_description=meta_description, canonical_slug=slug)

    @staticmethod
    def completeness(seo: SEOData) -> SEOStatus:
        if seo.meta_title and seo.meta_description:
            return SEOStatus.COMPLETE
        if seo.meta_title or seo.meta_description:
            return SEOStatus.INCOMPLETE
        return SEOStatus.MISSING


class SpecificationPolicy:
    @staticmethod
    def assert_within_limit(current_count: int) -> None:
        from common.exceptions import ValidationFailed

        if current_count >= MAX_SPECIFICATIONS:
            raise ValidationFailed(f"A product may not have more than {MAX_SPECIFICATIONS} specifications.")

    @staticmethod
    def assert_unique_key(existing_keys: frozenset[str], new_key: str) -> None:
        from common.exceptions import ConflictError

        if new_key in existing_keys:
            raise ConflictError(f"A specification with key '{new_key}' already exists on this product.")


class VariantMatrixBuilder:
    """
    Domain Architecture Specification §2.2's `VariantMatrixBuilder`:
    "attribute combinations -> variants." Given a set of attribute
    dimensions (e.g. Flavor x PackageSize), produces the cartesian
    product of combinations a bulk variant-creation flow can turn into
    concrete `ProductVariant` entities -- pure computation, no
    persistence.
    """

    @staticmethod
    def build_combinations(dimensions: dict[str, list[str]]) -> list[dict[str, str]]:
        """
        `dimensions = {"flavor": ["chocolate", "vanilla"], "package_size": ["1kg", "2kg"]}`
        -> 4 combinations, each a dict of attribute_code -> value_code.
        """
        if not dimensions:
            return []

        keys = list(dimensions.keys())
        combinations: list[dict[str, str]] = [{}]
        for key in keys:
            values = dimensions[key]
            combinations = [dict(combo, **{key: value}) for combo in combinations for value in values]
        return combinations
