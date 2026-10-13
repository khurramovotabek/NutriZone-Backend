from __future__ import annotations

import pytest

from apps.products.domain.enums import ProductStatus
from apps.products.infrastructure.cache import (
    NonCacheableProductStatusError,
    cache_brand_list,
    cache_catalog_page,
    cache_category_tree,
    cache_filter_options,
    cache_product_detail,
    cache_search_results,
    cache_seo,
    get_cached_brand_list,
    get_cached_catalog_page,
    get_cached_category_tree,
    get_cached_filter_options,
    get_cached_product_detail,
    get_cached_search_results,
    get_cached_seo,
    invalidate_all_product_caches,
    invalidate_search_cache,
)

pytestmark = pytest.mark.unit


def test_cache_product_detail_refuses_draft_products():
    with pytest.raises(NonCacheableProductStatusError):
        cache_product_detail("draft-slug", {"status": ProductStatus.DRAFT.value})


def test_cache_product_detail_refuses_archived_products():
    with pytest.raises(NonCacheableProductStatusError):
        cache_product_detail("archived-slug", {"status": ProductStatus.ARCHIVED.value})


def test_cache_product_detail_accepts_published():
    cache_product_detail("published-slug", {"status": ProductStatus.PUBLISHED.value, "name": "X"})
    assert get_cached_product_detail("published-slug") == {"status": "published", "name": "X"}


def test_get_cached_product_detail_miss_returns_none():
    assert get_cached_product_detail("never-cached") is None


def test_catalog_page_cache_round_trip():
    cache_catalog_page("page-1", {"results": []})
    assert get_cached_catalog_page("page-1") == {"results": []}


def test_brand_list_cache_round_trip():
    cache_brand_list([{"id": "1", "name": "ON"}])
    assert get_cached_brand_list() == [{"id": "1", "name": "ON"}]


def test_category_tree_cache_round_trip():
    cache_category_tree([{"id": "1", "name": "Protein"}])
    assert get_cached_category_tree() == [{"id": "1", "name": "Protein"}]


def test_search_results_cache_round_trip():
    cache_search_results("query-sig", {"total_count": 5})
    assert get_cached_search_results("query-sig") == {"total_count": 5}


def test_seo_cache_round_trip():
    cache_seo("whey-protein", {"meta_title": "Whey"})
    assert get_cached_seo("whey-protein") == {"meta_title": "Whey"}


def test_filter_options_cache_round_trip():
    cache_filter_options(None, {"brand": []})
    assert get_cached_filter_options(None) == {"brand": []}


def test_invalidate_all_product_caches_clears_detail_and_catalog():
    cache_product_detail("x", {"status": "published"})
    cache_catalog_page("y", {"data": 1})
    invalidate_all_product_caches()
    assert get_cached_product_detail("x") is None
    assert get_cached_catalog_page("y") is None


def test_invalidate_search_cache_clears_search_results():
    cache_search_results("z", {"total_count": 1})
    invalidate_search_cache()
    assert get_cached_search_results("z") is None
