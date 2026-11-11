"""Order / filter words inside a search query (infrastructure/query_intent.py)."""
from __future__ import annotations

import pytest

from apps.products.infrastructure.query_intent import parse


@pytest.mark.parametrize("raw, query, sort, filters", [
    ("arzon kreatin", "kreatin", "price", {}),
    ("eng arzon protein", "protein", "price", {}),
    ("qimmat protein", "protein", "-price", {}),
    ("chegirmadagi protein", "protein", None, {"on_sale": True}),
    ("скидки", "", None, {"on_sale": True}),
    ("дешевый протеин до 400 тысяч", "protein", "price", {"price": {"lte": "400000"}}),
    ("500 minggacha gainer", "gainer", None, {"price": {"lte": "500000"}}),
    ("500 000 so'mgacha protein", "protein", None, {"price": {"lte": "500000"}}),
    ("300 mingdan arzon kreatin", "kreatin", None, {"price": {"lte": "300000"}}),
    ("1 mln dan qimmat", "", None, {"price": {"gte": "1000000"}}),
    ("yangi vitaminlar", "vitaminlar", "-created_at", {}),
    ("mavjud kreatin", "kreatin", None, {"in_stock": True}),
])
def test_intent_words_leave_the_query(raw, query, sort, filters):
    intent = parse(raw)
    assert (intent.query, intent.sort, intent.filters) == (query, sort, filters)


@pytest.mark.parametrize("raw", ["vitamin d3 5000 iu", "whey 2270 g", "hitech creatine", "on whey", "Optimum Nutrition Gold Standard"])
def test_product_words_and_sizes_are_left_alone(raw):
    intent = parse(raw)
    assert intent.query == raw and intent.sort is None and intent.filters == {} and intent.understood == []
