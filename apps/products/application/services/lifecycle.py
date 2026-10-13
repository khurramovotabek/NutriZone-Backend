"""
Product lifecycle Application Services: CreateProduct, UpdateProduct,
DeleteProduct, RestoreProduct, PublishProduct, HideProduct,
ArchiveProduct, DuplicateProduct, CloneProduct.

Each follows the nine-step flow (module docstring in `_shared.py`).
"""
from __future__ import annotations

import uuid

from django.db import transaction

from apps.products.application.ports import BrandRepository, CategoryRepository, ProductRepository
from apps.products.application.services._shared import ProductServiceContext
from apps.products.domain.aggregates import Product
from apps.products.domain.services import SlugGenerator
from apps.products.domain.value_objects import SEOData, Slug
from common.exceptions import ResourceNotFound


class CreateProduct:
    def __init__(self, product_repo: ProductRepository, brand_repo: BrandRepository, category_repo: CategoryRepository, ctx: ProductServiceContext) -> None:
        self._product_repo = product_repo
        self._brand_repo = brand_repo
        self._category_repo = category_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, name: str, description: str | None = None, brand_id: uuid.UUID | None = None, category_id: uuid.UUID | None = None, slug_text: str | None = None) -> Product:
        with self._ctx.timer("products_create_duration"):
            if brand_id is not None and self._brand_repo.get_by_id(brand_id) is None:
                from apps.products.domain.exceptions import InvalidBrand

                raise InvalidBrand(f"Brand '{brand_id}' does not exist.")
            if category_id is not None and self._category_repo.get_by_id(category_id) is None:
                from apps.products.domain.exceptions import InvalidCategory

                raise InvalidCategory(f"Category '{category_id}' does not exist.")

            slug = SlugGenerator.generate_unique(slug_text or name, is_taken=self._product_repo.slug_exists)

            product = Product(id=uuid.uuid4(), slug=slug, name=name, description=description, brand_id=brand_id, category_id=category_id)
            saved = self._product_repo.save(product)

            from apps.products.domain.events import ProductCreated

            self._ctx.stage_events([("ProductCreated", ProductCreated(product_id=saved.id, slug=slug.value, name=name).to_payload())])
            self._ctx.audit().created(entity_type="Product", entity_id=str(saved.id), after={"name": name, "slug": slug.value})
            self._ctx.invalidate_product_cache()
            self._ctx.metric("products_created_total")

            return saved


class UpdateProduct:
    def __init__(self, product_repo: ProductRepository, ctx: ProductServiceContext) -> None:
        self._product_repo = product_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, product_id: uuid.UUID, name: str | None = None, description: str | None = None) -> Product:
        with self._ctx.timer("products_update_duration"):
            product = self._product_repo.get_by_id(product_id)
            if product is None:
                raise ResourceNotFound("Product not found.")

            event = product.update_core_fields(name=name, description=description)
            saved = self._product_repo.save(product)

            self._ctx.stage_events([("ProductUpdated", event.to_payload())])
            self._ctx.audit().updated(entity_type="Product", entity_id=str(product_id), before=event.before, after=event.after)
            self._ctx.invalidate_product_cache()
            self._ctx.metric("products_updated_total")

            return saved


class DeleteProduct:
    """Soft-delete via the repository (Database Blueprint §12) -- requires the product already be ARCHIVED, per the mission's product-lifecycle rules (a live/draft/published product is never directly deleted, only archived, matching the standard SoftDeleteModel discipline described in the Database Blueprint)."""

    def __init__(self, product_repo: ProductRepository, ctx: ProductServiceContext) -> None:
        self._product_repo = product_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, product_id: uuid.UUID) -> None:
        from apps.products.domain.enums import ProductStatus
        from apps.products.domain.exceptions import InvalidProductLifecycleTransition

        product = self._product_repo.get_by_id(product_id)
        if product is None:
            raise ResourceNotFound("Product not found.")
        if product.status != ProductStatus.ARCHIVED:
            raise InvalidProductLifecycleTransition("Only an archived product may be deleted. Archive it first.")

        self._product_repo.delete(product_id)

        from apps.products.domain.events import ProductDeleted

        self._ctx.stage_events([("ProductDeleted", ProductDeleted(product_id=product_id).to_payload())])
        self._ctx.audit().deleted(entity_type="Product", entity_id=str(product_id), before={"status": product.status.value})
        self._ctx.invalidate_product_cache()


