"""
Products domain events.

Registered against `core.events.registry` via
`shared/event_contracts/products.py`, imported once from
`ProductsConfig.ready()` -- matching the pattern established by
`apps/identity/domain/events.py`.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class ProductCreated:
    product_id: uuid.UUID
    slug: str
    name: str

    def to_payload(self) -> dict:
        return {**asdict(self), "product_id": str(self.product_id)}


@dataclass(frozen=True, slots=True)
class ProductUpdated:
    product_id: uuid.UUID
    before: dict
    after: dict

    def to_payload(self) -> dict:
        return {**asdict(self), "product_id": str(self.product_id)}


@dataclass(frozen=True, slots=True)
class ProductPublished:
    product_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"product_id": str(self.product_id)}


@dataclass(frozen=True, slots=True)
class ProductHidden:
    """
    Emitted by `Product.hide()`. The persisted status stays
    'unpublished' (Database Blueprint §4.2 `catalog.products.status`)
    -- 'Hidden' is this module's public-facing vocabulary for that
    same state, per `domain/enums.py::ProductStatus`'s reconciliation
    note; the event name matches the brief's vocabulary exactly.
    """

    product_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"product_id": str(self.product_id)}


@dataclass(frozen=True, slots=True)
class ProductArchived:
    product_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"product_id": str(self.product_id)}


@dataclass(frozen=True, slots=True)
class ProductRestored:
    product_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"product_id": str(self.product_id)}


@dataclass(frozen=True, slots=True)
class ProductDeleted:
    product_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"product_id": str(self.product_id)}


@dataclass(frozen=True, slots=True)
class BrandAssigned:
    product_id: uuid.UUID
    brand_id: uuid.UUID | None

    def to_payload(self) -> dict:
        return {"product_id": str(self.product_id), "brand_id": str(self.brand_id) if self.brand_id else None}


@dataclass(frozen=True, slots=True)
class CategoryAssigned:
    product_id: uuid.UUID
    category_id: uuid.UUID | None

    def to_payload(self) -> dict:
        return {"product_id": str(self.product_id), "category_id": str(self.category_id) if self.category_id else None}


@dataclass(frozen=True, slots=True)
class ProductVariantCreated:
    product_id: uuid.UUID
    variant_id: uuid.UUID
    sku: str

    def to_payload(self) -> dict:
        return {**asdict(self), "product_id": str(self.product_id), "variant_id": str(self.variant_id)}


@dataclass(frozen=True, slots=True)
class ProductVariantUpdated:
    product_id: uuid.UUID
    variant_id: uuid.UUID
    before: dict
    after: dict

    def to_payload(self) -> dict:
        return {**asdict(self), "product_id": str(self.product_id), "variant_id": str(self.variant_id)}


@dataclass(frozen=True, slots=True)
class ProductVariantDeleted:
    product_id: uuid.UUID
    variant_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"product_id": str(self.product_id), "variant_id": str(self.variant_id)}


@dataclass(frozen=True, slots=True)
class ProductMediaUploaded:
    product_id: uuid.UUID
    media_id: uuid.UUID
    media_role: str

    def to_payload(self) -> dict:
        return {**asdict(self), "product_id": str(self.product_id), "media_id": str(self.media_id)}


@dataclass(frozen=True, slots=True)
class ProductMediaDeleted:
    product_id: uuid.UUID
    media_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"product_id": str(self.product_id), "media_id": str(self.media_id)}


@dataclass(frozen=True, slots=True)
class ProductSEOUpdated:
    product_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"product_id": str(self.product_id)}


@dataclass(frozen=True, slots=True)
class CertificateAttached:
    product_id: uuid.UUID
    certificate_id: uuid.UUID
    certificate_type: str

    def to_payload(self) -> dict:
        return {**asdict(self), "product_id": str(self.product_id), "certificate_id": str(self.certificate_id)}
