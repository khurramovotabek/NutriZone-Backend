"""Dashboard lists: "Sahifada: 25 · 50 · 100 · 200" remembered per list, and the jump-to-page box."""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.django_db
URL = "/django-admin/reviews/reviewmodel/"


def _reviews(n):
    from apps.reviews.infrastructure.models import ReviewModel

    ReviewModel.objects.bulk_create([ReviewModel(id=uuid.uuid4(), product_id=uuid.uuid4(), customer_id=uuid.uuid4(), rating=5, body=f"Sharh {i}", status="published") for i in range(n)])


def test_size_links_and_choice_is_remembered_per_list(admin_client):
    _reviews(60)
    html = admin_client.get(URL).content.decode()
    assert "nz-pager-sizes" in html and "nz_per=50" in html
    r = admin_client.get(URL + "?nz_per=50&p=2")  # the size param never reaches ChangeList as a filter
    assert r.status_code == 200
    html = admin_client.get(URL).content.decode()
    assert 'is-current" aria-current="true">50' in html and 'data-nz-end="50"' in html
    assert admin_client.session["nz_per_page"] == {URL: 50}
    other = admin_client.get("/django-admin/reviews/productquestionmodel/")
    assert other.status_code == 200  # other lists keep their own size


def test_jump_box_only_for_long_lists_and_bad_values_reset(admin_client):
    _reviews(60)
    admin_client.get(URL + "?nz_per=10")  # 6 pages
    html = admin_client.get(URL).content.decode()
    assert "data-nz-jump" in html and "__P__" in html
    admin_client.get(URL + "?nz_per=abc")
    assert admin_client.session["nz_per_page"] == {URL: 10}
    admin_client.get(URL + "?nz_per=0")
    assert URL not in admin_client.session["nz_per_page"]
