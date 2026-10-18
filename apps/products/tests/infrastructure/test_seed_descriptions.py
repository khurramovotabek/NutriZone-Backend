"""Long category / brand descriptions: full coverage of the tree and brand list, safe overwrite rules, the detail API."""
import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.products.infrastructure import models as orm
from apps.products.infrastructure.brand_catalog import BRANDS, seed_brands
from apps.products.infrastructure.brand_texts import BRAND_TEXTS
from apps.products.infrastructure.category_catalog import TREE, count_nodes, seed_categories
from apps.products.infrastructure.category_texts import CATEGORY_TEXTS

pytestmark = pytest.mark.django_db


def _en(category):
    return category.translations.get(locale_code="en").description


def test_every_category_and_brand_has_three_languages():
    names = [n[2] for top in TREE for n in [top, *top[4], *[leaf for s in top[4] for leaf in s[4]]]]
    assert len(names) == count_nodes() and set(names) == set(CATEGORY_TEXTS)
    assert {b[0] for b in BRANDS} == set(BRAND_TEXTS)
    for texts in [*CATEGORY_TEXTS.values(), *BRAND_TEXTS.values()]:
        assert len(texts) == 3 and all(len(t) > 200 for t in texts)


def test_seed_texts_are_replaced_but_dashboard_edits_kept():
    seed_categories()
    seed_brands()
    creatine = orm.Category.objects.get(translations__locale_code="en", translations__name="Creatine")
    edited = creatine.translations.get(locale_code="uz")
    edited.description = "Do'kon egasining o'z matni"
    edited.save()
    call_command("seed_descriptions")
    assert _en(creatine) == CATEGORY_TEXTS["Creatine"][2]
    assert creatine.translations.get(locale_code="uz").description == "Do'kon egasining o'z matni"
    brand = orm.Brand.objects.get(translations__locale_code="en", translations__name="Optimum Nutrition")
    assert brand.translations.get(locale_code="ru").description == BRAND_TEXTS["Optimum Nutrition"][1]
    call_command("seed_descriptions", force=True)
    assert creatine.translations.get(locale_code="uz").description == CATEGORY_TEXTS["Creatine"][0]


def test_dry_run_changes_nothing():
    seed_categories()
    call_command("seed_descriptions", dry_run=True)
    creatine = orm.Category.objects.get(translations__locale_code="en", translations__name="Creatine")
    assert _en(creatine) != CATEGORY_TEXTS["Creatine"][2]


def test_category_detail_endpoint():
    seed_categories()
    call_command("seed_descriptions")
    creatine = orm.Category.objects.get(translations__locale_code="en", translations__name="Creatine")
    body = APIClient().get(f"/api/v1/categories/{creatine.id}?locale=ru").json()["data"]
    assert body["name"] == "Креатин" and body["description"] == CATEGORY_TEXTS["Creatine"][1]
    assert APIClient().get("/api/v1/categories/00000000-0000-0000-0000-000000000000").status_code == 404
