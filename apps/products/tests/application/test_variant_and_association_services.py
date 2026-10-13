from __future__ import annotations

import uuid

import pytest

from apps.products.application.services._shared import ProductServiceContext
from apps.products.application.services.associations import AssignBrand, AssignCategory, AssignTags
from apps.products.application.services.variants import (
    CreateVariant,
    DeleteVariant,
    SetDefaultVariant,
    UpdateVariant,
)
from apps.products.domain.aggregates import Brand, Category, Package, Product, ProductVariant, Tag
from apps.products.domain.exceptions import DuplicateSKU, InvalidBrand, InvalidPackage, InvalidVariant
from apps.products.domain.value_objects import SKU, Slug
from apps.products.tests.application.fakes import (
    FakeBrandRepository,
    FakeCategoryRepository,
    FakePackageRepository,
    FakeProductRepository,
    FakeTagRepository,
    collect_events,
)
from common.exceptions import ResourceNotFound, ValidationFailed


def _ctx():
    events: list = []
    return ProductServiceContext(stage_events=collect_events(events), actor_id=uuid.uuid4()), events


def _bare_product() -> Product:
    return Product(id=uuid.uuid4(), slug=Slug("x"), name="X")


@pytest.mark.django_db
class TestCreateVariant:
    def test_creates_variant(self):
        repo = FakeProductRepository()
        product = _bare_product()
        repo.save(product)
        ctx, events = _ctx()

        updated = CreateVariant(repo, FakePackageRepository(), ctx).execute(product_id=product.id, sku="SKU-1")

        assert len(updated.variants) == 1
        assert any(e[0] == "ProductVariantCreated" for e in events)

    def test_duplicate_sku_across_catalog_raises(self):
        repo = FakeProductRepository()
        product_a = _bare_product()
        product_a.add_variant(ProductVariant(id=uuid.uuid4(), sku=SKU("SKU-1")))
        repo.save(product_a)
        product_b = _bare_product()
        repo.save(product_b)
        ctx, _ = _ctx()

        with pytest.raises(DuplicateSKU):
            CreateVariant(repo, FakePackageRepository(), ctx).execute(product_id=product_b.id, sku="SKU-1")

    def test_creates_variant_with_a_real_package(self):
        repo = FakeProductRepository()
        package_repo = FakePackageRepository()
        product = _bare_product()
        repo.save(product)
        package = Package(id=uuid.uuid4(), slug=Slug("bottle"), name="Bottle")
        package_repo.save(package)
        ctx, _ = _ctx()

        updated = CreateVariant(repo, package_repo, ctx).execute(product_id=product.id, sku="SKU-1", package_id=package.id)

        assert next(iter(updated.variants.values())).package_id == package.id

    def test_unknown_package_raises(self):
        repo = FakeProductRepository()
        product = _bare_product()
        repo.save(product)
        ctx, _ = _ctx()

        with pytest.raises(InvalidPackage):
            CreateVariant(repo, FakePackageRepository(), ctx).execute(product_id=product.id, sku="SKU-1", package_id=uuid.uuid4())


@pytest.mark.django_db
class TestUpdateDeleteSetDefaultVariant:
    def test_update_variant_status(self):
        repo = FakeProductRepository()
        product = _bare_product()
        variant = ProductVariant(id=uuid.uuid4(), sku=SKU("SKU-1"))
        product.add_variant(variant)
        repo.save(product)
        ctx, events = _ctx()

        updated = UpdateVariant(repo, FakePackageRepository(), ctx).execute(product_id=product.id, variant_id=variant.id, status="inactive")

        assert updated.variants[variant.id].status.value == "inactive"
        assert any(e[0] == "ProductVariantUpdated" for e in events)

    def test_update_unknown_variant_raises(self):
        repo = FakeProductRepository()
        product = _bare_product()
        repo.save(product)
        ctx, _ = _ctx()
        with pytest.raises(InvalidVariant):
            UpdateVariant(repo, FakePackageRepository(), ctx).execute(product_id=product.id, variant_id=uuid.uuid4(), status="inactive")

    def test_delete_variant(self):
        repo = FakeProductRepository()
        product = _bare_product()
        variant = ProductVariant(id=uuid.uuid4(), sku=SKU("SKU-1"))
        product.add_variant(variant)
        repo.save(product)
        ctx, events = _ctx()

        updated = DeleteVariant(repo, ctx).execute(product_id=product.id, variant_id=variant.id)

        assert variant.id not in updated.variants
        assert any(e[0] == "ProductVariantDeleted" for e in events)

    def test_set_default_variant(self):
        repo = FakeProductRepository()
        product = _bare_product()
        v1 = ProductVariant(id=uuid.uuid4(), sku=SKU("SKU-1"))
        v2 = ProductVariant(id=uuid.uuid4(), sku=SKU("SKU-2"))
        product.add_variant(v1)
        product.add_variant(v2)
        repo.save(product)
        ctx, _ = _ctx()

        updated = SetDefaultVariant(repo, ctx).execute(product_id=product.id, variant_id=v2.id)

        assert updated.variants[v2.id].is_default is True
        assert updated.variants[v1.id].is_default is False


@pytest.mark.django_db
class TestAssignBrandCategoryTags:
    def test_assign_brand(self):
        product_repo = FakeProductRepository()
        brand_repo = FakeBrandRepository()
        product = _bare_product()
        product_repo.save(product)
        brand = Brand(id=uuid.uuid4(), slug=Slug("on"), name="ON")
        brand_repo.save(brand)
        ctx, events = _ctx()

        updated = AssignBrand(product_repo, brand_repo, ctx).execute(product_id=product.id, brand_id=brand.id)

        assert updated.brand_id == brand.id
        assert any(e[0] == "BrandAssigned" for e in events)

    def test_assign_unknown_brand_raises(self):
        product_repo = FakeProductRepository()
        product = _bare_product()
        product_repo.save(product)
        ctx, _ = _ctx()
        with pytest.raises(InvalidBrand):
            AssignBrand(product_repo, FakeBrandRepository(), ctx).execute(product_id=product.id, brand_id=uuid.uuid4())

    def test_assign_category(self):
        product_repo = FakeProductRepository()
        category_repo = FakeCategoryRepository()
        product = _bare_product()
        product_repo.save(product)
        category = Category(id=uuid.uuid4(), slug=Slug("supplements"), name="Supplements")
        category_repo.save(category)
        ctx, events = _ctx()

        updated = AssignCategory(product_repo, category_repo, ctx).execute(product_id=product.id, category_id=category.id)

        assert updated.category_id == category.id
        assert any(e[0] == "CategoryAssigned" for e in events)

    def test_assign_tags(self):
        product_repo = FakeProductRepository()
        tag_repo = FakeTagRepository()
        product = _bare_product()
        product_repo.save(product)
        tag = Tag(id=uuid.uuid4(), code="vegan", name="Vegan")
        tag_repo.save(tag)
        ctx, _ = _ctx()

        updated = AssignTags(product_repo, tag_repo, ctx).execute(product_id=product.id, tag_ids=frozenset({tag.id}))

        assert tag.id in updated.tag_ids

    def test_assign_unknown_tags_raises(self):
        product_repo = FakeProductRepository()
        product = _bare_product()
        product_repo.save(product)
        ctx, _ = _ctx()
        with pytest.raises(ValidationFailed):
            AssignTags(product_repo, FakeTagRepository(), ctx).execute(product_id=product.id, tag_ids=frozenset({uuid.uuid4()}))
