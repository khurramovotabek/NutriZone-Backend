"""The product list's brand / category filters read every name with one query, not one per brand and category."""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from apps.products.infrastructure import models as orm

pytestmark = pytest.mark.django_db


def _brand(i):
    b = orm.Brand.objects.create()
    orm.BrandTranslation.objects.create(brand=b, locale_code="uz", name=f"Brend {i}", slug=f"fq-brand-{i}")
    return b


def test_brand_filter_names_cost_one_query():
    for i in range(6):
        _brand(i)
    user = get_user_model().objects.create(username="fq-admin", is_staff=True, is_superuser=True)
    client = Client()
    client.force_login(user)
    with CaptureQueriesContext(connection) as q:
        html = client.get("/django-admin/products/product/").content.decode()
    assert "Brend 0" in html and "Brend 5" in html
    per_brand = [x for x in q.captured_queries if '"catalog_brand_translations"' in x["sql"] and "WHERE" in x["sql"] and '"brand_id" =' in x["sql"]]
    assert per_brand == []
