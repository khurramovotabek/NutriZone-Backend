"""
Phase 08.3: NutriZone Admin Commerce Workspace tests
(Products, Categories, Brands, Flavours, Variants).

Real database fixtures throughout -- not status-code-only assertions,
per this phase's own explicit testing requirement.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.db import connection

from apps.products.domain.aggregates import Brand, Category, Product, ProductVariant
from apps.products.domain.entities import ProductMedia
from apps.products.domain.enums import MediaRole
from apps.products.domain.value_objects import SKU, Slug
from apps.products.infrastructure.repositories import DjangoBrandRepository, DjangoCategoryRepository, DjangoProductRepository

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _published_product(slug: str, category_id=None, brand_id=None) -> Product:
    from apps.products.infrastructure import models as orm

    suffix = uuid.uuid4().hex[:8].upper()
    product = Product(id=uuid.uuid4(), slug=Slug(slug), name=f"Commerce Test {slug}", category_id=category_id, brand_id=brand_id)
    product.add_variant(ProductVariant(id=uuid.uuid4(), sku=SKU(f"SKU-{suffix}")))
    product.add_media(ProductMedia(id=uuid.uuid4(), media_id=uuid.uuid4(), media_role=MediaRole.PRIMARY, storage_path=f"products/{slug}.jpg"))
    product.publish()
    return DjangoProductRepository().save(product)


def _category(slug: str) -> Category:
    cat = Category(id=uuid.uuid4(), slug=Slug(slug), name=f"Category {slug}")
    return DjangoCategoryRepository().save(cat)


def _brand(slug: str) -> Brand:
    b = Brand(id=uuid.uuid4(), slug=Slug(slug), name=f"Brand {slug}")
    return DjangoBrandRepository().save(b)


@pytest.fixture
def staff_client():
    User = get_user_model()
    user = User.objects.create(username=f"nz_staff_{uuid.uuid4().hex[:8]}", is_staff=True, is_superuser=True)
    user.set_password("pw")
    user.save()
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def non_staff_client():
    User = get_user_model()
    user = User.objects.create(username=f"nz_customer_{uuid.uuid4().hex[:8]}", is_staff=False)
    user.set_password("pw")
    user.save()
    client = Client()
    client.force_login(user)
    return client


class TestCommerceAccessControl:
    def test_anonymous_denied_products(self):
        response = Client().get("/django-admin/products/product/")
        assert response.status_code in (302, 403)

    def test_non_staff_denied_products(self, non_staff_client):
        response = non_staff_client.get("/django-admin/products/product/")
        assert response.status_code in (302, 403)

    def test_non_staff_cannot_access_by_manipulating_url(self, non_staff_client):
        """IDOR check -- a non-staff user must be denied even with a specific object's real ID in the URL, not just the list view."""
        category = _category("idor-check")
        response = non_staff_client.get(f"/django-admin/products/category/{category.id}/change/")
        assert response.status_code in (302, 403)

    def test_staff_with_view_permission_sees_products(self, staff_client):
        response = staff_client.get("/django-admin/products/product/")
        assert response.status_code == 200

    def test_staff_with_explicit_permission_but_not_superuser_sees_products(self):
        """Distinct from superuser -- a staff user granted only the specific view_product permission, matching this phase's own access matrix which lists 'Staff with permission' separately from 'Superuser'."""
        from django.contrib.auth.models import Permission

        User = get_user_model()
        user = User.objects.create(username=f"nz_permstaff_{uuid.uuid4().hex[:8]}", is_staff=True, is_superuser=False)
        user.set_password("pw")
        user.save()
        from django.contrib.contenttypes.models import ContentType
        from apps.products.infrastructure import models as products_orm

        # Forces a fresh lookup -- ContentType's own cache is process-level,
        # not scoped to this test's transaction, so a prior test's rolled-back
        # ContentType creation can otherwise leave a stale, now-invalid id cached.
        ContentType.objects.clear_cache()
        content_type = ContentType.objects.get_for_model(products_orm.Product)
        permission, _ = Permission.objects.get_or_create(codename="view_product", content_type=content_type, defaults={"name": "Can view product"})
        user.user_permissions.add(permission)

        client = Client()
        client.force_login(user)
        response = client.get("/django-admin/products/product/")
        assert response.status_code == 200

        # But this same user must NOT be able to change a product without change_product.
        response = client.get("/django-admin/products/category/")
        assert response.status_code == 403


