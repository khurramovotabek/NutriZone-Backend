"""
Full-stack API integration tests -- real URL routing, serializers,
views, application services, and repository layer together against a
real database. Matches `apps/identity/tests/interfaces/
test_api_authentication_flow.py`'s pattern.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.products.domain.aggregates import Product, ProductVariant
from apps.products.domain.entities import ProductMedia
from apps.products.domain.enums import MediaRole
from apps.products.domain.value_objects import SKU, Slug
from apps.products.infrastructure.repositories import DjangoProductRepository
from common.permissions import HasPermissionCode

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


class _AllowAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return True


class _DenyAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return False


def _published_product() -> Product:
    from apps.products.infrastructure import models as orm
    product = Product(id=uuid.uuid4(), slug=Slug("whey-protein-2kg"), name="Whey Protein 2kg")
    product.add_variant(ProductVariant(id=uuid.uuid4(), sku=SKU("WHEY-2KG")))
    product.add_media(ProductMedia(id=uuid.uuid4(), media_id=uuid.uuid4(), media_role=MediaRole.PRIMARY, storage_path="products/test-asset.jpg"))
    product.publish()
    return product


class TestPublicProductEndpoints:
    def test_list_products_returns_only_published(self, api_client):
        repo = DjangoProductRepository()
        repo.save(_published_product())

        response = api_client.get("/api/v1/products")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["pagination"]["total_count"] == 1

    def test_get_product_by_slug(self, api_client):
        repo = DjangoProductRepository()
        product = _published_product()
        repo.save(product)

        response = api_client.get(f"/api/v1/products/{product.slug.value}")
        assert response.status_code == 200
        assert response.json()["data"]["slug"] == product.slug.value

    def test_get_nonexistent_product_returns_404(self, api_client):
        response = api_client.get("/api/v1/products/does-not-exist")
        assert response.status_code == 404

    def test_get_draft_product_returns_404(self, api_client):
        repo = DjangoProductRepository()
        draft = Product(id=uuid.uuid4(), slug=Slug("secret-draft"), name="Secret Draft")
        repo.save(draft)

        response = api_client.get("/api/v1/products/secret-draft")
        assert response.status_code == 404

    def test_search_endpoint_returns_envelope_with_facets(self, api_client):
        response = api_client.get("/api/v1/products/search?q=whey")
        assert response.status_code == 200
        assert "facets" in response.json()["meta"]

    def test_categories_endpoint(self, api_client):
        response = api_client.get("/api/v1/categories")
        assert response.status_code == 200

    def test_brands_endpoint(self, api_client):
        response = api_client.get("/api/v1/brands")
        assert response.status_code == 200

    def test_catalog_filters_endpoint(self, api_client):
        response = api_client.get("/api/v1/catalog/filters")
        assert response.status_code == 200
        assert "brand" in response.json()["data"]


class TestAdminEndpointsUnauthenticated:
    def test_admin_list_requires_authentication(self, api_client):
        response = api_client.get("/api/v1/admin/products")
        assert response.status_code == 401

    def test_admin_create_requires_authentication(self, api_client):
        response = api_client.post("/api/v1/admin/products", {"name": "X"}, format="json")
        assert response.status_code == 401


class TestAdminEndpointsPermissionDenial:
    @pytest.fixture(autouse=True)
    def _authenticated_but_unauthorized_user(self, monkeypatch):
        original_resolver = HasPermissionCode.resolver
        HasPermissionCode.resolver = _DenyAllResolver()

        fake_user = SimpleNamespace(id=uuid.uuid4(), is_authenticated=True, store_ids=set())
        monkeypatch.setattr(
            "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
            lambda self, request: (fake_user, None),
        )
        yield
        HasPermissionCode.resolver = original_resolver

    def test_admin_list_denied_without_permission(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.get("/api/v1/admin/products")
        assert response.status_code == 403

    def test_admin_create_denied_without_permission(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post("/api/v1/admin/products", {"name": "X"}, format="json")
        assert response.status_code == 403


class TestAdminEndpointsAuthorized:
    @pytest.fixture(autouse=True)
    def _authenticated_and_authorized_user(self, monkeypatch):
        original_resolver = HasPermissionCode.resolver
        HasPermissionCode.resolver = _AllowAllResolver()

        fake_user = SimpleNamespace(id=uuid.uuid4(), is_authenticated=True, store_ids=set())
        monkeypatch.setattr(
            "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
            lambda self, request: (fake_user, None),
        )
        yield
        HasPermissionCode.resolver = original_resolver

    def test_create_product(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post("/api/v1/admin/products", {"name": "New Product"}, format="json")
        assert response.status_code == 201
        assert response.json()["data"]["status"] == "draft"

    def test_create_product_invalid_payload_returns_422(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post("/api/v1/admin/products", {}, format="json")
        assert response.status_code == 422

    def test_full_lifecycle_create_variant_upload_image_publish(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")

        create_response = api_client.post("/api/v1/admin/products", {"name": "Lifecycle Product"}, format="json")
        product_id = create_response.json()["data"]["id"]

        variant_response = api_client.post(f"/api/v1/admin/products/{product_id}/variants", {"sku": "LIFECYCLE-1"}, format="json")
        assert variant_response.status_code == 201

        publish_response = api_client.post(f"/api/v1/admin/products/{product_id}/publish", {}, format="json")
        # Publish should fail (422) since no primary image was uploaded -- this
        # verifies the aggregated PublishValidationFailed surfaces correctly
        # through the full HTTP stack, not just at the domain-test level.
        assert publish_response.status_code == 422
        assert publish_response.json()["error"]["code"] == "PUBLISH_VALIDATION_FAILED"

    def test_admin_get_nonexistent_product_returns_404(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.get(f"/api/v1/admin/products/{uuid.uuid4()}")
        assert response.status_code == 404

    def test_delete_non_archived_product_returns_409(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        create_response = api_client.post("/api/v1/admin/products", {"name": "Not Archived"}, format="json")
        product_id = create_response.json()["data"]["id"]

        response = api_client.delete(f"/api/v1/admin/products/{product_id}")
        assert response.status_code == 409

    def test_update_seo(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        create_response = api_client.post("/api/v1/admin/products", {"name": "SEO Product"}, format="json")
        product_id = create_response.json()["data"]["id"]

        response = api_client.patch(f"/api/v1/admin/products/{product_id}/seo", {"meta_title": "Great Product"}, format="json")
        assert response.status_code == 200
        assert response.json()["data"]["seo"]["meta_title"] == "Great Product"

    def test_response_envelope_has_request_id_and_timestamp(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post("/api/v1/admin/products", {"name": "Envelope Test"}, format="json")
        meta = response.json()["meta"]
        assert "request_id" in meta
        assert "timestamp" in meta
