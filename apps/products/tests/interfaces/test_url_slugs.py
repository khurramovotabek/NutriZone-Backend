"""
Readable, per-language URLs: categories, brands and product cards carry `slug` (the request's language) and
`slugs` (every language), so the storefront can link /categories/<slug> and emit hreflang alternates that
point at each language's own address.
"""
from __future__ import annotations

import uuid

import pytest
from django.test import Client

from apps.products.infrastructure import models as p_models

pytestmark = pytest.mark.django_db


def _category(slugs: dict[str, str]) -> p_models.Category:
    category = p_models.Category.objects.create(id=uuid.uuid4(), is_active=True, sort_order=1)
    for locale, slug in slugs.items():
        p_models.CategoryTranslation.objects.create(id=uuid.uuid4(), category=category, locale_code=locale, name=f"Cat {locale} {slug}", slug=slug)
    return category


class TestCategorySlugs:
    def test_category_list_has_the_slug_of_the_requested_language_and_all_slugs(self):
        tag = uuid.uuid4().hex[:6]
        category = _category({"uz": f"sport-ozuqalari-{tag}", "ru": f"sportivnoe-pitanie-{tag}", "en": f"sports-nutrition-{tag}"})

        data = Client().get("/api/v1/categories?locale=ru").json()["data"]
        row = next(c for c in data if c["id"] == str(category.id))

        assert row["slug"] == f"sportivnoe-pitanie-{tag}"
        assert row["slugs"] == {"uz": f"sport-ozuqalari-{tag}", "ru": f"sportivnoe-pitanie-{tag}", "en": f"sports-nutrition-{tag}"}

    def test_a_language_without_its_own_slug_falls_back_to_uzbek(self):
        tag = uuid.uuid4().hex[:6]
        category = _category({"uz": f"faqat-uz-{tag}"})

        data = Client().get("/api/v1/categories?locale=en").json()["data"]
        row = next(c for c in data if c["id"] == str(category.id))

        assert row["slug"] == f"faqat-uz-{tag}"
        assert row["slugs"] == {"uz": f"faqat-uz-{tag}"}


class TestBrandSlugs:
    def test_brand_list_slug_follows_the_requested_language(self):
        tag = uuid.uuid4().hex[:6]
        brand = p_models.Brand.objects.create(id=uuid.uuid4(), is_active=True, is_manufacturer=False)
        p_models.BrandTranslation.objects.create(id=uuid.uuid4(), brand=brand, locale_code="uz", name="Slug Brand", slug=f"slug-brand-{tag}")
        p_models.BrandTranslation.objects.create(id=uuid.uuid4(), brand=brand, locale_code="ru", name="Slug Brand", slug=f"slug-brand-ru-{tag}")

        data = Client().get("/api/v1/brands?locale=ru").json()["data"]
        row = next(b for b in data if b["id"] == str(brand.id))

        assert row["slug"] == f"slug-brand-ru-{tag}"
        assert row["slugs"] == {"uz": f"slug-brand-{tag}", "ru": f"slug-brand-ru-{tag}"}
