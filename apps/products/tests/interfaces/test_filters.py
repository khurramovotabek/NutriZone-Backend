from __future__ import annotations

import uuid

import pytest
from django.http import QueryDict

from apps.products.interfaces.api.v1.filters import (
    parse_admin_catalog_list_params,
    parse_catalog_list_params,
    parse_search_params,
)
from common.exceptions import ValidationFailed

pytestmark = pytest.mark.unit


def _qd(params: dict) -> QueryDict:
    qd = QueryDict(mutable=True)
    for key, value in params.items():
        qd[key] = value
    return qd


class TestCatalogListParams:
    def test_defaults(self):
        params = parse_catalog_list_params(_qd({}))
        assert params.page == 1
        assert params.page_size == 20
        assert params.category_id is None

    def test_parses_valid_uuids(self):
        cid = str(uuid.uuid4())
        params = parse_catalog_list_params(_qd({"filter[category_id]": cid}))
        assert str(params.category_id) == cid

    def test_invalid_uuid_raises(self):
        with pytest.raises(ValidationFailed):
            parse_catalog_list_params(_qd({"filter[category_id]": "not-a-uuid"}))

    def test_page_size_capped_at_max(self):
        params = parse_catalog_list_params(_qd({"page_size": "500"}))
        assert params.page_size == 100

    def test_invalid_page_raises(self):
        with pytest.raises(ValidationFailed):
            parse_catalog_list_params(_qd({"page": "not-a-number"}))


class TestSearchParams:
    def test_defaults(self):
        params = parse_search_params(_qd({}))
        assert params.query == ""
        assert params.sort == "-created_at"

    def test_invalid_sort_raises(self):
        with pytest.raises(ValidationFailed):
            parse_search_params(_qd({"sort": "not-allowed"}))

    def test_availability_filter_validated(self):
        with pytest.raises(ValidationFailed):
            parse_search_params(_qd({"filter[availability]": "bogus"}))

    def test_valid_availability_filter_accepted(self):
        params = parse_search_params(_qd({"filter[availability]": "in_stock"}))
        assert params.filters["availability"] == "in_stock"

    def test_nutrition_category_filter_validated(self):
        with pytest.raises(ValidationFailed):
            parse_search_params(_qd({"filter[nutrition_category]": "bogus"}))

    def test_gender_filter_validated(self):
        with pytest.raises(ValidationFailed):
            parse_search_params(_qd({"filter[gender]": "bogus"}))

    def test_age_group_filter_validated(self):
        with pytest.raises(ValidationFailed):
            parse_search_params(_qd({"filter[age_group]": "bogus"}))

    def test_price_range_filter_parsed(self):
        params = parse_search_params(_qd({"filter[price][gte]": "10000", "filter[price][lte]": "50000"}))
        assert params.filters["price"] == {"gte": "10000", "lte": "50000"}

    def test_tags_filter_splits_on_comma(self):
        params = parse_search_params(_qd({"filter[tags]": "vegan,gluten-free"}))
        assert params.filters["tags"] == ["vegan", "gluten-free"]

    def test_sku_slug_barcode_filters_pass_through(self):
        params = parse_search_params(_qd({"filter[sku]": "SKU-1", "filter[slug]": "whey", "filter[barcode]": "123"}))
        assert params.filters["sku"] == "SKU-1"
        assert params.filters["slug"] == "whey"
        assert params.filters["barcode"] == "123"

    def test_date_range_filters_parsed(self):
        params = parse_search_params(_qd({"filter[created_at][gte]": "2026-01-01"}))
        assert params.filters["created_at"]["gte"] == "2026-01-01"


class TestAdminCatalogListParams:
    def test_valid_status_accepted(self):
        params = parse_admin_catalog_list_params(_qd({"filter[status]": "draft"}))
        assert params.status == "draft"

    def test_invalid_status_raises(self):
        with pytest.raises(ValidationFailed):
            parse_admin_catalog_list_params(_qd({"filter[status]": "not-a-status"}))
