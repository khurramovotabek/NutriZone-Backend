"""
Cart read-side selector -- CQRS-lite application-layer orchestration
point for cart search, matching every prior module's
application/selectors.py pattern.
"""
from __future__ import annotations

from typing import Protocol


class CartSearchBackend(Protocol):
    def search(self, query: str, filters: dict, page: int, page_size: int) -> tuple[list[dict], int]: ...


class CartSelector:
    def __init__(self, backend: CartSearchBackend) -> None:
        self._backend = backend

    def search(self, query: str, filters: dict, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
        return self._backend.search(query=query, filters=filters, page=page, page_size=page_size)
