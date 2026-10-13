"""
Products read-side selector -- the application-layer orchestration
point for search/filter/facet queries (Django Implementation Blueprint
§3's Selector pattern), sitting above
`infrastructure/selectors.py`'s concrete Postgres FTS query builder.

Kept separate from `application/ports.py::SearchGateway` deliberately:
`SearchGateway` is the Anti-Corruption Layer boundary for a *future*
dedicated search-engine swap-in (Domain Architecture Specification
§2.16); `ProductSelector` is the *current*, launch-stage orchestration
that happens to be backed by Postgres full-text search today. When the
search-engine swap happens, `ProductSelector` starts calling
`SearchGateway` instead of `infrastructure/selectors.py` directly --
this class is the seam, not the destination.
"""
from __future__ import annotations

import uuid
from typing import Protocol


class ProductSearchBackend(Protocol):
    """Matches `infrastructure/selectors.py::DjangoProductSelector`'s shape -- injected so this class never imports infrastructure directly."""

    def search(self, query: str, filters: dict, page: int, page_size: int, sort: str, locale: str | None = None) -> dict: ...
    """`locale` added as a real defect fix: search previously always filtered against `_DEFAULT_LOCALE` ("en") regardless of the requesting user's actual language -- a real gap, since the project already has a single, established `common.utils.localization.resolve_locale()` mechanism for exactly this (Accept-Language header / explicit query param), it was simply never wired into search. Optional and defaults to the platform default, so no existing caller breaks."""

    def autocomplete(self, partial: str, limit: int) -> list[str]: ...


class ProductDetailReader(Protocol):
    """New Protocol, for the search-module barcode/SKU exact-match cascade: matches `infrastructure/selectors.py::ProductDetailSelector.get_by_id`'s shape -- lets `SearchProducts` render an exact match's product card without importing Infrastructure directly."""

    def get_by_id(self, product_id: uuid.UUID, locale: str | None = None) -> dict | None: ...

    def list_facets(self, category_id=None) -> dict: ...


class ProductSelector:
    def __init__(self, backend: ProductSearchBackend) -> None:
        self._backend = backend

    def search(self, query: str, filters: dict, page: int = 1, page_size: int = 20, sort: str = "-created_at", locale: str | None = None) -> dict:
        """
        Returns a dict shaped like:
            {"results": [...ProductCard-ish dicts...], "total_count": N,
             "facets": {"brand": [...], "category": [...], ...}}
        matching Enterprise REST API Blueprint §6's Search Response
        envelope shape (the `search_meta`/`facets` portion), assembled
        here from the backend's raw query results.
        """
        return self._backend.search(query=query, filters=filters, page=page, page_size=page_size, sort=sort, locale=locale)

    def autocomplete(self, partial: str, limit: int = 10) -> list[str]:
        return self._backend.autocomplete(partial=partial, limit=limit)

    def facets(self, category_id=None) -> dict:
        """
        Faceted search metadata: Brand, Category, Flavor, Package Size,
        Product Form, Availability, Nutrition Category, Rating, Price,
        Status -- per this module's mission. Rating/Price facets are
        placeholders here (Reviews and Pricing contexts own that data
        respectively, per Domain Architecture Specification §2.3/§2.11
        -- not yet implemented modules) and are populated with an
        empty range until those contexts exist; every other facet
        (Brand/Category/Flavor/PackageSize/Form/Availability/
        NutritionCategory/Status) is fully computed from Products' own
        data.
        """
        return self._backend.list_facets(category_id=category_id)
