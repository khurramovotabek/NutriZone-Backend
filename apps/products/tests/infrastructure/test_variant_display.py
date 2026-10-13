"""`GET /api/v1/products/variants?ids=...` -- name/photo/size for order and cart lines."""
from __future__ import annotations

import uuid

import pytest
from django.test import Client

from apps.products.infrastructure import models as p_models

pytestmark = pytest.mark.django_db

URL = "/api/v1/products/variants"


def _product(status="published", name="Gold Standard Whey"):
    product = p_models.Product.objects.create(id=uuid.uuid4(), status=status)
    p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="uz", name=name, slug=f"whey-{uuid.uuid4().hex[:6]}")
    return product


def _variant(product, **kwargs):
    return p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:8]}", **kwargs)


def test_resolves_name_size_and_photo_preferring_the_variants_own_photo():
    product = _product()
    p_models.ProductMedia.objects.create(id=uuid.uuid4(), product=product, storage_path="image/family.jpg", media_role="primary")
    variant = _variant(product, weight_value=2.27, weight_unit="kg")
    p_models.ProductMedia.objects.create(id=uuid.uuid4(), product=product, variant=variant, storage_path="image/own.jpg", media_role="primary")
    plain = _variant(product)

    body = Client().get(URL, {"ids": f"{variant.id},{plain.id}"}).json()

    assert body["success"] is True
    by_id = {row["variant_id"]: row for row in body["data"]}
    assert by_id[str(variant.id)]["product_name"] == "Gold Standard Whey"
    assert by_id[str(variant.id)]["weight_value"] == 2.27 and by_id[str(variant.id)]["weight_unit"] == "kg"
    assert by_id[str(variant.id)]["image_url"].endswith("image/own.jpg")
    assert by_id[str(plain.id)]["image_url"].endswith("image/family.jpg")
    assert by_id[str(plain.id)]["is_published"] is True


def test_archived_product_still_resolves_but_is_flagged_unpublished():
    variant = _variant(_product(status="archived", name="Old Formula"))

    row = Client().get(URL, {"ids": str(variant.id)}).json()["data"][0]

    assert row["product_name"] == "Old Formula"
    assert row["is_published"] is False


def test_ignores_malformed_and_unknown_ids():
    body = Client().get(URL, {"ids": f"not-a-uuid,{uuid.uuid4()}"}).json()

    assert body["success"] is True and body["data"] == []


def _priced_product(base, compare_at=None, sale=None):
    from apps.pricing.infrastructure.models import PriceListEntryModel, PriceListModel

    product = _product()
    variant = _variant(product, is_default=True)
    price_list = PriceListModel.objects.create(id=uuid.uuid4(), code=f"pl-{uuid.uuid4().hex[:8]}", name="Default", currency="UZS")
    PriceListEntryModel.objects.create(id=uuid.uuid4(), price_list=price_list, product_variant_id=variant.id, base_price_amount=base, compare_at_price_amount=compare_at, sale_price_amount=sale)
    return product


def _card(product):
    from apps.products.infrastructure.selectors import ProductDetailSelector

    return ProductDetailSelector().get_by_id(product.id, locale="uz")


def test_card_shows_old_price_and_discount_from_the_editors_old_price():
    card = _card(_priced_product("850000", compare_at="1000000"))
    assert card["price"] == "850000.00"
    assert card["compare_at_price"] == "1000000.00"
    assert card["discount_percent"] == 15
    assert card["variants"][0]["discount_percent"] == 15


def test_sale_price_is_what_the_card_charges_and_base_becomes_the_old_price():
    card = _card(_priced_product("1000000", sale="800000"))
    assert card["price"] == "800000.00"  # matches checkout's CalculatePrice (sale price wins)
    assert card["compare_at_price"] == "1000000.00"
    assert card["discount_percent"] == 20


def test_no_discount_without_a_higher_old_price():
    card = _card(_priced_product("500000", compare_at="500000"))
    assert card["compare_at_price"] is None and card["discount_percent"] is None


def test_catalog_on_sale_filter_and_biggest_discount_sort():
    small = _priced_product("900000", compare_at="1000000")  # -10%
    big = _priced_product("700000", compare_at="1000000")  # -30%
    plain = _priced_product("500000")
    body = Client().get("/api/v1/products/search", {"q": "", "filter[on_sale]": "1", "sort": "-discount"}).json()

    ids = [p["id"] for p in body["data"]]
    assert ids == [str(big.id), str(small.id)]
    assert str(plain.id) not in ids
    assert body["meta"]["facets"]["on_sale_count"] == 2
