"""
Products cache integration -- the seven cache groups this module's
brief requires (Product Detail, Catalog List, Brand List, Category
Tree, Search Results, SEO, Filter Options), built on
`core.caching.CacheManager`/`CacheDomain` (Foundation Hardening
phase). Enforces "never cache draft/archived products or mutable
inventory data" as an actual runtime guard, not just a comment --
`cache_product_detail()` below refuses to cache anything but a
PUBLISHED product's read model.
"""
from __future__ import annotations

import uuid

from apps.products.domain.enums import ProductStatus
from core.caching import CacheDomain, CacheManager

_product_cache = CacheManager(CacheDomain.PRODUCT)
_search_cache = CacheManager(CacheDomain.SEARCH)


class NonCacheableProductStatusError(RuntimeError):
    """Raised if code attempts to cache a draft/hidden/archived product -- the mission's explicit 'never cache draft or hidden products' rule, enforced structurally."""


def cache_product_detail(slug: str, product_read_model: dict) -> None:
    if product_read_model.get("status") != ProductStatus.PUBLISHED.value:
        raise NonCacheableProductStatusError(
            f"Refusing to cache product '{slug}': status is '{product_read_model.get('status')}', not 'published'."
        )
    _product_cache.set("detail", slug, value=product_read_model)


def get_cached_product_detail(slug: str) -> dict | None:
    return _product_cache.get("detail", slug)


def cache_catalog_page(cache_key_signature: str, page_data: dict) -> None:
    _product_cache.set("catalog", cache_key_signature, value=page_data)


def get_cached_catalog_page(cache_key_signature: str) -> dict | None:
    return _product_cache.get("catalog", cache_key_signature)


def cache_brand_list(brands: list[dict]) -> None:
    _product_cache.set("brand-list", value=brands)


def get_cached_brand_list() -> list[dict] | None:
    return _product_cache.get("brand-list")


def cache_category_tree(tree: list[dict]) -> None:
    _product_cache.set("category-tree", value=tree)


def get_cached_category_tree() -> list[dict] | None:
    return _product_cache.get("category-tree")


def cache_search_results(query_signature: str, results: dict) -> None:
    _search_cache.set("results", query_signature, value=results)


def get_cached_search_results(query_signature: str) -> dict | None:
    return _search_cache.get("results", query_signature)


def cache_seo(slug: str, seo_data: dict) -> None:
    _product_cache.set("seo", slug, value=seo_data)


def get_cached_seo(slug: str) -> dict | None:
    return _product_cache.get("seo", slug)


def cache_filter_options(category_id: uuid.UUID | None, facets: dict) -> None:
    _product_cache.set("filter-options", str(category_id or "all"), value=facets)


def get_cached_filter_options(category_id: uuid.UUID | None) -> dict | None:
    return _product_cache.get("filter-options", str(category_id or "all"))


def invalidate_all_product_caches() -> None:
    """Called after any product mutation (ProductServiceContext.invalidate_product_cache) -- bumps the whole PRODUCT domain version (O(1), Foundation Hardening phase), covering detail/catalog/brand-list/category-tree/seo/filter-options in one call, since they're all versioned under the same CacheDomain.PRODUCT namespace."""
    _product_cache.invalidate_domain()


def invalidate_search_cache() -> None:
    _search_cache.invalidate_domain()
