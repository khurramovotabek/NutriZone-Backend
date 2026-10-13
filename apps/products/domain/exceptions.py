"""
Products domain exceptions.

All subclass common/exceptions/exceptions.py's DomainException
hierarchy (Django Implementation Blueprint §5), matching the pattern
established by `apps/identity/domain/exceptions.py`. Named to match
this module's brief exactly (DuplicateSKU, DuplicateSlug, etc.).
"""
from __future__ import annotations

from common.exceptions import BusinessRuleViolation, ConflictError, ValidationFailed


class DuplicateSKU(ConflictError):
    code = "SKU_ALREADY_EXISTS"


class DuplicateSlug(ConflictError):
    code = "SLUG_COLLISION"


class DuplicateBarcode(ConflictError):
    code = "BARCODE_ALREADY_EXISTS"


class InvalidCategory(ValidationFailed):
    code = "CATEGORY_NOT_FOUND"


class InvalidBrand(ValidationFailed):
    code = "BRAND_NOT_FOUND"


class InvalidFlavour(ValidationFailed):
    code = "FLAVOUR_NOT_FOUND"


class InvalidPackage(ValidationFailed):
    code = "PACKAGE_NOT_FOUND"


class InvalidVariant(BusinessRuleViolation):
    code = "INVALID_VARIANT"


class InvalidNutrition(ValidationFailed):
    code = "INVALID_NUTRITION"


class InvalidMedia(ValidationFailed):
    code = "INVALID_MEDIA"


class InvalidSEO(ValidationFailed):
    code = "INVALID_SEO"


class InvalidAttribute(ValidationFailed):
    code = "INVALID_ATTRIBUTE"


class ProductArchived(ConflictError):
    """Raised when a mutating operation targets an archived product -- archived products are read-only except for `restore()`."""

    code = "PRODUCT_ARCHIVED"


class ProductHidden(BusinessRuleViolation):
    """Raised where an operation specifically requires a currently-visible (PUBLISHED) product -- distinct from ProductArchived, which is terminal, this is a normal, reversible state."""

    code = "PRODUCT_HIDDEN"


class PublishValidationFailed(BusinessRuleViolation):
    """
    Umbrella exception for the publish-workflow gate -- raised with a
    structured `details.reasons` list when one or more of the
    `PublicationPolicy` checks (domain/services.py) fail, so a client
    sees every blocking reason at once rather than one at a time
    (mirrors MIC §6's ValidationAggregator pattern for multi-reason
    business failures).
    """

    code = "PUBLISH_VALIDATION_FAILED"


class MediaLimitExceeded(BusinessRuleViolation):
    code = "MEDIA_LIMIT_EXCEEDED"


class PrimaryImageMissing(BusinessRuleViolation):
    code = "PRIMARY_IMAGE_MISSING"


class MissingRequiredCertificate(BusinessRuleViolation):
    code = "MISSING_REQUIRED_CERTIFICATE"


class InvalidProductLifecycleTransition(ConflictError):
    code = "INVALID_PRODUCT_LIFECYCLE_TRANSITION"


class VariantAlreadyExists(DuplicateSKU):
    """A variant-scoped alias of DuplicateSKU -- kept as a distinct, catchable type for call sites that specifically mean 'this SKU already exists on this product' rather than the broader catalog-wide uniqueness case."""

    code = "VARIANT_ALREADY_EXISTS"
