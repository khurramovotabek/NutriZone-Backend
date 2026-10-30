"""
Products API serializers.

Structural validation only (Django Implementation Blueprint §6's
400-vs-422 split) -- format checks call the same domain value objects
used elsewhere (SKU, Slug, Barcode) rather than re-implementing
regexes, per MIC §6's "a business rule is implemented in exactly one
place" rule. Business validation (publish-workflow gate, uniqueness,
media limits) is never duplicated here; it surfaces automatically as a
422/409 when the Application Service raises. Matches
`apps/identity/interfaces/api/v1/serializers.py`'s pattern exactly.
"""
from __future__ import annotations

from rest_framework import serializers

from apps.products.domain.enums import (
    AgeGroup,
    Availability,
    Gender,
    MediaRole,
    NutritionCategory,
    ProductStatus,
    SpecificationType,
    WeightUnit,
)
from apps.products.domain.value_objects import SKU, Barcode, Slug
from common.exceptions import ValidationFailed
from common.serializers import ReadOnlyAuditFieldsMixin


def _validate_slug(value: str) -> str:
    try:
        Slug(value)
    except ValidationFailed as exc:
        raise serializers.ValidationError(exc.message) from exc
    return value


def _validate_sku(value: str) -> str:
    try:
        SKU(value)
    except ValidationFailed as exc:
        raise serializers.ValidationError(exc.message) from exc
    return value


def _validate_barcode(value: str) -> str:
    try:
        Barcode(value)
    except ValidationFailed as exc:
        raise serializers.ValidationError(exc.message) from exc
    return value


# --- Public read shapes -----------------------------------------------


class PublicProductListSerializer(serializers.Serializer):
    """GET /products list item -- deliberately minimal (a 'card'), matching REST API Blueprint §13.2's product-list shape."""

    id = serializers.UUIDField()
    slug = serializers.CharField()
    slugs = serializers.DictField(child=serializers.CharField(), help_text="URL slug per language code (uz/ru/en) -- for hreflang alternates")
    name = serializers.CharField()
    brand_id = serializers.CharField(allow_null=True)
    category_id = serializers.CharField(allow_null=True)
    primary_image_path = serializers.CharField(allow_null=True)
    created_at = serializers.CharField()


class PublicProductDetailSerializer(serializers.Serializer):
    """GET /products/{slug} -- the full public-facing product read model. Kept in sync with `infrastructure/selectors.py::_product_card(..., include_details=True)`, which is what actually builds this response (this class is schema-only, for OpenAPI/drf-spectacular)."""

    id = serializers.UUIDField()
    slug = serializers.CharField()
    slugs = serializers.DictField(child=serializers.CharField(), help_text="URL slug per language code (uz/ru/en) -- for hreflang alternates")
    name = serializers.CharField()
    status = serializers.CharField()
    brand_id = serializers.CharField(allow_null=True)
    category_id = serializers.CharField(allow_null=True)
    primary_image_path = serializers.CharField(allow_null=True)
    created_at = serializers.CharField()
    price = serializers.CharField(allow_null=True)
    currency = serializers.CharField(allow_null=True)
    rating_average = serializers.FloatField(allow_null=True)
    rating_count = serializers.IntegerField()
    default_variant_id = serializers.CharField(allow_null=True)
    description = serializers.CharField(allow_blank=True)
    gallery = serializers.ListField(child=serializers.CharField())
    specifications = serializers.ListField(child=serializers.DictField())
    supplement_facts = serializers.CharField(allow_null=True)
    warnings = serializers.CharField(allow_null=True)
    directions = serializers.CharField(allow_null=True)
    variants = serializers.ListField(child=serializers.DictField())


class VariantSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    sku = serializers.CharField()
    barcode = serializers.CharField(allow_null=True, required=False)
    status = serializers.CharField(read_only=True)
    weight_value = serializers.FloatField(allow_null=True, required=False)
    weight_unit = serializers.CharField(read_only=True)
    package_id = serializers.CharField(allow_null=True, required=False)
    is_default = serializers.BooleanField(read_only=True)


class MediaSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    media_role = serializers.ChoiceField(choices=MediaRole.values())
    sort_order = serializers.IntegerField(read_only=True)


class NutritionFactsSerializer(serializers.Serializer):
    serving_size_grams = serializers.FloatField(min_value=0.01)
    servings_per_container = serializers.IntegerField(min_value=1)
    calories = serializers.FloatField(min_value=0)
    nutrients = serializers.DictField(child=serializers.FloatField(), required=False, default=dict)


class SEOSerializer(serializers.Serializer):
    meta_title = serializers.CharField(required=False, allow_null=True, max_length=70)
    meta_description = serializers.CharField(required=False, allow_null=True, max_length=160)


class SpecificationSerializer(serializers.Serializer):
    key = serializers.CharField(max_length=128)
    value = serializers.CharField(max_length=512)
    spec_type = serializers.ChoiceField(choices=SpecificationType.values(), default=SpecificationType.TEXT.value)
    sort_order = serializers.IntegerField(default=0)


class RelatedProductSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    related_product_id = serializers.UUIDField()
    relation_type = serializers.CharField()
    sort_order = serializers.IntegerField()


# --- Admin read shapes --------------------------------------------------


class AdminProductListItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    name = serializers.CharField()
    status = serializers.CharField()
    brand_id = serializers.CharField(allow_null=True)
    category_id = serializers.CharField(allow_null=True)
    variant_count = serializers.IntegerField(allow_null=True, required=False)
    media_count = serializers.IntegerField(allow_null=True, required=False)
    created_at = serializers.CharField()


