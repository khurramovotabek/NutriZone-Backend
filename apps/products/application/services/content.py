"""
Content Application Services: UpdateNutritionFacts, UpdateIngredients,
UpdateWarnings, UpdateDirections, UpdateSEO.

Ingredients/Warnings/Directions are modeled as plain text fields
(`Product.supplement_facts_text`-adjacent JSONB columns at the
infrastructure layer) rather than separate entities -- see
`domain/entities.py`'s module docstring for the same rationale already
applied to `ProductSpecification`: these are descriptive,
order-preserving text content with no independent identity or query
pattern that would justify a dedicated table.
"""
from __future__ import annotations

import uuid

from django.db import transaction

from apps.products.application.ports import ProductRepository
from apps.products.application.services._shared import ProductServiceContext
from apps.products.domain.aggregates import Product
from apps.products.domain.services import NutritionPolicy, SEOGenerator
from apps.products.domain.value_objects import NutritionFacts, SEOData, ServingSize
from common.exceptions import ResourceNotFound


class UpdateNutritionFacts:
    def __init__(self, product_repo: ProductRepository, ctx: ProductServiceContext) -> None:
        self._product_repo = product_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, product_id: uuid.UUID, serving_size_grams: float, servings_per_container: int, calories: float, nutrients: dict[str, float]) -> Product:
        product = self._product_repo.get_by_id(product_id)
        if product is None:
            raise ResourceNotFound("Product not found.")

        facts = NutritionFacts(serving_size=ServingSize(amount_grams=serving_size_grams, servings_per_container=servings_per_container), calories=calories, nutrients=nutrients)
        NutritionPolicy.validate(facts)

        product.update_nutrition_facts(facts)
        saved = self._product_repo.save(product)

        self._ctx.audit().updated(entity_type="Product", entity_id=str(product_id), before={}, after={"calories": calories})
        self._ctx.invalidate_product_cache()

        return saved


class UpdateIngredients:
    def __init__(self, product_repo: ProductRepository, ctx: ProductServiceContext) -> None:
        self._product_repo = product_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, product_id: uuid.UUID, ingredients_text: str, locale: str = "uz") -> Product:
        product = self._product_repo.get_by_id(product_id)
        if product is None:
            raise ResourceNotFound("Product not found.")

        product.update_supplement_facts(ingredients_text, locale)
        saved = self._product_repo.save(product)

        self._ctx.audit().updated(entity_type="Product", entity_id=str(product_id), before={}, after={"ingredients_updated": True, "locale": locale})
        self._ctx.invalidate_product_cache()

        return saved


class UpdateWarnings:
    def __init__(self, product_repo: ProductRepository, ctx: ProductServiceContext) -> None:
        self._product_repo = product_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, product_id: uuid.UUID, warnings_text: str, locale: str = "uz") -> Product:
        product = self._product_repo.get_by_id(product_id)
        if product is None:
            raise ResourceNotFound("Product not found.")

        product.update_warnings(warnings_text, locale)
        saved = self._product_repo.save(product)

        self._ctx.audit().updated(entity_type="Product", entity_id=str(product_id), before={}, after={"warnings_updated": True, "locale": locale})
        self._ctx.invalidate_product_cache()

        return saved


class UpdateDirections:
    def __init__(self, product_repo: ProductRepository, ctx: ProductServiceContext) -> None:
        self._product_repo = product_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, product_id: uuid.UUID, directions_text: str, locale: str = "uz") -> Product:
        product = self._product_repo.get_by_id(product_id)
        if product is None:
            raise ResourceNotFound("Product not found.")

        product.update_directions(directions_text, locale)
        saved = self._product_repo.save(product)

        self._ctx.audit().updated(entity_type="Product", entity_id=str(product_id), before={}, after={"directions_updated": True, "locale": locale})
        self._ctx.invalidate_product_cache()

        return saved


class UpdateSEO:
    def __init__(self, product_repo: ProductRepository, ctx: ProductServiceContext) -> None:
        self._product_repo = product_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, product_id: uuid.UUID, meta_title: str | None = None, meta_description: str | None = None) -> Product:
        product = self._product_repo.get_by_id(product_id)
        if product is None:
            raise ResourceNotFound("Product not found.")

        seo = SEOData(
            meta_title=meta_title if meta_title is not None else product.seo.meta_title,
            meta_description=meta_description if meta_description is not None else product.seo.meta_description,
            canonical_slug=product.slug,
        )
        event = product.update_seo(seo)
        saved = self._product_repo.save(product)

        self._ctx.stage_events([("ProductSEOUpdated", event.to_payload())])
        self._ctx.audit().updated(entity_type="Product", entity_id=str(product_id), before={}, after={"meta_title": seo.meta_title})
        self._ctx.invalidate_product_cache()

        return saved
