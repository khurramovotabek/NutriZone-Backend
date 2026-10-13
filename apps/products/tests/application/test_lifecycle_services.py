from __future__ import annotations

import uuid

import pytest

from apps.products.application.services._shared import ProductServiceContext
from apps.products.application.services.lifecycle import (
    ArchiveProduct, CreateProduct, DeleteProduct, HideProduct, PublishProduct, RestoreProduct, UpdateProduct,
)
from apps.products.domain.aggregates import Product, ProductVariant
from apps.products.domain.entities import ProductMedia
from apps.products.domain.enums import MediaRole, ProductStatus
from apps.products.domain.exceptions import InvalidBrand, InvalidProductLifecycleTransition, PublishValidationFailed
from apps.products.domain.value_objects import SKU, Slug
from apps.products.tests.application.fakes import FakeBrandRepository, FakeCategoryRepository, FakeProductRepository, collect_events
from common.exceptions import ResourceNotFound


def _ctx() -> tuple[ProductServiceContext, list]:
    events: list = []
    return ProductServiceContext(stage_events=collect_events(events), actor_id=uuid.uuid4()), events


@pytest.mark.django_db
class TestCreateProduct:
    """Marked django_db: CreateProduct.execute uses @transaction.atomic -- see apps.identity.tests.application.test_auth_services's identical documented rationale."""

    def test_creates_a_draft_product(self):
        repo = FakeProductRepository()
        ctx, events = _ctx()
        service = CreateProduct(repo, FakeBrandRepository(), FakeCategoryRepository(), ctx)

        product = service.execute(name="Whey Protein")

        assert product.status == ProductStatus.DRAFT
        assert product.slug.value == "whey-protein"
        assert any(e[0] == "ProductCreated" for e in events)

    def test_unknown_brand_raises(self):
        repo = FakeProductRepository()
        ctx, _ = _ctx()
        service = CreateProduct(repo, FakeBrandRepository(), FakeCategoryRepository(), ctx)
        with pytest.raises(InvalidBrand):
            service.execute(name="Whey Protein", brand_id=uuid.uuid4())

    def test_generates_unique_slug_on_collision(self):
        repo = FakeProductRepository()
        ctx, _ = _ctx()
        service = CreateProduct(repo, FakeBrandRepository(), FakeCategoryRepository(), ctx)
        service.execute(name="Whey Protein")
        second = service.execute(name="Whey Protein")
        assert second.slug.value == "whey-protein-2"


@pytest.mark.django_db
class TestUpdateProduct:
    def test_updates_name(self):
        repo = FakeProductRepository()
        product = Product(id=uuid.uuid4(), slug=Slug("x"), name="Old Name")
        repo.save(product)
        ctx, events = _ctx()

        updated = UpdateProduct(repo, ctx).execute(product_id=product.id, name="New Name")

        assert updated.name == "New Name"
        assert any(e[0] == "ProductUpdated" for e in events)

    def test_missing_product_raises(self):
        repo = FakeProductRepository()
        ctx, _ = _ctx()
        with pytest.raises(ResourceNotFound):
            UpdateProduct(repo, ctx).execute(product_id=uuid.uuid4(), name="X")


@pytest.mark.django_db
class TestPublishProduct:
    def test_publish_succeeds_when_ready(self):
        repo = FakeProductRepository()
        product = Product(id=uuid.uuid4(), slug=Slug("x"), name="X")
        product.add_variant(ProductVariant(id=uuid.uuid4(), sku=SKU("SKU-1")))
        product.add_media(ProductMedia(id=uuid.uuid4(), media_id=uuid.uuid4(), media_role=MediaRole.PRIMARY))
        repo.save(product)
        ctx, events = _ctx()

        published = PublishProduct(repo, FakeCategoryRepository(), ctx).execute(product.id)

        assert published.status == ProductStatus.PUBLISHED
        assert any(e[0] == "ProductPublished" for e in events)

    def test_publish_fails_when_not_ready(self):
        repo = FakeProductRepository()
        product = Product(id=uuid.uuid4(), slug=Slug("x"), name="X")
        repo.save(product)
        ctx, _ = _ctx()
        with pytest.raises(PublishValidationFailed):
            PublishProduct(repo, FakeCategoryRepository(), ctx).execute(product.id)


@pytest.mark.django_db
class TestHideArchiveRestoreProduct:
    def _published_product(self, repo: FakeProductRepository) -> Product:
        product = Product(id=uuid.uuid4(), slug=Slug("x"), name="X")
        product.add_variant(ProductVariant(id=uuid.uuid4(), sku=SKU("SKU-1")))
        product.add_media(ProductMedia(id=uuid.uuid4(), media_id=uuid.uuid4(), media_role=MediaRole.PRIMARY))
        product.publish()
        repo.save(product)
        return product

    def test_hide_published_product(self):
        repo = FakeProductRepository()
        product = self._published_product(repo)
        ctx, events = _ctx()
        hidden = HideProduct(repo, ctx).execute(product.id)
        assert hidden.status == ProductStatus.UNPUBLISHED
        assert any(e[0] == "ProductHidden" for e in events)

    def test_hide_draft_product_raises(self):
        repo = FakeProductRepository()
        product = Product(id=uuid.uuid4(), slug=Slug("x"), name="X")
        repo.save(product)
        ctx, _ = _ctx()
        with pytest.raises(InvalidProductLifecycleTransition):
            HideProduct(repo, ctx).execute(product.id)

    def test_archive_and_restore_round_trip(self):
        repo = FakeProductRepository()
        product = Product(id=uuid.uuid4(), slug=Slug("x"), name="X")
        repo.save(product)
        ctx, events = _ctx()

        archived = ArchiveProduct(repo, ctx).execute(product.id)
        assert archived.status == ProductStatus.ARCHIVED

        restored = RestoreProduct(repo, ctx).execute(product.id)
        assert restored.status == ProductStatus.DRAFT
        event_types = [e[0] for e in events]
        assert "ProductArchived" in event_types
        assert "ProductRestored" in event_types


@pytest.mark.django_db
class TestDeleteProduct:
    def test_delete_requires_archived_status(self):
        repo = FakeProductRepository()
        product = Product(id=uuid.uuid4(), slug=Slug("x"), name="X")
        repo.save(product)
        ctx, _ = _ctx()
        with pytest.raises(InvalidProductLifecycleTransition):
            DeleteProduct(repo, ctx).execute(product.id)

    def test_delete_succeeds_when_archived(self):
        repo = FakeProductRepository()
        product = Product(id=uuid.uuid4(), slug=Slug("x"), name="X", status=ProductStatus.ARCHIVED)
        repo.save(product)
        ctx, events = _ctx()

        DeleteProduct(repo, ctx).execute(product.id)

        assert product.id in repo.deleted_ids
        assert any(e[0] == "ProductDeleted" for e in events)
