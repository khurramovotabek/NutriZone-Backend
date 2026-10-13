from __future__ import annotations

import pytest

from apps.products.interfaces.api.v1.serializers import (
    AssignTagsSerializer,
    CreateProductSerializer,
    CreateVariantSerializer,
    NutritionFactsSerializer,
    UpdateSEOSerializer,
)

pytestmark = pytest.mark.unit


class TestCreateProductSerializer:
    def test_valid_minimal_payload(self):
        serializer = CreateProductSerializer(data={"name": "Whey Protein"})
        assert serializer.is_valid()

    def test_missing_name_is_invalid(self):
        serializer = CreateProductSerializer(data={})
        assert not serializer.is_valid()
        assert "name" in serializer.errors

    def test_invalid_slug_format_is_invalid(self):
        serializer = CreateProductSerializer(data={"name": "X", "slug": "Not A Valid Slug!"})
        assert not serializer.is_valid()
        assert "slug" in serializer.errors


class TestCreateVariantSerializer:
    def test_valid_sku(self):
        serializer = CreateVariantSerializer(data={"sku": "WHEY-1KG"})
        assert serializer.is_valid()

    def test_invalid_sku_format_is_invalid(self):
        serializer = CreateVariantSerializer(data={"sku": "invalid sku!"})
        assert not serializer.is_valid()
        assert "sku" in serializer.errors

    def test_invalid_barcode_is_invalid(self):
        serializer = CreateVariantSerializer(data={"sku": "SKU-1", "barcode": "123"})
        assert not serializer.is_valid()
        assert "barcode" in serializer.errors


class TestNutritionFactsSerializer:
    def test_valid_payload(self):
        serializer = NutritionFactsSerializer(data={"serving_size_grams": 30, "servings_per_container": 20, "calories": 120})
        assert serializer.is_valid()

    def test_negative_calories_invalid(self):
        serializer = NutritionFactsSerializer(data={"serving_size_grams": 30, "servings_per_container": 20, "calories": -1})
        assert not serializer.is_valid()

    def test_zero_serving_size_invalid(self):
        serializer = NutritionFactsSerializer(data={"serving_size_grams": 0, "servings_per_container": 20, "calories": 100})
        assert not serializer.is_valid()


class TestUpdateSEOSerializer:
    def test_meta_title_length_enforced(self):
        serializer = UpdateSEOSerializer(data={"meta_title": "x" * 71})
        assert not serializer.is_valid()

    def test_valid_seo_payload(self):
        serializer = UpdateSEOSerializer(data={"meta_title": "Whey Protein", "meta_description": "The best."})
        assert serializer.is_valid()


class TestAssignTagsSerializer:
    def test_requires_tag_ids(self):
        serializer = AssignTagsSerializer(data={})
        assert not serializer.is_valid()

    def test_valid_uuid_list(self):
        import uuid

        serializer = AssignTagsSerializer(data={"tag_ids": [str(uuid.uuid4()), str(uuid.uuid4())]})
        assert serializer.is_valid()