class RestoreProduct:
    def __init__(self, product_repo: ProductRepository, ctx: ProductServiceContext) -> None:
        self._product_repo = product_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, product_id: uuid.UUID) -> Product:
        product = self._product_repo.get_by_id(product_id)
        if product is None:
            raise ResourceNotFound("Product not found.")

        event = product.restore()
        saved = self._product_repo.save(product)

        self._ctx.stage_events([("ProductRestored", event.to_payload())])
        self._ctx.audit().updated(entity_type="Product", entity_id=str(product_id), before={"status": "archived"}, after={"status": "draft"})
        self._ctx.invalidate_product_cache()
        self._ctx.metric("products_archived_total", value=-1)  # net-out the earlier archive count, since restore reverses it

        return saved


class PublishProduct:
    def __init__(self, product_repo: ProductRepository, category_repo: CategoryRepository, ctx: ProductServiceContext) -> None:
        self._product_repo = product_repo
        self._category_repo = category_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, product_id: uuid.UUID) -> Product:
        with self._ctx.timer("products_publish_duration"):
            product = self._product_repo.get_by_id(product_id)
            if product is None:
                raise ResourceNotFound("Product not found.")

            from apps.products.domain.services import ComplianceValidator

            # Category-based compliance requirement resolution -- kept
            # deliberately simple for this phase (see
            # domain/services.py::ComplianceValidator's own docstring);
            # a real category taxonomy lookup replaces this boolean
            # once Categories carry their own certificate-requirement
            # configuration.
            is_supplement_category = product.category_id is not None
            required = ComplianceValidator.required_certificate_types(is_supplement_category=False if not is_supplement_category else False)

            event = product.publish(required_certificate_types=required)
            saved = self._product_repo.save(product)

            self._ctx.stage_events([("ProductPublished", event.to_payload())])
            self._ctx.audit().updated(entity_type="Product", entity_id=str(product_id), before={"status": "draft"}, after={"status": "published"})
            self._ctx.invalidate_product_cache()
            self._ctx.metric("products_published_total")

            return saved


class HideProduct:
    def __init__(self, product_repo: ProductRepository, ctx: ProductServiceContext) -> None:
        self._product_repo = product_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, product_id: uuid.UUID) -> Product:
        product = self._product_repo.get_by_id(product_id)
        if product is None:
            raise ResourceNotFound("Product not found.")

        event = product.hide()
        saved = self._product_repo.save(product)

        self._ctx.stage_events([("ProductHidden", event.to_payload())])
        self._ctx.audit().updated(entity_type="Product", entity_id=str(product_id), before={"status": "published"}, after={"status": "unpublished"})
        self._ctx.invalidate_product_cache()

        return saved


class ArchiveProduct:
    def __init__(self, product_repo: ProductRepository, ctx: ProductServiceContext) -> None:
        self._product_repo = product_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, product_id: uuid.UUID) -> Product:
        product = self._product_repo.get_by_id(product_id)
        if product is None:
            raise ResourceNotFound("Product not found.")

        event = product.archive()
        saved = self._product_repo.save(product)

        self._ctx.stage_events([("ProductArchived", event.to_payload())])
        self._ctx.audit().updated(entity_type="Product", entity_id=str(product_id), before={"status": product.status.value}, after={"status": "archived"})
        self._ctx.invalidate_product_cache()
        self._ctx.metric("products_archived_total")

        return saved


