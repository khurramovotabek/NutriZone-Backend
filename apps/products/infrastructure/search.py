"""
Concrete `SearchGateway` (application/ports.py) -- the Anti-Corruption
Layer boundary for the future dedicated search-engine swap-in (Domain
Architecture Specification §2.16). For this phase, delegates entirely
to `infrastructure/selectors.py::DjangoProductSearchBackend` (Postgres
full-text search) -- when a dedicated search engine is introduced,
only this file's internals change; `application/ports.py::SearchGateway`
and every caller of it stay untouched.
"""
from __future__ import annotations

import uuid

from apps.products.infrastructure.selectors import DjangoProductSearchBackend


class PostgresSearchGateway:
    def __init__(self) -> None:
        self._backend = DjangoProductSearchBackend()

    def index_product(self, product) -> None:
        """
        No-op for the Postgres FTS backend: the search index *is* the
        `catalog_product_translations` table itself (GIN-indexed, per
        Enterprise Database Blueprint §15), already kept current by
        `DjangoProductRepository.save()` -- there is no separate index
        to push to. A dedicated search-engine implementation of this
        Protocol would replace this no-op with a real indexing call.
        """

    def remove_from_index(self, product_id: uuid.UUID) -> None:
        """Same rationale as index_product -- soft-deleting/un-publishing the product (already handled by the repository) is what removes it from FTS results, since search only ever queries PUBLISHED products."""

    def search(self, query: str, filters: dict, page: int, page_size: int) -> tuple[list[uuid.UUID], int, dict]:
        result = self._backend.search(query=query, filters=filters, page=page, page_size=page_size, sort="-created_at")
        product_ids = [uuid.UUID(r["id"]) for r in result["results"]]
        return product_ids, result["total_count"], result["facets"]
