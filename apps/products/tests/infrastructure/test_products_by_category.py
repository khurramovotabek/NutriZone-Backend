"""
Real, live-verified regression test for Phase E2: products_by_category
real distribution metric, and its rendering on the Reports admin page.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.products.infrastructure import models as p_models
from apps.products.infrastructure.selectors import StatisticsSelector

pytestmark = pytest.mark.django_db


class TestProductsByCategorySelector:
    def test_returns_real_category_name_and_count(self):
        category = p_models.Category.objects.create(id=uuid.uuid4())
        p_models.CategoryTranslation.objects.create(id=uuid.uuid4(), category=category, locale_code="en", name="Protein", slug=f"protein-{uuid.uuid4().hex[:6]}")
        for i in range(3):
            product = p_models.Product.objects.create(id=uuid.uuid4(), status="published", category=category)
            p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name=f"Product {i}", slug=f"product-{uuid.uuid4().hex[:6]}")

        result = StatisticsSelector().products_by_category(limit=8)
        matching = next((r for r in result if r["name"] == "Protein"), None)
        assert matching is not None
        assert matching["count"] == 3


class TestReportsPageCategoryChart:
    def test_reports_page_renders_real_category_chart(self):
        category = p_models.Category.objects.create(id=uuid.uuid4())
        p_models.CategoryTranslation.objects.create(id=uuid.uuid4(), category=category, locale_code="en", name="Vitamins", slug=f"vitamins-{uuid.uuid4().hex[:6]}")
        product = p_models.Product.objects.create(id=uuid.uuid4(), status="published", category=category)
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name="Vitamin C", slug=f"vc-{uuid.uuid4().hex[:6]}")

        admin_user = User.objects.create_superuser(username=f"admin_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
        client = Client()
        client.force_login(admin_user)

        response = client.get("/django-admin/reports/")
        assert response.status_code == 200
        body = response.content.decode()
        assert "nz-category-chart" in body
        assert "Vitamins" in body
