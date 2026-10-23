"""NutriZone's category tree seed (apps/products/infrastructure/category_catalog.py)."""
from __future__ import annotations

import pytest

from apps.products.infrastructure import models as orm
from apps.products.infrastructure.category_catalog import count_nodes, seed_categories

pytestmark = pytest.mark.django_db


def _by_en(name, parent=None):
    return orm.Category.objects.get(parent=parent, translations__locale_code="en", translations__name=name)


def test_builds_the_three_level_tree_in_three_languages():
    stats = seed_categories()
    assert stats["created"] == count_nodes() == orm.Category.objects.count()
    sport = _by_en("Sports Nutrition")
    amino = _by_en("Amino Acids", sport)
    assert {t.name for t in _by_en("BCAA", amino).translations.all()} == {"BCAA"}
    hydration = _by_en("Hydration", sport)
    assert set(orm.Category.objects.filter(parent=hydration).values_list("translations__name", flat=True)) >= {"Izotonik", "Electrolytes"}
    recovery = _by_en("Recovery", sport)
    assert orm.Category.objects.filter(parent=recovery).count() == 4
    assert not orm.CategoryTranslation.objects.filter(name__icontains="intra").exists()
    for c in orm.Category.objects.all():
        assert {t.locale_code for t in c.translations.all()} == {"uz", "ru", "en"}
    assert _by_en("Proteins", sport).translations.get(locale_code="ru").name == "Протеины"


def test_rerun_adds_nothing_and_keeps_dashboard_edits():
    seed_categories()
    row = _by_en("Proteins", _by_en("Sports Nutrition")).translations.get(locale_code="uz")
    row.name = "Proteinlar (tahrirlangan)"
    row.save()
    stats = seed_categories()
    assert stats["created"] == 0 and stats["existing"] == count_nodes()
    row.refresh_from_db()
    assert row.name == "Proteinlar (tahrirlangan)"


def test_slugs_are_unique_per_language_even_for_repeated_names():
    seed_categories()
    for locale in ("uz", "ru", "en"):
        slugs = list(orm.CategoryTranslation.objects.filter(locale_code=locale).values_list("slug", flat=True))
        assert len(slugs) == len(set(slugs)) and all(slugs)


def test_a_top_category_covers_its_sections_and_product_types():
    from apps.products.infrastructure.catalog_browse import _category_scope

    seed_categories()
    sport = _by_en("Sports Nutrition")
    proteins = _by_en("Proteins", sport)
    whey = _by_en("Whey Protein", proteins)
    scope = _category_scope(sport.id)
    assert {sport.id, proteins.id, whey.id} <= scope
    assert _by_en("Vitamins").id not in scope
    assert _category_scope(proteins.id) == {proteins.id, *orm.Category.objects.filter(parent=proteins).values_list("id", flat=True)}


def test_product_form_lists_categories_with_their_full_path():
    from django.contrib.auth import get_user_model
    from django.test import Client

    seed_categories()
    user = get_user_model().objects.create(username="cat_path_admin", is_staff=True, is_superuser=True)
    client = Client()
    client.force_login(user)
    html = client.get("/django-admin/products/product/add/", HTTP_ACCEPT_LANGUAGE="uz").content.decode()
    assert "Sport ozuqalari › Proteinlar › Whey protein" in html
    assert "Vitaminlar › Alohida vitaminlar › Vitamin D3" in html
