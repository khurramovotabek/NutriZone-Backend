"""
Product detail: each variant's `store_availability` -- which real stores
(branches) hold it and how many units each, read from the WMS stock (on hand − reserved).
"""
from __future__ import annotations

import uuid

import pytest

from apps.products.infrastructure import models as p_models
from apps.products.infrastructure.selectors import ProductDetailSelector
from apps.products.tests.stock_helpers import put_stock

pytestmark = pytest.mark.django_db


def _store(name: str, status: str = "active", kind: str = "store"):
    from apps.stores.infrastructure.models import Store

    return Store.objects.create(id=uuid.uuid4(), name=name, slug=f"s-{uuid.uuid4().hex[:8]}", status=status, kind=kind, city="Toshkent", district="Olmazor")


def _stock(variant, store, quantity, reserved=0):
    put_stock(variant.id, quantity, store=store, reserved=reserved)


def _product_with_variant():
    slug = f"p-{uuid.uuid4().hex[:8]}"
    product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
    p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name="Availability Test", slug=slug)
    variant = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:8]}", is_default=True, status="active")
    return slug, variant


def _availability(slug):
    detail = ProductDetailSelector().get_by_slug(slug, locale="en")
    (variant,) = detail["variants"]
    return variant


def test_lists_each_store_with_its_own_count_stocked_stores_first():
    slug, variant = _product_with_variant()
    small, big, empty = _store("Chilonzor"), _store("Olmazor"), _store("Yunusobod")
    _stock(variant, small, 4)
    _stock(variant, big, 40)
    _stock(variant, empty, 0)

    result = _availability(slug)

    assert [(s["name"], s["available_quantity"]) for s in result["store_availability"]] == [("Olmazor", 40), ("Chilonzor", 4), ("Yunusobod", 0)]
    assert result["store_availability"][0]["slug"] == big.slug
    assert result["stock_quantity"] == 44


def test_inactive_stores_and_warehouses_are_not_listed():
    slug, variant = _product_with_variant()
    _stock(variant, _store("Closed branch", status="inactive"), 10)
    _stock(variant, _store("Main warehouse", kind="warehouse"), 30)

    result = _availability(slug)
    assert result["store_availability"] == []
    assert result["stock_quantity"] == 30  # the warehouse still counts toward what can be sold online


def test_reserved_units_are_not_sellable():
    """The storefront reads the WMS stock: units reserved for orders / transfers are no longer for sale."""
    slug, variant = _product_with_variant()
    _stock(variant, _store("Olmazor"), 10, reserved=8)

    result = _availability(slug)
    assert [(s["name"], s["available_quantity"]) for s in result["store_availability"]] == [("Olmazor", 2)]
    assert (result["stock_status"], result["stock_quantity"]) == ("low_stock", 2)


def test_variant_with_no_inventory_has_an_empty_list():
    slug, _variant = _product_with_variant()
    result = _availability(slug)
    assert result["store_availability"] == []
    assert (result["stock_status"], result["stock_quantity"]) == ("out_of_stock", 0)