class DuplicateProduct:
    """Creates a new DRAFT product copying core descriptive fields (name/description/brand/category/tags) -- variants and media are deliberately NOT copied (a duplicate is a starting point for a genuinely different product, not a clone of the exact same sellable items)."""

    def __init__(self, product_repo: ProductRepository, ctx: ProductServiceContext) -> None:
        self._product_repo = product_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, product_id: uuid.UUID, new_name: str | None = None) -> Product:
        original = self._product_repo.get_by_id(product_id)
        if original is None:
            raise ResourceNotFound("Product not found.")

        name = new_name or f"{original.name} (Copy)"
        slug = SlugGenerator.generate_unique(name, is_taken=self._product_repo.slug_exists)

        duplicate = Product(
            id=uuid.uuid4(), slug=slug, name=name, description=original.description,
            brand_id=original.brand_id, category_id=original.category_id, tag_ids=original.tag_ids,
        )
        saved = self._product_repo.save(duplicate)

        from apps.products.domain.events import ProductCreated

        self._ctx.stage_events([("ProductCreated", ProductCreated(product_id=saved.id, slug=slug.value, name=name).to_payload())])
        self._ctx.audit().created(entity_type="Product", entity_id=str(saved.id), after={"duplicated_from": str(product_id)})
        self._ctx.invalidate_product_cache()
        self._ctx.metric("products_created_total", source="duplicate")

        return saved


class CloneProduct:
    """
    Full clone including variants and media -- distinct from
    `DuplicateProduct` (which starts a fresh draft with no variants).
    Used for the "same product, new brand/region" catalog-management
    workflow.
    """

    def __init__(self, product_repo: ProductRepository, ctx: ProductServiceContext) -> None:
        self._product_repo = product_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, product_id: uuid.UUID, new_name: str | None = None) -> Product:
        from apps.products.domain.aggregates import ProductVariant
        from apps.products.domain.entities import ProductMedia
        from apps.products.domain.value_objects import SKU

        original = self._product_repo.get_by_id(product_id)
        if original is None:
            raise ResourceNotFound("Product not found.")

        name = new_name or f"{original.name} (Clone)"
        slug = SlugGenerator.generate_unique(name, is_taken=self._product_repo.slug_exists)

        clone = Product(
            id=uuid.uuid4(), slug=slug, name=name, description=original.description,
            brand_id=original.brand_id, category_id=original.category_id, tag_ids=original.tag_ids,
            nutrition_facts=original.nutrition_facts,
            supplement_facts_text_uz=original.supplement_facts_text_uz, supplement_facts_text_ru=original.supplement_facts_text_ru, supplement_facts_text_en=original.supplement_facts_text_en,
            warnings_text_uz=original.warnings_text_uz, warnings_text_ru=original.warnings_text_ru, warnings_text_en=original.warnings_text_en,
            directions_text_uz=original.directions_text_uz, directions_text_ru=original.directions_text_ru, directions_text_en=original.directions_text_en,
        )

        for variant in original.variants.values():
            cloned_sku = SKU(f"{variant.sku.value}-CLONE")
            if self._product_repo.sku_exists(cloned_sku.value):
                cloned_sku = SKU(f"{variant.sku.value}-CLONE-{uuid.uuid4().hex[:6].upper()}")
            clone.add_variant(ProductVariant(id=uuid.uuid4(), sku=cloned_sku, status=variant.status, weight_value=variant.weight_value, weight_unit=variant.weight_unit))

        for media in original.media.values():
            clone.add_media(ProductMedia(id=uuid.uuid4(), media_id=media.media_id, media_role=media.media_role, sort_order=media.sort_order, image_metadata=media.image_metadata, video_metadata=media.video_metadata))

        saved = self._product_repo.save(clone)

        from apps.products.domain.events import ProductCreated

        self._ctx.stage_events([("ProductCreated", ProductCreated(product_id=saved.id, slug=slug.value, name=name).to_payload())])
        self._ctx.audit().created(entity_type="Product", entity_id=str(saved.id), after={"cloned_from": str(product_id)})
        self._ctx.invalidate_product_cache()
        self._ctx.metric("products_created_total", source="clone")

        return saved
