"""
Application-layer ports (abstract interfaces).

`application/services/` depends only on these Protocols, never on
`infrastructure/repositories.py` concrete classes directly (Django
Implementation Blueprint §4) -- matching the pattern established by
`apps/identity/application/ports.py`. Cross-cutting ports
(Clock/Metrics/Audit/Outbox/Health/Cache) are NOT redefined here --
`core/clock`, `core/metrics`, `core/audit`, `core/outbox`,
`core/health`, `core/caching` already provide them platform-wide, per
the Foundation Hardening phase; this module's brief listing them under
"Ports" is satisfied by importing those `core/` modules directly in
`application/services/`, exactly as `identity` already does, not by
re-declaring redundant Protocols for infrastructure that's already
generic and platform-wide.
"""
from __future__ import annotations

import uuid
from typing import Protocol

from apps.products.domain.aggregates import Brand, Category, Flavour, Package, Product, Tag
from apps.products.domain.entities import ProductMedia


class ProductRepository(Protocol):
    def get_by_id(self, product_id: uuid.UUID) -> Product | None: ...

    def get_by_slug(self, slug: str) -> Product | None: ...

    def save(self, product: Product) -> Product: ...

    def slug_exists(self, slug: str, exclude_product_id: uuid.UUID | None = None) -> bool: ...

    def sku_exists(self, sku: str, exclude_product_id: uuid.UUID | None = None) -> bool: ...

    def barcode_exists(self, barcode: str, exclude_product_id: uuid.UUID | None = None) -> bool: ...

    def list_public(
        self,
        category_id: uuid.UUID | None = None,
        brand_id: uuid.UUID | None = None,
        tag_ids: frozenset[uuid.UUID] | None = None,
        query: str | None = None,
        page: int = 1,
        page_size: int = 20,
        ordering: str = "-created_at",
    ) -> tuple[list[Product], int]:
        """Returns (page of PUBLISHED products only, total_count) -- draft/hidden/archived products are never returned by this method (MIC §6's Never-Cache/never-serve rule for non-public products)."""
        ...

    def list_for_admin(
        self,
        status: str | None = None,
        query: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Product], int]: ...

    def delete(self, product_id: uuid.UUID) -> None:
        """Soft delete, per Database Blueprint §12 -- an ARCHIVED product may additionally be soft-deleted from the admin catalog listing."""
        ...


class BrandRepository(Protocol):
    def get_by_id(self, brand_id: uuid.UUID) -> Brand | None: ...

    def get_by_slug(self, slug: str) -> Brand | None: ...

    def save(self, brand: Brand) -> Brand: ...

    def slug_exists(self, slug: str, exclude_brand_id: uuid.UUID | None = None) -> bool: ...

    def list_active(self) -> list[Brand]: ...


class ManufacturerRepository(Protocol):
    """
    Distinct Protocol per this module's brief, backed by the same
    underlying `brands` table filtered to `is_manufacturer=True` --
    see `domain/aggregates.py::Manufacturer`'s docstring for the full
    reconciliation.
    """

    def get_by_id(self, manufacturer_id: uuid.UUID) -> Brand | None: ...

    def save(self, manufacturer: Brand) -> Brand: ...

    def list_active(self) -> list[Brand]: ...


class CategoryRepository(Protocol):
    def get_by_id(self, category_id: uuid.UUID) -> Category | None: ...

    def get_by_slug(self, slug: str) -> Category | None: ...

    def save(self, category: Category) -> Category: ...

    def slug_exists(self, slug: str, exclude_category_id: uuid.UUID | None = None) -> bool: ...

    def list_tree(self) -> list[Category]: ...


class VariantRepository(Protocol):
    """
    Variants are entities owned by the Product aggregate (Domain
    Architecture Specification §2.2) -- this Protocol exists for the
    read-side convenience of looking a variant up by SKU/barcode
    without loading the full parent Product, per this module's brief's
    explicit request for a `VariantRepository` port. Writes always go
    through `ProductRepository.save(product)`, never through this
    Protocol directly (an entity has no independent persistence
    lifecycle from its aggregate root).
    """

    def get_product_id_for_variant(self, variant_id: uuid.UUID) -> uuid.UUID | None: ...

    def get_by_sku(self, sku: str) -> tuple[uuid.UUID, uuid.UUID] | None:
        """Returns (product_id, variant_id) or None."""
        ...

    def get_by_barcode(self, barcode: str) -> tuple[uuid.UUID, uuid.UUID] | None:
        """Returns (product_id, variant_id) or None. Added for the POS Search module -- mirrors `get_by_sku()` exactly, per that module's explicitly authorized minimal cross-context extension."""
        ...


class FlavourRepository(Protocol):
    def get_by_id(self, flavour_id: uuid.UUID) -> Flavour | None: ...

    def get_by_slug(self, slug: str) -> Flavour | None: ...

    def get_many_by_ids(self, flavour_ids: frozenset[uuid.UUID]) -> list[Flavour]: ...

    def save(self, flavour: Flavour) -> Flavour: ...

    def list_active(self) -> list[Flavour]: ...


class PackageRepository(Protocol):
    """Backs `ProductVariant.package_id` -- a single FK, not a M2M (see domain/aggregates.py::Package's own docstring)."""

    def get_by_id(self, package_id: uuid.UUID) -> Package | None: ...

    def get_by_slug(self, slug: str) -> Package | None: ...

    def save(self, package: Package) -> Package: ...

    def list_active(self) -> list[Package]: ...


class MediaRepository(Protocol):
    """
    Persists `ProductMedia` rows (owned by Product, per Domain
    Architecture Specification §2.2) -- like `VariantRepository`,
    writes ultimately flow through `ProductRepository.save()`; this
    Protocol backs read-side lookups the brief's "DeleteImage"/
    "DeleteVideo"/"DeleteDocument" services need (resolving a bare
    media_id to its owning product before loading the aggregate).
    """

    def get_product_id_for_media(self, media_id: uuid.UUID) -> uuid.UUID | None: ...


class TagRepository(Protocol):
    def get_by_code(self, code: str) -> Tag | None: ...

    def get_many_by_ids(self, tag_ids: frozenset[uuid.UUID]) -> list[Tag]: ...

    def save(self, tag: Tag) -> Tag: ...

    def list_all(self) -> list[Tag]: ...


class SpecificationRepository(Protocol):
    """
    Specifications are stored as a JSONB column on `Product`
    (domain/entities.py::ProductSpecification's docstring) -- this
    Protocol is a read-side convenience for cross-product
    specification-key lookups (e.g. "which products declare a
    'Protein per serving' spec"), not an independent write path.
    """

    def list_distinct_keys(self) -> list[str]: ...


class SearchGateway(Protocol):
    """
    Anti-Corruption Layer boundary for the future dedicated
    search-engine swap-in (Domain Architecture Specification §2.16) --
    for this phase, backed by Postgres full-text search
    (infrastructure/repositories.py), never a live query built ad hoc
    in `application/`.
    """

    def index_product(self, product: Product) -> None: ...

    def remove_from_index(self, product_id: uuid.UUID) -> None: ...

    def search(self, query: str, filters: dict, page: int, page_size: int) -> tuple[list[uuid.UUID], int, dict]:
        """Returns (ordered product_ids, total_count, facets)."""
        ...


class StorageGateway(Protocol):
    """Matches `core.storage.MediaStorageBackend`'s shape -- re-declared as a Protocol here only so `application/ports.py` is self-contained for this module's own composition root; the concrete implementation is `core.storage.get_storage_backend()`, unchanged from the Foundation phase."""

    def save(self, path: str, content: bytes) -> str: ...
