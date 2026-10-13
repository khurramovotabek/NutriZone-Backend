"""
Variant Application Services: CreateVariant, UpdateVariant,
DeleteVariant, SetDefaultVariant.
"""
from __future__ import annotations

import uuid

from django.db import transaction

from apps.products.application.ports import PackageRepository, ProductRepository
from apps.products.application.services._shared import ProductServiceContext
from apps.products.domain.aggregates import Product, ProductVariant
from apps.products.domain.enums import VariantStatus, WeightUnit
from apps.products.domain.services import VariantPolicy
from apps.products.domain.value_objects import SKU, Barcode
from common.exceptions import ResourceNotFound


class CreateVariant:
    def __init__(self, product_repo: ProductRepository, package_repo: PackageRepository, ctx: ProductServiceContext) -> None:
        self._product_repo = product_repo
        self._package_repo = package_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, product_id: uuid.UUID, sku: str, barcode: str | None = None, weight_value: float | None = None, weight_unit: str = WeightUnit.GRAM.value, package_id: uuid.UUID | None = None) -> Product:
        product = self._product_repo.get_by_id(product_id)
        if product is None:
            raise ResourceNotFound("Product not found.")

        if self._product_repo.sku_exists(sku):
            from apps.products.domain.exceptions import DuplicateSKU

            raise DuplicateSKU(f"SKU '{sku}' already exists in the catalog.")
        if barcode and self._product_repo.barcode_exists(barcode):
            from apps.products.domain.exceptions import DuplicateBarcode

            raise DuplicateBarcode(f"Barcode '{barcode}' already exists in the catalog.")
        if package_id is not None and self._package_repo.get_by_id(package_id) is None:
            from apps.products.domain.exceptions import InvalidPackage

            raise InvalidPackage(f"Package '{package_id}' does not exist.")

        VariantPolicy.assert_within_limit(len(product.variants))

        variant = ProductVariant(
            id=uuid.uuid4(), sku=SKU(sku), barcode=Barcode(barcode) if barcode else None, weight_value=weight_value, weight_unit=WeightUnit(weight_unit), package_id=package_id
        )
        event = product.add_variant(variant)
        saved = self._product_repo.save(product)

        self._ctx.stage_events([("ProductVariantCreated", event.to_payload())])
        self._ctx.audit().created(entity_type="ProductVariant", entity_id=str(variant.id), after={"sku": sku})
        self._ctx.invalidate_product_cache()
        self._ctx.metric("variants_created_total")

        return saved


class UpdateVariant:
    def __init__(self, product_repo: ProductRepository, package_repo: PackageRepository, ctx: ProductServiceContext) -> None:
        self._product_repo = product_repo
        self._package_repo = package_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, product_id: uuid.UUID, variant_id: uuid.UUID, status: str | None = None, weight_value: float | None = None, weight_unit: str | None = None, package_id: uuid.UUID | None = None) -> Product:
        from apps.products.domain.exceptions import InvalidVariant

        product = self._product_repo.get_by_id(product_id)
        if product is None:
            raise ResourceNotFound("Product not found.")
        variant = product.variants.get(variant_id)
        if variant is None:
            raise InvalidVariant(f"Variant '{variant_id}' does not belong to this product.")
        if package_id is not None and self._package_repo.get_by_id(package_id) is None:
            from apps.products.domain.exceptions import InvalidPackage

            raise InvalidPackage(f"Package '{package_id}' does not exist.")

        before = {"status": variant.status.value, "weight_value": variant.weight_value, "weight_unit": variant.weight_unit.value, "package_id": str(variant.package_id) if variant.package_id else None}
        if status is not None:
            variant.status = VariantStatus(status)
        if weight_value is not None:
            variant.weight_value = weight_value
        if weight_unit is not None:
            variant.weight_unit = WeightUnit(weight_unit)
        if package_id is not None:
            variant.package_id = package_id
        after = {"status": variant.status.value, "weight_value": variant.weight_value, "weight_unit": variant.weight_unit.value, "package_id": str(variant.package_id) if variant.package_id else None}

        saved = self._product_repo.save(product)

        from apps.products.domain.events import ProductVariantUpdated

        self._ctx.stage_events([("ProductVariantUpdated", ProductVariantUpdated(product_id=product_id, variant_id=variant_id, before=before, after=after).to_payload())])
        self._ctx.audit().updated(entity_type="ProductVariant", entity_id=str(variant_id), before=before, after=after)
        self._ctx.invalidate_product_cache()

        return saved


class DeleteVariant:
    def __init__(self, product_repo: ProductRepository, ctx: ProductServiceContext) -> None:
        self._product_repo = product_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, product_id: uuid.UUID, variant_id: uuid.UUID) -> Product:
        from apps.products.domain.exceptions import InvalidVariant

        product = self._product_repo.get_by_id(product_id)
        if product is None:
            raise ResourceNotFound("Product not found.")
        if variant_id not in product.variants:
            raise InvalidVariant(f"Variant '{variant_id}' does not belong to this product.")

        product.remove_variant(variant_id)
        saved = self._product_repo.save(product)

        from apps.products.domain.events import ProductVariantDeleted

        self._ctx.stage_events([("ProductVariantDeleted", ProductVariantDeleted(product_id=product_id, variant_id=variant_id).to_payload())])
        self._ctx.audit().deleted(entity_type="ProductVariant", entity_id=str(variant_id), before={"product_id": str(product_id)})
        self._ctx.invalidate_product_cache()

        return saved


class SetDefaultVariant:
    def __init__(self, product_repo: ProductRepository, ctx: ProductServiceContext) -> None:
        self._product_repo = product_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, product_id: uuid.UUID, variant_id: uuid.UUID) -> Product:
        product = self._product_repo.get_by_id(product_id)
        if product is None:
            raise ResourceNotFound("Product not found.")

        product.set_default_variant(variant_id)
        saved = self._product_repo.save(product)

        self._ctx.audit().updated(entity_type="Product", entity_id=str(product_id), before={}, after={"default_variant_id": str(variant_id)})
        self._ctx.invalidate_product_cache()

        return saved
