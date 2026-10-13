"""
Geo & Location read-side selector -- CQRS-lite application-layer
orchestration point for location search, matching
`apps.products.application.selectors.ProductSelector`'s exact pattern.
"""
from __future__ import annotations

from typing import Protocol


class GeoSearchBackend(Protocol):
    """Matches `infrastructure/selectors.py::DjangoGeoSearchBackend`'s shape."""

    def search(self, query: str, geo_level: str | None, page: int, page_size: int) -> tuple[list[dict], int]: ...

    def autocomplete(self, partial: str, limit: int) -> list[str]: ...


class GeoSelector:
    def __init__(self, backend: GeoSearchBackend) -> None:
        self._backend = backend

    def search(self, query: str, geo_level: str | None = None, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
        return self._backend.search(query=query, geo_level=geo_level, page=page, page_size=page_size)

    def autocomplete(self, partial: str, limit: int = 10) -> list[str]:
        return self._backend.autocomplete(partial=partial, limit=limit)
