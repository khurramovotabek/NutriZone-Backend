"""
Catalog browse (infrastructure/catalog_browse.py): every storefront filter
is really applied, facets count correctly (each dimension ignores its own
filter), and every sort order works -- end to end through the API.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.products.infrastructure import models as p_models
from apps.products.infrastructure.catalog_browse import size_band, size_key
from apps.products.tests.stock_helpers import put_stock

pytestmark = pytest.mark.django_db

URL = "/api/v1/products/search"


@pytest.fixture
def catalog():
    """Four real products in one fresh category, with prices, sizes, flavours and stock."""
    from apps.pricing.infrastructure import models as pricing_orm

    category = p_models.Category.objects.create(id=uuid.uuid4(), is_active=True)
    brand_a, brand_b = (p_models.Brand.objects.create(id=uuid.uuid4()) for _ in range(2))
    for brand, name in ((brand_a, "Alpha Labs"), (brand_b, "Beta Sport")):
        p_models.BrandTranslation.objects.create(id=uuid.uuid4(), brand=brand, locale_code="en", name=name, slug=f"b-{uuid.uuid4().hex[:8]}")
    vanilla, choco = (p_models.Flavour.objects.create(id=uuid.uuid4(), is_active=True, slug=f"f-{uuid.uuid4().hex[:8]}", color_hex="#ffffff") for _ in range(2))
    price_list, _ = pricing_orm.PriceListModel.objects.get_or_create(code="DEFAULT-UZS", defaults={"name": "Default", "currency": "UZS", "status": "active"})

    def product(name, brand, price, weight, stock, flavours=()):
        p = p_models.Product.objects.create(id=uuid.uuid4(), status="published", category=category, brand=brand)
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=p, locale_code="en", name=name, slug=f"p-{uuid.uuid4().hex[:8]}")
        v = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=p, sku=f"SKU-{uuid.uuid4().hex[:8]}", is_default=True, status="active", weight_value=weight[0], weight_unit=weight[1])
        pricing_orm.PriceListEntryModel.objects.create(price_list=price_list, product_variant_id=v.id, base_price_amount=Decimal(price))
        put_stock(v.id, stock)
        for f in flavours:
            p_models.ProductFlavour.objects.create(product=p, flavour=f)
        return p

    items = {
        "a_whey": product("Alpha Whey", brand_a, "500000", (2270, "g"), 12, [vanilla, choco]),
        "a_crea": product("Alpha Creatine", brand_a, "180000", (250, "g"), 0),
        "b_whey": product("Beta Whey", brand_b, "650000", (2270, "g"), 5, [choco]),
        "b_bcaa": product("Beta BCAA", brand_b, "220000", (400, "g"), 30, [vanilla]),
    }
    ratings = {str(items["a_whey"].id): 4.6, str(items["b_whey"].id): 3.4, str(items["b_bcaa"].id): 4.1}
    return {"category": category, "brand_a": brand_a, "brand_b": brand_b, "vanilla": vanilla, "choco": choco, "ratings": ratings, **items}


def _get(client, catalog, **params):
    query = {"filter[category_id]": str(catalog["category"].id), "page_size": 50, **params}
    summaries = {pid: {"average": avg, "count": 3} for pid, avg in catalog["ratings"].items()}
    with patch("apps.products.infrastructure.selectors._bulk_rating_summary", side_effect=lambda ids: {str(i): summaries[str(i)] for i in ids if str(i) in summaries}):
        response = client.get(URL, query)
    assert response.status_code == 200, response.content
    return response.json()


def _ids(body):
    return [row["id"] for row in body["data"]]


def _id(product):
    return str(product.id)


class TestFilters:
    def test_several_brands_at_once(self, client, catalog):
        body = _get(client, catalog, **{"filter[brand_id]": f"{catalog['brand_a'].id},{catalog['brand_b'].id}"})
        assert len(_ids(body)) == 4
        body = _get(client, catalog, **{"filter[brand_id]": str(catalog["brand_b"].id)})
        assert set(_ids(body)) == {_id(catalog["b_whey"]), _id(catalog["b_bcaa"])}

    def test_price_range(self, client, catalog):
        body = _get(client, catalog, **{"filter[price][gte]": "200000", "filter[price][lte]": "600000"})
        assert set(_ids(body)) == {_id(catalog["a_whey"]), _id(catalog["b_bcaa"])}

    def test_minimum_rating(self, client, catalog):
        body = _get(client, catalog, **{"filter[rating][gte]": "4"})
        assert set(_ids(body)) == {_id(catalog["a_whey"]), _id(catalog["b_bcaa"])}

    def test_flavour_any_of(self, client, catalog):
        body = _get(client, catalog, **{"filter[flavor_id]": str(catalog["choco"].id)})
        assert set(_ids(body)) == {_id(catalog["a_whey"]), _id(catalog["b_whey"])}

    def test_size_any_of(self, client, catalog):
        body = _get(client, catalog, **{"filter[size]": "250g,400g"})
        assert set(_ids(body)) == {_id(catalog["a_crea"]), _id(catalog["b_bcaa"])}

    def test_size_band_takes_every_pack_size_in_its_range(self, client, catalog):
        body = _get(client, catalog, **{"filter[size]": "2-3kg"})
        assert set(_ids(body)) == {_id(catalog["a_whey"]), _id(catalog["b_whey"])}

    def test_size_bands_and_exact_sizes_combine_as_any_of(self, client, catalog):
        body = _get(client, catalog, **{"filter[size]": "2-3kg,400g"})
        assert len(_ids(body)) == 3

    def test_in_stock_only(self, client, catalog):
        body = _get(client, catalog, **{"filter[availability]": "in_stock"})
        assert _id(catalog["a_crea"]) not in _ids(body)
        assert len(_ids(body)) == 3

    def test_filters_combine_with_the_smart_query(self, client, catalog):
        body = _get(client, catalog, q="whey", **{"filter[price][lte]": "600000"})
        assert _ids(body) == [_id(catalog["a_whey"])]

    @pytest.mark.parametrize("param, value", [("filter[rating][gte]", "9"), ("filter[price][gte]", "abc"), ("filter[brand_id]", "not-a-uuid"), ("sort", "bogus")])
    def test_invalid_filter_values_are_rejected(self, client, catalog, param, value):
        response = client.get(URL, {param: value})
        assert response.status_code == 422


class TestFacets:
    def test_each_dimension_counts_without_its_own_filter(self, client, catalog):
        body = _get(client, catalog, **{"filter[brand_id]": str(catalog["brand_a"].id)})
        facets = body["meta"]["facets"]
        # brand counts ignore the brand filter itself...
        assert {b["name"]: b["count"] for b in facets["brand"]} == {"Alpha Labs": 2, "Beta Sport": 2}
        # ...while every other dimension respects it (only Alpha's two products)
        assert {s["id"]: s["count"] for s in facets["size"]} == {"250g": 1, "2270g": 1}
        assert facets["price_range"] == {"min": "180000.00", "max": "500000.00"}
        assert facets["in_stock_count"] == 1

    def test_flavour_rating_and_size_facets(self, client, catalog):
        facets = _get(client, catalog)["meta"]["facets"]
        assert {f["id"]: f["count"] for f in facets["flavour"]} == {str(catalog["vanilla"].id): 2, str(catalog["choco"].id): 2}
        assert {r["min"]: r["count"] for r in facets["rating"]} == {4: 2, 3: 3, 2: 3, 1: 3}
        assert [s["id"] for s in facets["size"]] == ["250g", "400g", "2270g"]  # sorted by real weight
        # the bands a shopper sees, in their fixed order, counting products
        assert [(b["id"], b["kind"], b["count"]) for b in facets["size_band"]] == [("upto-300g", "mass", 1), ("300g-1kg", "mass", 1), ("2-3kg", "mass", 2)]


class TestSorting:
    @pytest.mark.parametrize("sort, first", [("price", "a_crea"), ("-price", "b_whey"), ("-rating", "a_whey"), ("name", "a_crea")])
    def test_sort_orders(self, client, catalog, sort, first):
        assert _ids(_get(client, catalog, sort=sort))[0] == _id(catalog[first])


@pytest.mark.parametrize("value, unit, expected", [(250, "g", "250g"), (Decimal("2.270"), "kg", "2.27kg"), (Decimal("1.0"), "kg", "1kg"), (None, "g", None)])
def test_size_key(value, unit, expected):
    assert size_key(value, unit) == expected


@pytest.mark.parametrize("key, band", [("250g", "upto-300g"), ("2270g", "2-3kg"), ("2.27kg", "2-3kg"), ("5lb", "2-3kg"), ("60capsule", "upto-60pcs"), ("120tablet", "61-120pcs"), ("500ml", "250ml-1l"), ("1l", "1l-plus"), ("12x", None), (None, None)])
def test_size_band(key, band):
    assert size_band(key) == band