class AdminProductDetailSerializer(ReadOnlyAuditFieldsMixin, serializers.Serializer):
    slug = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True, allow_null=True)
    brand_id = serializers.CharField(read_only=True, allow_null=True)
    category_id = serializers.CharField(read_only=True, allow_null=True)
    tag_ids = serializers.ListField(child=serializers.CharField(), read_only=True)
    flavour_ids = serializers.ListField(child=serializers.CharField(), read_only=True)
    supplement_facts_text_uz = serializers.CharField(read_only=True, allow_null=True)
    supplement_facts_text_ru = serializers.CharField(read_only=True, allow_null=True)
    supplement_facts_text_en = serializers.CharField(read_only=True, allow_null=True)
    warnings_text_uz = serializers.CharField(read_only=True, allow_null=True)
    warnings_text_ru = serializers.CharField(read_only=True, allow_null=True)
    warnings_text_en = serializers.CharField(read_only=True, allow_null=True)
    directions_text_uz = serializers.CharField(read_only=True, allow_null=True)
    directions_text_ru = serializers.CharField(read_only=True, allow_null=True)
    directions_text_en = serializers.CharField(read_only=True, allow_null=True)
    variants = VariantSerializer(many=True, read_only=True)
    media = MediaSerializer(many=True, read_only=True)
    seo = SEOSerializer(read_only=True)


# --- Write / command shapes --------------------------------------------


class CreateProductSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    brand_id = serializers.UUIDField(required=False, allow_null=True)
    category_id = serializers.UUIDField(required=False, allow_null=True)
    slug = serializers.CharField(required=False, allow_null=True, validators=[_validate_slug])


class UpdateProductSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, max_length=255)
    description = serializers.CharField(required=False, allow_null=True, allow_blank=True)


class PublishProductSerializer(serializers.Serializer):
    """Empty body -- publish takes no parameters, kept as an explicit serializer for OpenAPI documentation symmetry with the other lifecycle actions."""


class HideProductSerializer(serializers.Serializer):
    pass


class ArchiveProductSerializer(serializers.Serializer):
    pass


class RestoreProductSerializer(serializers.Serializer):
    pass


class DuplicateProductSerializer(serializers.Serializer):
    new_name = serializers.CharField(required=False, allow_null=True, max_length=255)


class CloneProductSerializer(serializers.Serializer):
    new_name = serializers.CharField(required=False, allow_null=True, max_length=255)


_WEIGHT_UNIT_CHOICES = [u.value for u in WeightUnit]


class CreateVariantSerializer(serializers.Serializer):
    sku = serializers.CharField(validators=[_validate_sku])
    barcode = serializers.CharField(required=False, allow_null=True, validators=[_validate_barcode])
    weight_value = serializers.FloatField(required=False, allow_null=True, min_value=0.01)
    weight_unit = serializers.ChoiceField(choices=_WEIGHT_UNIT_CHOICES, required=False, default=WeightUnit.GRAM.value)
    package_id = serializers.UUIDField(required=False, allow_null=True)


class UpdateVariantSerializer(serializers.Serializer):
    status = serializers.CharField(required=False)
    weight_value = serializers.FloatField(required=False, allow_null=True, min_value=0.01)
    weight_unit = serializers.ChoiceField(choices=_WEIGHT_UNIT_CHOICES, required=False)
    package_id = serializers.UUIDField(required=False, allow_null=True)


class UploadMediaSerializer(serializers.Serializer):
    """Multipart form shape for image/video/document upload."""

    media_role = serializers.ChoiceField(choices=MediaRole.values(), required=False, default=MediaRole.GALLERY.value)


class UpdateNutritionFactsSerializer(NutritionFactsSerializer):
    pass


class UpdateIngredientsSerializer(serializers.Serializer):
    ingredients_text = serializers.CharField(allow_blank=True)
    locale = serializers.ChoiceField(choices=["uz", "ru", "en"], default="uz")


class UpdateWarningsSerializer(serializers.Serializer):
    warnings_text = serializers.CharField(allow_blank=True)
    locale = serializers.ChoiceField(choices=["uz", "ru", "en"], default="uz")


class UpdateDirectionsSerializer(serializers.Serializer):
    directions_text = serializers.CharField(allow_blank=True)
    locale = serializers.ChoiceField(choices=["uz", "ru", "en"], default="uz")


class UpdateSEOSerializer(SEOSerializer):
    pass


class AssignBrandSerializer(serializers.Serializer):
    brand_id = serializers.UUIDField(required=False, allow_null=True)


class AssignCategorySerializer(serializers.Serializer):
    category_id = serializers.UUIDField(required=False, allow_null=True)


class AssignTagsSerializer(serializers.Serializer):
    tag_ids = serializers.ListField(child=serializers.UUIDField())


class AssignFlavoursSerializer(serializers.Serializer):
    flavour_ids = serializers.ListField(child=serializers.UUIDField())


# --- Reference data shapes ------------------------------------------------


class CategorySerializer(serializers.Serializer):
    id = serializers.CharField()
    parent_id = serializers.CharField(allow_null=True)
    name = serializers.CharField()
    sort_order = serializers.IntegerField()


class BrandSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()


class FlavourSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    color_hex = serializers.CharField(allow_null=True)
    image_url = serializers.CharField(allow_null=True)


class PackageSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()


class TagSerializer(serializers.Serializer):
    id = serializers.CharField()
    code = serializers.CharField()
    name = serializers.CharField()


class FilterMetadataSerializer(serializers.Serializer):
    brand = BrandSerializer(many=True)
    flavour = FlavourSerializer(many=True)
    status = serializers.ListField(child=serializers.CharField())
