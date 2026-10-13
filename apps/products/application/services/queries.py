"""
Query Application Services: SearchProducts, ListProducts,
AdminListProducts, GetProduct.

Read-side use cases -- per Django Implementation Blueprint §3, these
compose the module's Selector (application/selectors.py) rather than
the write-oriented repository methods, and are the concrete
`QueryHandler`-shaped operations `core.query.QueryBus` (Foundation
Hardening phase) can dispatch, though direct instantiation (as
`identity`'s services do) remains equally valid per that module's own
"using the bus is optional" rule.
"""
from __future__ import annotations

import uuid

from apps.products.application.ports import ProductRepository, VariantRepository
from apps.products.application.selectors import ProductDetailReader, ProductSelector
from apps.products.domain.aggregates import Product
from apps.products.domain.value_objects import SKU, Barcode
from common.exceptions import ResourceNotFound, ValidationFailed
from core.caching import CacheDomain, CacheManager
from core.metrics import default_collector


class GetProduct:
    """Public, by-slug lookup -- PUBLISHED products only (Product.is_publicly_visible), cached (CacheManager, PRODUCT domain, never for draft/hidden products per this module's brief's explicit caching rule)."""

    def __init__(self, product_repo: ProductRepository) -> None:
        self._product_repo = product_repo
        self._cache = CacheManager(CacheDomain.PRODUCT)

    def execute(self, slug: str) -> Product:
        cached = self._cache.get("detail", slug)
        if cached is not None:
            # Cache stores only publicly-visible products (see
            # infrastructure/composition.py's cache-population call
            # site) -- a cache hit is always safe to serve directly.
            return cached

        product = self._product_repo.get_by_slug(slug)
        if product is None or not product.is_publicly_visible:
            raise ResourceNotFound("Product not found.")

        self._cache.set("detail", slug, value=product)
        return product


class ListProducts:
    """Public catalog listing -- PUBLISHED products only."""

    def __init__(self, product_repo: ProductRepository) -> None:
        self._product_repo = product_repo

    def execute(self, category_id: uuid.UUID | None = None, brand_id: uuid.UUID | None = None, page: int = 1, page_size: int = 20) -> tuple[list[Product], int]:
        return self._product_repo.list_public(category_id=category_id, brand_id=brand_id, page=page, page_size=page_size)


class AdminListProducts:
    """Staff listing -- all statuses, per `identity.user.view`-equivalent permission at the interfaces layer."""

    def __init__(self, product_repo: ProductRepository) -> None:
        self._product_repo = product_repo

    def execute(self, status: str | None = None, query: str | None = None, page: int = 1, page_size: int = 20) -> tuple[list[Product], int]:
        return self._product_repo.list_for_admin(status=status, query=query, page=page, page_size=page_size)


class SearchProducts:
    """
    Full-text + faceted search -- delegates to `ProductSelector`
    (application/selectors.py), which is the module's read-model
    orchestration layer over `infrastructure/selectors.py`'s concrete
    Postgres FTS query builder (Domain Architecture Specification
    §2.16's launch-stage search approach). Results are cached (SEARCH
    domain) keyed by the full query signature.

    **`variant_repo`/`detail_reader` added for a real, evidenced gap**:
    the public search endpoint previously only ever performed fuzzy
    full-text matching against name/description -- a customer typing
    or scanning an exact SKU/barcode (e.g. from a product label or a
    phone camera) would get generic text-search results, not the exact
    product. Products already owns both the certified `Barcode`/`SKU`
    Domain value objects and exact-lookup repository methods (proven
    by POS's own already-certified integration, Phase Search Module) --
    this reuses them directly, mirroring POS's own proven `SearchProduct`
    cascade (barcode -> SKU -> text) rather than inventing a new one.

    **Both new dependencies are optional and default to `None`**,
    preserving exact prior behavior (full-text only) for any existing
    caller/test not explicitly updated to wire them in.
    """

    def __init__(self, selector: ProductSelector, variant_repo: VariantRepository | None = None, detail_reader: ProductDetailReader | None = None) -> None:
        self._selector = selector
        self._variant_repo = variant_repo
        self._detail_reader = detail_reader
        self._cache = CacheManager(CacheDomain.SEARCH)

    def execute(self, query: str, filters: dict, page: int = 1, page_size: int = 20, sort: str = "-created_at", locale: str | None = None) -> dict:
        """`locale` added as a real defect fix (see `ProductSearchBackend`'s own docstring) -- included in the cache key below, since caching a search result under a locale-blind key would otherwise serve one language's results to a different language's requester."""
        stripped = query.strip() if query else query
        if self._variant_repo is not None and self._detail_reader is not None and stripped:
            exact = self._try_exact_identifier_match(stripped, locale)
            if exact is not None:
                return exact

        cache_key_parts = (query, sorted(filters.items()), page, page_size, sort, locale)
        cached = self._cache.get(*[str(p) for p in cache_key_parts])
        if cached is not None:
            default_collector.counter("catalog_search_total", cache="hit")
            return cached

        result = self._selector.search(query=query, filters=filters, page=page, page_size=page_size, sort=sort, locale=locale)
        self._cache.set(*[str(p) for p in cache_key_parts], value=result)
        default_collector.counter("catalog_search_total", cache="miss")
        return result

    def _try_exact_identifier_match(self, raw: str, locale: str | None) -> dict | None:
        """Mirrors POS's own certified `SearchProduct._try_exact` cascade exactly: a format mismatch or a no-match both silently return None, letting the caller fall through to full-text search -- never raised, since an exact-identifier probe failing just means "this wasn't a barcode/SKU," not an error."""
        for vo_cls, lookup in ((Barcode, self._variant_repo.get_by_barcode), (SKU, self._variant_repo.get_by_sku)):
            try:
                vo_cls(raw)
            except ValidationFailed:
                continue
            match = lookup(raw)
            if match is None:
                continue
            product_id, _variant_id = match
            card = self._detail_reader.get_by_id(product_id, locale=locale)
            if card is None:
                continue
            return {"results": [card], "total_count": 1, "facets": {}}
        return None
