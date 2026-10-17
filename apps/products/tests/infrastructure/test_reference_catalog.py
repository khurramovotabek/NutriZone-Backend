"""Package / flavour / tag reference lists (reference_catalog.py)."""
from __future__ import annotations

import pytest

from apps.products.infrastructure import models as orm
from apps.products.infrastructure.reference_catalog import FLAVOURS, PACKAGES, TAGS, seed_reference

pytestmark = pytest.mark.django_db


def test_seeds_three_languages_and_is_idempotent():
    seed_reference()
    assert orm.Package.objects.count() == len(PACKAGES)
    assert orm.Flavour.objects.count() == len(FLAVOURS)
    assert orm.Tag.objects.count() == len(TAGS)
    for model in (orm.Package, orm.Flavour, orm.Tag):
        for obj in model.objects.prefetch_related("translations"):
            assert {t.locale_code for t in obj.translations.all()} == {"uz", "ru", "en"}
    choc = orm.Flavour.objects.get(slug="chocolate")
    assert choc.color_hex.startswith("#") and choc.translations.get(locale_code="uz").name == "Shokolad"
    t = choc.translations.get(locale_code="uz")
    t.name = "Shokoladli"
    t.save()
    stats = seed_reference()
    assert stats["flavours"] == [0, len(FLAVOURS)]
    assert choc.translations.get(locale_code="uz").name == "Shokoladli"


def test_flavour_names_are_found_in_product_names():
    from apps.products.infrastructure.product_grouping import _find_flavour, _flavour_index, base_name

    seed_reference()
    index = _flavour_index()
    assert _find_flavour("Olimp Complex Whey 1.8 kg Coconut Cream", index)[1] == "coconut cream"
    assert _find_flavour("BSN Syntha-6 Chocolate Peanut Butter 2.27kg", index)[1] == "chocolate peanut butter"
    assert base_name("Optimum Nutrition Gold Standard 100% Whey 2.27 kg Double Rich Chocolate", index) == "Optimum Nutrition Gold Standard 100% Whey"
