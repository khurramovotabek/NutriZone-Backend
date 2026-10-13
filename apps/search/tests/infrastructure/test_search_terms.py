"""Search analytics: submitted catalog searches are counted per normalized term; popular terms and the dashboard page read them."""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import User as StaffUser
from django.core.cache import cache
from django.test import Client

from apps.search.infrastructure import repositories as repo
from apps.search.infrastructure.models import SearchTerm

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _fresh_popular_cache():
    cache.delete(repo.POPULAR_CACHE_KEY)
    yield
    cache.delete(repo.POPULAR_CACHE_KEY)


def test_spellings_of_one_term_are_one_row_and_zero_results_are_counted():
    repo.record("Протеин", 3, "ru")
    repo.record("  протеин ", 0, "ru")

    row = SearchTerm.objects.get(term="protein")
    assert (row.searches, row.zero_results, row.last_results, row.display) == (2, 1, 0, "протеин")


def test_too_short_terms_are_ignored():
    repo.record("a", 5)
    assert not SearchTerm.objects.exists()


def test_only_submitted_first_page_searches_are_recorded(client):
    term = "zqxwvutsr"  # letters only: normalize() would split digits off into words
    client.get("/api/v1/products/search", {"q": term})  # type-ahead preview: no record flag
    client.get("/api/v1/products/search", {"q": term, "record": "1", "page": 2})
    assert not SearchTerm.objects.filter(term=term).exists()

    client.get("/api/v1/products/search", {"q": term, "record": "1"})
    row = SearchTerm.objects.get(term=term)
    assert (row.searches, row.last_results) == (1, 0)


def test_popular_lists_most_searched_terms_that_find_products(client):
    for _ in range(3):
        repo.record("kreatin", 4)
    repo.record("whey", 2)
    for _ in range(5):
        repo.record("nothing here", 0)

    body = client.get("/api/v1/products/search/popular", {"limit": 5}).json()
    assert body["data"] == ["kreatin", "whey"]


def test_dashboard_page_and_missing_tab():
    repo.record("vitamin d3", 0)
    repo.record("kreatin", 2)
    staff = Client()
    staff.force_login(StaffUser.objects.create_superuser(username=f"st_{uuid.uuid4().hex[:6]}", password="x-pass-12345"))

    page = staff.get("/django-admin/search/searchterm/")
    missing = staff.get("/django-admin/search/searchterm/?nz=missing")

    assert page.status_code == 200 and "kreatin" in page.content.decode()
    assert missing.status_code == 200 and "vitamin d3" in missing.content.decode() and "kreatin" not in missing.content.decode().split("nzi-row", 1)[-1]