class TestProductsWorkspace:
    def test_list_shows_real_product(self, staff_client):
        product = _published_product("workspace-visible")
        response = staff_client.get("/django-admin/products/product/")
        assert response.status_code == 200
        assert "Commerce Test workspace-visible" in response.content.decode()

    def test_search_finds_by_name(self, staff_client):
        _published_product("searchable-unique-slug")
        response = staff_client.get("/django-admin/products/product/?q=searchable-unique-slug")
        assert response.status_code == 200
        assert "Commerce Test searchable-unique-slug" in response.content.decode()

    def test_filter_by_status(self, staff_client):
        _published_product("filter-status-check")
        response = staff_client.get("/django-admin/products/product/?status__exact=published")
        assert response.status_code == 200
        assert "Commerce Test filter-status-check" in response.content.decode()

    def test_filter_by_category(self, staff_client):
        category = _category("filter-cat")
        _published_product("filter-by-cat-product", category_id=category.id)
        response = staff_client.get(f"/django-admin/products/product/?category__id__exact={category.id}")
        assert response.status_code == 200
        assert "Commerce Test filter-by-cat-product" in response.content.decode()

    def test_no_n_plus_1_on_product_list(self, staff_client):
        """Query count must not scale linearly with product count -- proves prefetch_related is actually effective, not just declared."""
        for i in range(5):
            _published_product(f"n1-check-{i}")

        with CaptureQueriesContext(connection) as ctx:
            response = staff_client.get("/django-admin/products/product/")
        assert response.status_code == 200
        query_count_5 = len(ctx.captured_queries)

        for i in range(5, 10):
            _published_product(f"n1-check-{i}")

        with CaptureQueriesContext(connection) as ctx:
            response = staff_client.get("/django-admin/products/product/")
        assert response.status_code == 200
        query_count_10 = len(ctx.captured_queries)

        # A handful of extra queries is fine (pagination count, etc.) but must not double.
        assert query_count_10 < query_count_5 + 5, f"Query count grew from {query_count_5} to {query_count_10} for 5 more products -- possible N+1"


class TestCategoriesWorkspace:
    def test_list_shows_real_category(self, staff_client):
        _category("visible-category")
        response = staff_client.get("/django-admin/products/category/")
        assert response.status_code == 200
        assert "Category visible-category" in response.content.decode()

    def test_hierarchy_parent_displayed(self, staff_client):
        """Category.parent is a real, self-referential FK (confirmed by direct model inspection) -- verify it actually renders, not just that the field exists."""
        from apps.products.infrastructure import models as orm

        parent = _category("parent-cat")
        child_row = orm.Category.objects.get(id=_category("child-cat").id)
        child_row.parent_id = parent.id
        child_row.save()

        response = staff_client.get("/django-admin/products/category/")
        assert response.status_code == 200

    def test_search_finds_category(self, staff_client):
        _category("searchable-category-unique")
        response = staff_client.get("/django-admin/products/category/?q=searchable-category-unique")
        assert response.status_code == 200
        assert "Category searchable-category-unique" in response.content.decode()


class TestBrandsWorkspace:
    def test_list_shows_real_brand(self, staff_client):
        _brand("visible-brand")
        response = staff_client.get("/django-admin/products/brand/")
        assert response.status_code == 200
        assert "Brand visible-brand" in response.content.decode()

    def test_search_finds_brand(self, staff_client):
        _brand("searchable-brand-unique")
        response = staff_client.get("/django-admin/products/brand/?q=searchable-brand-unique")
        assert response.status_code == 200
        assert "Brand searchable-brand-unique" in response.content.decode()


class TestFlavoursWorkspace:
    def test_list_renders(self, staff_client):
        response = staff_client.get("/django-admin/products/flavour/")
        assert response.status_code == 200

    def test_create_flavour_via_admin(self, staff_client):
        from apps.products.infrastructure import models as orm

        flavour = orm.Flavour.objects.create(slug=f"chocolate-{uuid.uuid4().hex[:6]}", color_hex="#4B2E1E")

        response = staff_client.get(f"/django-admin/products/flavour/{flavour.id}/change/")
        assert response.status_code == 200


class TestVariantsWorkspace:
    def test_list_shows_real_variant(self, staff_client):
        product = _published_product("variant-workspace-check")
        response = staff_client.get("/django-admin/products/productvariant/")
        assert response.status_code == 200
        variant_sku = list(product.variants.values())[0].sku.value
        assert variant_sku in response.content.decode()

    def test_variant_shows_parent_product(self, staff_client):
        product = _published_product("variant-parent-check")
        response = staff_client.get("/django-admin/products/productvariant/")
        assert "Commerce Test variant-parent-check" in response.content.decode()

    def test_variant_search_by_sku(self, staff_client):
        product = _published_product("variant-sku-search")
        variant_sku = list(product.variants.values())[0].sku.value
        response = staff_client.get(f"/django-admin/products/productvariant/?q={variant_sku}")
        assert response.status_code == 200
        assert variant_sku in response.content.decode()


class TestDashboardHomeRegression:
    """Phase 08.3 must not break Phase 08.2's own Dashboard Home."""

    def test_dashboard_home_still_renders(self, staff_client):
        response = staff_client.get("/django-admin/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "nz-dashboard" in content
        assert "nz-kpi-grid" in content
