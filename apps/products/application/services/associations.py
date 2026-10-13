"""
Association Application Services: AssignBrand, AssignCategory,
AssignTags, AssignFlavours.
"""
from __future__ import annotations

import uuid

from django.db import transaction

from apps.products.application.ports import (
    BrandRepository,
    CategoryRepository,
    FlavourRepository,
    ProductRepository,
    TagRepository,
)
from apps.products.application.services._shared import ProductServiceContext
from apps.products.domain.aggregates import Product
from common.exceptions import ResourceNotFound


class AssignBrand:
    def __init__(self, product_repo: ProductRepository, brand_repo: BrandRepository, ctx: ProductServiceContext) -> None:
        self._product_repo = product_repo
        self._brand_repo = brand_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, product_id: uuid.UUID, brand_id: uuid.UUID | None) -> Product:
        product = self._product_repo.get_by_id(product_id)
        if product is None:
            raise ResourceNotFound("Product not found.")
        if brand_id is not None and self._brand_repo.get_by_id(brand_id) is None:
            from apps.products.domain.exceptions import InvalidBrand

            raise InvalidBrand(f"Brand '{brand_id}' does not exist.")

        event = product.assign_brand(brand_id)
        saved = self._product_repo.save(product)

        self._ctx.stage_events([("BrandAssigned", event.to_payload())])
        self._ctx.audit().updated(entity_type="Product", entity_id=str(product_id), before={}, after={"brand_id": str(brand_id) if brand_id else None})
        self._ctx.invalidate_product_cache()

        return saved


class AssignCategory:
    def __init__(self, product_repo: ProductRepository, category_repo: CategoryRepository, ctx: ProductServiceContext) -> None:
        self._product_repo = product_repo
        self._category_repo = category_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, product_id: uuid.UUID, category_id: uuid.UUID | None) -> Product:
        product = self._product_repo.get_by_id(product_id)
        if product is None:
            raise ResourceNotFound("Product not found.")
        if category_id is not None and self._category_repo.get_by_id(category_id) is None:
            from apps.products.domain.exceptions import InvalidCategory

            raise InvalidCategory(f"Category '{category_id}' does not exist.")

        event = product.assign_category(category_id)
        saved = self._product_repo.save(product)

        self._ctx.stage_events([("CategoryAssigned", event.to_payload())])
        self._ctx.audit().updated(entity_type="Product", entity_id=str(product_id), before={}, after={"category_id": str(category_id) if category_id else None})
        self._ctx.invalidate_product_cache()

        return saved


class AssignTags:
    def __init__(self, product_repo: ProductRepository, tag_repo: TagRepository, ctx: ProductServiceContext) -> None:
        self._product_repo = product_repo
        self._tag_repo = tag_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, product_id: uuid.UUID, tag_ids: frozenset[uuid.UUID]) -> Product:
        product = self._product_repo.get_by_id(product_id)
        if product is None:
            raise ResourceNotFound("Product not found.")

        found = self._tag_repo.get_many_by_ids(tag_ids)
        if len(found) != len(tag_ids):
            from common.exceptions import ValidationFailed

            raise ValidationFailed("One or more tag_ids do not exist.", details={"fields": [{"field": "tag_ids", "code": "INVALID_REFERENCE"}]})

        product.assign_tags(tag_ids)
        saved = self._product_repo.save(product)

        self._ctx.audit().updated(entity_type="Product", entity_id=str(product_id), before={}, after={"tag_ids": [str(t) for t in tag_ids]})
        self._ctx.invalidate_product_cache()

        return saved


class AssignFlavours:
    """
    Product-level, not variant-level -- a Flavour tags the whole
    Product (one Product carries many Flavours; one Flavour tags many
    Products), the exact same many-to-many shape AssignTags already
    uses above, never an owned child entity.
    """

    def __init__(self, product_repo: ProductRepository, flavour_repo: FlavourRepository, ctx: ProductServiceContext) -> None:
        self._product_repo = product_repo
        self._flavour_repo = flavour_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, product_id: uuid.UUID, flavour_ids: frozenset[uuid.UUID]) -> Product:
        product = self._product_repo.get_by_id(product_id)
        if product is None:
            raise ResourceNotFound("Product not found.")

        found = self._flavour_repo.get_many_by_ids(flavour_ids)
        if len(found) != len(flavour_ids):
            from common.exceptions import ValidationFailed

            raise ValidationFailed("One or more flavour_ids do not exist.", details={"fields": [{"field": "flavour_ids", "code": "INVALID_REFERENCE"}]})

        product.assign_flavours(flavour_ids)
        saved = self._product_repo.save(product)

        self._ctx.audit().updated(entity_type="Product", entity_id=str(product_id), before={}, after={"flavour_ids": [str(f) for f in flavour_ids]})
        self._ctx.invalidate_product_cache()

        return saved
