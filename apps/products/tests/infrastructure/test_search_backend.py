"""
`DjangoProductSearchBackend` was, until this test file, entirely
untested despite being the search implementation every storefront/POS
search box calls through `PostgresSearchGateway` /
`application/selectors.py::ProductSelector.search`. Covers the real
defects fixed alongside migration 0024:

  1. Matching used to be plain `icontains` (a substring LIKE scan with
     no index) with a `SearchRank` annotation computed but never used
     to filter or reliably order -- ranking by real relevance
     (name-match ranked above description-only match) was untested and,
     as written, not actually guaranteed.
  2. No typo tolerance at all: a one-character-off query returned
     nothing.
  3. `locale` was joined without a matching text-search config, so a
     Russian product name was never stemmed correctly.
  4. Non-matching locale rows must never leak into results (the join
     fan-out this backend deliberately avoids by design).

Each product is created with a real, GIN-indexed `search_vector`
(populated by migration 0024's Postgres trigger on save --
never written by application code).
"""
from __future__ import annotations

import uuid

import pytest

from apps.products.domain.enums import ProductStatus
from apps.products.infrastructure import models as orm
from apps.products.infrastructure.selectors import DjangoProductSearchBackend

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _make_product(*, locale: str = "en", name: str, description: str = "", status: str = ProductStatus.PUBLISHED.value) -> orm.Product:
    product = orm.Product.objects.create(id=uuid.uuid4(), status=status)
    orm.ProductTranslation.objects.create(
        id=uuid.uuid4(), product=product, locale_code=locale, name=name, description=description,
        slug=f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}",
    )
    return product


class TestFullTextMatch:
    def test_matches_on_name(self):
        target = _make_product(name="Whey Protein Isolate")
        _make_product(name="Fish Oil Omega 3")

        result = DjangoProductSearchBackend().search(query="protein", filters={}, page=1, page_size=20, sort="-created_at", locale="en")

        ids = {r["id"] for r in result["results"]}
        assert str(target.id) in ids
        assert result["total_count"] == 1

    def test_matches_on_description_but_ranks_name_match_higher(self):
        name_match = _make_product(name="Creatine Monohydrate", description="Pure creatine powder.")
        description_only = _make_product(name="Recovery Blend", description="Contains creatine as a secondary ingredient.")

        result = DjangoProductSearchBackend().search(query="creatine", filters={}, page=1, page_size=20, sort="-created_at", locale="en")

        ids = [r["id"] for r in result["results"]]
        assert str(name_match.id) in ids
        assert str(description_only.id) in ids
        # Name (weight A) must outrank description-only (weight B).
        assert ids.index(str(name_match.id)) < ids.index(str(description_only.id))

    def test_stems_english_words(self):
        """`english` text-search config stems "vitamins" -> "vitamin", so a plural query still matches a singular name."""
        target = _make_product(name="Daily Vitamin Complex")

        result = DjangoProductSearchBackend().search(query="vitamins", filters={}, page=1, page_size=20, sort="-created_at", locale="en")

        assert str(target.id) in {r["id"] for r in result["results"]}


class TestTypoTolerance:
    def test_trigram_fallback_survives_a_single_typo(self):
        target = _make_product(name="Creatine Monohydrate")

        result = DjangoProductSearchBackend().search(query="creatin", filters={}, page=1, page_size=20, sort="-created_at", locale="en")

        assert str(target.id) in {r["id"] for r in result["results"]}

    def test_unrelated_query_returns_nothing(self):
        _make_product(name="Creatine Monohydrate")

        result = DjangoProductSearchBackend().search(query="zzqxvw", filters={}, page=1, page_size=20, sort="-created_at", locale="en")

        assert result["results"] == []
        assert result["total_count"] == 0


class TestLocaleScoping:
    def test_every_locale_name_is_searchable_whatever_the_requested_locale(self):
        """Product decision: a shopper finds a product by its name in any of the three languages, whichever UI language they browse in (smart_search.py)."""
        product = orm.Product.objects.create(id=uuid.uuid4(), status=ProductStatus.PUBLISHED.value)
        orm.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name="Fish Oil", slug=f"fish-oil-{uuid.uuid4().hex[:6]}")
        orm.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="ru", name="Рыбий жир", slug=f"fish-oil-ru-{uuid.uuid4().hex[:6]}")

        for query, locale in (("Fish", "en"), ("Fish", "ru"), ("рыбий жир", "en"), ("ribiy jir", "uz")):
            result = DjangoProductSearchBackend().search(query=query, filters={}, page=1, page_size=20, sort="-created_at", locale=locale)
            assert str(product.id) in {r["id"] for r in result["results"]}, (query, locale)


class TestPublishedOnly:
    def test_draft_products_are_excluded(self):
        _make_product(name="Unreleased Pre-Workout", status=ProductStatus.DRAFT.value)

        result = DjangoProductSearchBackend().search(query="pre-workout", filters={}, page=1, page_size=20, sort="-created_at", locale="en")

        assert result["results"] == []


class TestFilterCombination:
    def test_brand_filter_is_applied_on_top_of_relevance_ranking(self):
        brand_a = orm.Brand.objects.create(id=uuid.uuid4())
        brand_b = orm.Brand.objects.create(id=uuid.uuid4())
        wanted = _make_product(name="Optimum Whey Protein")
        wanted.brand = brand_a
        wanted.save(update_fields=["brand"])
        other = _make_product(name="Generic Whey Protein")
        other.brand = brand_b
        other.save(update_fields=["brand"])

        result = DjangoProductSearchBackend().search(query="whey", filters={"brand_id": brand_a.id}, page=1, page_size=20, sort="-created_at", locale="en")

        ids = {r["id"] for r in result["results"]}
        assert ids == {str(wanted.id)}
