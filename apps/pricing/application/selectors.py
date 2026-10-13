"""
Pricing read-side selector -- CQRS-lite application-layer
orchestration point for pricing search, matching every prior module's
application/selectors.py pattern.
"""
from __future__ import annotations

from typing import Protocol


class PricingSearchBackend(Protocol):
    def search(self, query: str, filters: dict, page: int, page_size: int) -> tuple[list[dict], int]: ...


class PricingSelector:
    def __init__(self, backend: PricingSearchBackend) -> None:
        self._backend = backend

    def search(self, query: str, filters: dict, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
        return self._backend.search(query=query, filters=filters, page=page, page_size=page_size)
