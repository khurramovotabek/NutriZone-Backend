"""
Repository integration tests -- require a real PostgreSQL database
(Django Implementation Blueprint §11: no SQLite, ever). Matches
`apps/identity/tests/infrastructure/test_repositories.py`'s pattern.
"""
from __future__ import annotations

import uuid

import pytest

from apps.products.domain.aggregates import Brand, Category, Product, ProductVariant, Tag
from apps.products.domain.value_objects import SKU, Slug
from apps.products.infrastructure.repositories import (
    DjangoBrandRepository,
    DjangoCategoryRepository,
    DjangoProductRepository,
    DjangoTagRepository,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestDjangoProductRepository:
    def test_save_then_get_by_id_round_trips_core_fields(self):
        repo = DjangoProductRepository()
        product = Product(id=uuid.uuid4(), slug=Slug("whey-protein"), name="Whey Protein", description="Great protein")
        repo.save(product)

        fetched = repo.get_by_id(product.id)
        assert fetched is not None
        assert fetched.name == "Whey Protein"
        assert fetched.slug.value == "whey-protein"
        assert fetched.description == "Great protein"

    def test_get_by_slug_finds_saved_product(self):
        repo = DjangoProductRepository()
        product = Product(id=uuid.uuid4(), slug=Slug("mass-gainer"), name="Mass Gainer")
        repo.save(product)

        fetched = repo.get_by_slug("mass-gainer")
        assert fetched is not None
        assert fetched.id == product.id

    def test_variants_round_trip(self):
        repo = DjangoProductRepository()
        product = Product(id=uuid.uuid4(), slug=Slug("test"), name="Test")
        product.add_variant(ProductVariant(id=uuid.uuid4(), sku=SKU("TEST-1")))
        repo.save(product)

        fetched = repo.get_by_id(product.id)
        assert len(fetched.variants) == 1
        assert next(iter(fetched.variants.values())).sku.value == "TEST-1"

    def test_removing_a_variant_deletes_it_on_next_save(self):
        repo = DjangoProductRepository()
        product = Product(id=uuid.uuid4(), slug=Slug("test2"), name="Test2")
        variant = ProductVariant(id=uuid.uuid4(), sku=SKU("TEST-2"))
        product.add_variant(variant)
        repo.save(product)

        product.remove_variant(variant.id)
        repo.save(product)

        fetched = repo.get_by_id(product.id)
        assert len(fetched.variants) == 0

    def test_slug_exists_respects_exclusion(self):
        repo = DjangoProductRepository()
        product = Product(id=uuid.uuid4(), slug=Slug("unique-slug"), name="X")
        repo.save(product)

        assert repo.slug_exists("unique-slug") is True
        assert repo.slug_exists("unique-slug", exclude_product_id=product.id) is False

    def test_sku_exists(self):
        repo = DjangoProductRepository()
        product = Product(id=uuid.uuid4(), slug=Slug("sku-test"), name="X")
        product.add_variant(ProductVariant(id=uuid.uuid4(), sku=SKU("UNIQUE-SKU")))
        repo.save(product)

        assert repo.sku_exists("UNIQUE-SKU") is True
        assert repo.sku_exists("NONEXISTENT-SKU") is False

    def test_list_public_only_returns_published(self):
        from apps.products.domain.entities import ProductMedia
        from apps.products.domain.enums import MediaRole

        repo = DjangoProductRepository()
        draft = Product(id=uuid.uuid4(), slug=Slug("draft-product"), name="Draft")
        repo.save(draft)

        published = Product(id=uuid.uuid4(), slug=Slug("published-product"), name="Published")
        published.add_variant(ProductVariant(id=uuid.uuid4(), sku=SKU("PUB-1")))
        published.add_media(ProductMedia(id=uuid.uuid4(), media_id=uuid.uuid4(), media_role=MediaRole.PRIMARY, storage_path="products/test-asset.jpg"))
        published.publish()
        repo.save(published)

        results, total = repo.list_public()
        assert total == 1
        assert results[0].id == published.id

    def test_delete_soft_deletes(self):
        from apps.products.infrastructure import models as orm

        repo = DjangoProductRepository()
        product = Product(id=uuid.uuid4(), slug=Slug("to-delete"), name="X")
        repo.save(product)

        repo.delete(product.id)

        assert orm.Product.objects.filter(id=product.id).first() is None
        assert orm.Product.all_objects.filter(id=product.id).first() is not None


class TestDjangoBrandRepository:
    def test_save_and_get(self):
        repo = DjangoBrandRepository()
        brand = Brand(id=uuid.uuid4(), slug=Slug("optimum-nutrition"), name="Optimum Nutrition")
        repo.save(brand)

        fetched = repo.get_by_id(brand.id)
        assert fetched.name == "Optimum Nutrition"

    def test_manufacturer_scoped_brands_excluded_from_list_active(self):
        from apps.products.domain.aggregates import Manufacturer

        repo = DjangoBrandRepository()
        manufacturer = Manufacturer.create(uuid.uuid4(), Slug("glanbia"), "Glanbia")
        repo.save(manufacturer)

        active_brands = repo.list_active()
        assert all(b.id != manufacturer.id for b in active_brands)


class TestDjangoCategoryRepository:
    def test_save_and_get(self):
        repo = DjangoCategoryRepository()
        category = Category(id=uuid.uuid4(), slug=Slug("protein"), name="Protein")
        repo.save(category)

        fetched = repo.get_by_id(category.id)
        assert fetched.name == "Protein"


class TestDjangoTagRepository:
    def test_save_and_get_by_code(self):
        repo = DjangoTagRepository()
        tag = Tag(id=uuid.uuid4(), code="vegan", name="Vegan")
        repo.save(tag)

        fetched = repo.get_by_code("vegan")
        assert fetched.id == tag.id
