"""
Phase 02J's product recommendations test matrix. Real PostgreSQL
throughout; drives the real HTTP endpoint, using the same
`_published_product`-style helper `test_api_integration.py` already
establishes for this module.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework.test import APIClient

from apps.products.domain.aggregates import Product, ProductVariant
from apps.products.domain.entities import ProductMedia
from apps.products.domain.enums import MediaRole
from apps.products.domain.value_objects import SKU, Slug
from apps.products.infrastructure.repositories import DjangoProductRepository

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


def _real_category() -> uuid.UUID:
    from apps.products.infrastructure import models as orm
    return orm.Category.objects.create().id


def _published_product(slug: str, category_id=None, sku_suffix: str = None) -> Product:
    from apps.products.infrastructure import models as orm
    suffix = sku_suffix or uuid.uuid4().hex[:8].upper()
    product = Product(id=uuid.uuid4(), slug=Slug(slug), name=f"Product {slug}", category_id=category_id)
    product.add_variant(ProductVariant(id=uuid.uuid4(), sku=SKU(f"SKU-{suffix}")))
    product.add_media(ProductMedia(id=uuid.uuid4(), media_id=uuid.uuid4(), media_role=MediaRole.PRIMARY, storage_path=f"products/{slug}.jpg"))
    product.publish()
    return product


class TestRecommendationsBasic:
    def test_unknown_product_returns_404(self, api_client):
        response = api_client.get("/api/v1/products/does-not-exist/recommendations")
        assert response.status_code == 404

    def test_product_with_no_category_and_no_curated_returns_empty(self, api_client):
        repo = DjangoProductRepository()
        repo.save(_published_product("standalone-item"))
        response = api_client.get("/api/v1/products/standalone-item/recommendations")
        assert response.status_code == 200
        assert response.json()["data"] == []

    def test_anonymous_access_allowed(self, api_client):
        """Recommendations for a public product page are themselves public -- no auth required, matching ProductDetailView's own AllowAny precedent."""
        repo = DjangoProductRepository()
        repo.save(_published_product("anon-test-item"))
        response = api_client.get("/api/v1/products/anon-test-item/recommendations")
        assert response.status_code == 200


class TestSimilarCategoryFallback:
    def test_same_category_products_recommended(self, api_client):
        category_id = _real_category()
        repo = DjangoProductRepository()
        repo.save(_published_product("cat-main", category_id=category_id))
        repo.save(_published_product("cat-sibling-a", category_id=category_id))
        repo.save(_published_product("cat-sibling-b", category_id=category_id))

        response = api_client.get("/api/v1/products/cat-main/recommendations")
        assert response.status_code == 200
        slugs = {item["slug"] for item in response.json()["data"]}
        assert slugs == {"cat-sibling-a", "cat-sibling-b"}

    def test_current_product_excluded_from_its_own_recommendations(self, api_client):
        category_id = _real_category()
        repo = DjangoProductRepository()
        repo.save(_published_product("self-exclude-main", category_id=category_id))
        repo.save(_published_product("self-exclude-other", category_id=category_id))

        response = api_client.get("/api/v1/products/self-exclude-main/recommendations")
        slugs = {item["slug"] for item in response.json()["data"]}
        assert "self-exclude-main" not in slugs

    def test_different_category_products_not_recommended(self, api_client):
        category_a = _real_category()
        category_b = _real_category()
        repo = DjangoProductRepository()
        repo.save(_published_product("diffcat-main", category_id=category_a))
        repo.save(_published_product("diffcat-other", category_id=category_b))

        response = api_client.get("/api/v1/products/diffcat-main/recommendations")
        slugs = {item["slug"] for item in response.json()["data"]}
        assert "diffcat-other" not in slugs

    def test_no_duplicate_products_in_result(self, api_client):
        category_id = _real_category()
        repo = DjangoProductRepository()
        repo.save(_published_product("dup-main", category_id=category_id))
        repo.save(_published_product("dup-sibling", category_id=category_id))

        response = api_client.get("/api/v1/products/dup-main/recommendations")
        data = response.json()["data"]
        ids = [item["id"] for item in data]
        assert len(ids) == len(set(ids))

    def test_deterministic_ordering_across_repeated_requests(self, api_client):
        category_id = _real_category()
        repo = DjangoProductRepository()
        repo.save(_published_product("det-main", category_id=category_id))
        for i in range(5):
            repo.save(_published_product(f"det-sibling-{i}", category_id=category_id))

        first = api_client.get("/api/v1/products/det-main/recommendations").json()["data"]
        second = api_client.get("/api/v1/products/det-main/recommendations").json()["data"]
        assert [i["id"] for i in first] == [i["id"] for i in second]

    def test_result_bounded_by_default_limit(self, api_client):
        category_id = _real_category()
        repo = DjangoProductRepository()
        repo.save(_published_product("bound-main", category_id=category_id))
        for i in range(15):
            repo.save(_published_product(f"bound-sibling-{i}", category_id=category_id))

        response = api_client.get("/api/v1/products/bound-main/recommendations")
        assert len(response.json()["data"]) <= 8  # RecommendationSelector.DEFAULT_LIMIT


