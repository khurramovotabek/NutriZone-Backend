"""
Products domain entities (non-root members of an aggregate -- no
independent lifecycle of their own, always accessed/mutated through
their owning aggregate root in aggregates.py).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from apps.products.domain.enums import CertificateType, MediaRole, SpecificationType
from apps.products.domain.value_objects import DocumentMetadata, ImageMetadata, VideoMetadata


@dataclass(slots=True)
class ProductMedia:
    """
    Non-root entity, owned by Product (or a specific Variant) --
    Database Blueprint §4.2 `catalog.product_media`. Unifies Image,
    Video, and Document per that table's actual schema (one table,
    `media_role` discriminates) rather than three separate tables.
    """

    id: uuid.UUID
    media_id: uuid.UUID  # self-referential now that the separate Media Asset table is removed (was: cross-schema ref to content.media_library) -- equals `id` above by construction.
    media_role: MediaRole
    storage_path: str = ""
    thumbnail_paths: dict = field(default_factory=dict)
    sort_order: int = 0
    variant_id: uuid.UUID | None = None
    image_metadata: ImageMetadata | None = None
    video_metadata: VideoMetadata | None = None
    document_metadata: DocumentMetadata | None = None


@dataclass(slots=True)
class Certificate:
    """Non-root entity -- Database Blueprint §4.2 `catalog.certificates`."""

    id: uuid.UUID
    certificate_type: CertificateType
    issuing_body: str
    document_media_id: uuid.UUID
    valid_from: datetime
    valid_until: datetime | None = None

    def is_expired(self, as_of: datetime) -> bool:
        return self.valid_until is not None and as_of >= self.valid_until


@dataclass(slots=True)
class RelatedProduct:
    """Non-root entity -- Database Blueprint §4.2 `catalog.product_recommendations`."""

    id: uuid.UUID
    product_id: uuid.UUID
    related_product_id: uuid.UUID
    relation_type: str
    sort_order: int = 0


@dataclass(slots=True)
class ProductSpecification:
    """
    Non-root entity, owned by Product -- free-form key/value
    specifications (e.g. "Protein per serving": "24g") distinct from
    the structured `NutritionFacts` value object. Not a Database
    Blueprint table on its own; persisted as a JSONB column on
    `catalog.products` (a documented, additive storage choice --
    specifications are descriptive, order-preserving key/value pairs
    with no independent query/index requirement of their own, so a
    dedicated table would add schema weight without a matching
    read-pattern need).
    """

    key: str
    value: str
    spec_type: SpecificationType = SpecificationType.TEXT
    sort_order: int = 0
