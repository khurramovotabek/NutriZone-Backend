"""
List-level product cards carry the product's total available stock
(`stock_quantity` / `stock_status`) -- summed across every variant and
warehouse, resolved in bulk for the whole page.
"""
from __future__ import annotations

import uuid

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.products.infrastructure import models as p_models
from apps.products.infrastructure.selectors import CatalogSelector
from apps.products.tests.stock_helpers import location, put_stock

pytestmark = pytest.mark.django_db


def _product(stock_per_variant: list[int] | None):
    """A published product; `None` = no inventory record at all (not tracked)."""
    category = p_models.Category.objects.create(id=uuid.uuid4(), is_active=True)
    product = p_models.Product.objects.create(id=uuid.uuid4(), status="published", category=category)
    for idx, quantity in enumerate(stock_per_variant or [0]):
        variant = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:8]}", is_default=idx == 0)
        if stock_per_variant is None:
            continue
        # split each variant's stock over a warehouse and a branch to prove both levels are summed
        put_stock(variant.id, quantity // 2, store=location("WH", kind="warehouse"))
        put_stock(variant.id, quantity - quantity // 2)
    return product


def _card(product):
    cards, _total = CatalogSelector().list(category_id=product.category_id)
    return next(c for c in cards if c["id"] == str(product.id))


def test_total_stock_is_summed_across_variants_and_warehouses():
    product = _product([40, 55])
    card = _card(product)
    assert card["stock_quantity"] == 95
    assert card["stock_status"] == "in_stock"


def test_low_and_out_of_stock_statuses():
    assert _card(_product([3]))["stock_status"] == "low_stock"
    out = _card(_product([0]))
    assert (out["stock_quantity"], out["stock_status"]) == (0, "out_of_stock")


def test_untracked_product_reports_none_not_a_made_up_count():
    card = _card(_product(None))
    assert card["stock_quantity"] is None
    assert card["stock_status"] is None


def test_stock_adds_a_constant_number_of_queries_not_one_per_card():
    category = p_models.Category.objects.create(id=uuid.uuid4(), is_active=True)

    def make(n):
        for _ in range(n):
            product = _product([5, 5])
            p_models.Product.objects.filter(id=product.id).update(category=category)

    make(3)
    with CaptureQueriesContext(connection) as small:
        CatalogSelector().list(category_id=category.id)
    make(6)
    with CaptureQueriesContext(connection) as large:
        CatalogSelector().list(category_id=category.id)
    assert len(large.captured_queries) == len(small.captured_queries)