class TestManualCuratedPrecedence:
    def test_manual_curated_takes_precedence_over_category_fallback(self, api_client):
        from apps.products.infrastructure import models as orm
        category_id = _real_category()
        repo = DjangoProductRepository()
        main = _published_product("curated-main", category_id=category_id)
        repo.save(main)
        repo.save(_published_product("curated-category-sibling", category_id=category_id))
        curated_target = _published_product("curated-explicit-pick", category_id=_real_category())  # deliberately a DIFFERENT category
        repo.save(curated_target)

        orm.ProductRecommendation.objects.create(product_id=main.id, related_product_id=curated_target.id, relation_type="manual_curated", sort_order=0)

        response = api_client.get("/api/v1/products/curated-main/recommendations")
        slugs = [item["slug"] for item in response.json()["data"]]
        assert slugs == ["curated-explicit-pick"]  # only the curated pick, not the category-fallback sibling

    def test_manual_curated_respects_sort_order(self, api_client):
        from apps.products.infrastructure import models as orm
        repo = DjangoProductRepository()
        main = _published_product("sort-main")
        repo.save(main)
        second = _published_product("sort-second")
        repo.save(second)
        first = _published_product("sort-first")
        repo.save(first)

        orm.ProductRecommendation.objects.create(product_id=main.id, related_product_id=second.id, relation_type="manual_curated", sort_order=1)
        orm.ProductRecommendation.objects.create(product_id=main.id, related_product_id=first.id, relation_type="manual_curated", sort_order=0)

        response = api_client.get("/api/v1/products/sort-main/recommendations")
        slugs = [item["slug"] for item in response.json()["data"]]
        assert slugs == ["sort-first", "sort-second"]


class TestActiveProductFilter:
    def test_unpublished_curated_target_excluded(self, api_client):
        from apps.products.infrastructure import models as orm
        repo = DjangoProductRepository()
        main = _published_product("unpub-main")
        repo.save(main)
        # A curated target that is NOT published (e.g. draft/unpublished).
        draft_target = Product(id=uuid.uuid4(), slug=Slug("unpub-draft-target"), name="Draft Target")
        draft_target.add_variant(ProductVariant(id=uuid.uuid4(), sku=SKU("SKU-DRAFT01")))
        repo.save(draft_target)  # never published -- stays DRAFT

        orm.ProductRecommendation.objects.create(product_id=main.id, related_product_id=draft_target.id, relation_type="manual_curated", sort_order=0)

        response = api_client.get("/api/v1/products/unpub-main/recommendations")
        assert response.json()["data"] == []  # the unpublished curated target must not be exposed


class TestNoNPlusOne:
    def test_query_count_stable_across_result_size(self, api_client):
        """Uses two independent products (each queried once, both genuine cache misses via GetProduct's own caching) to isolate row count as the only variable -- comparing repeated requests to the SAME product would confound cache-hit state with row count."""
        category_id = _real_category()
        repo = DjangoProductRepository()

        repo.save(_published_product("nplus1-small-main", category_id=category_id))
        for i in range(3):
            repo.save(_published_product(f"nplus1-small-sib-{i}", category_id=category_id))
        with CaptureQueriesContext(connection) as ctx:
            api_client.get("/api/v1/products/nplus1-small-main/recommendations")
        small_count = len(ctx.captured_queries)

        repo.save(_published_product("nplus1-large-main", category_id=category_id))
        for i in range(13):
            repo.save(_published_product(f"nplus1-large-sib-{i}", category_id=category_id))
        with CaptureQueriesContext(connection) as ctx:
            api_client.get("/api/v1/products/nplus1-large-main/recommendations")
        large_count = len(ctx.captured_queries)

        assert large_count == small_count
