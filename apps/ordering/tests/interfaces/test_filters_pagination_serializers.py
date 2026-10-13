from __future__ import annotations

import pytest
from django.http import QueryDict

from apps.ordering.interfaces.api.v1.filters import parse_order_list_params
from apps.ordering.interfaces.api.v1.pagination import AdminOrderingPagination, OrderingPagination
from apps.ordering.interfaces.api.v1.serializers import (
    AddressInputSerializer, CreateOrderSerializer, LockOrderSerializer, OrderLineInputSerializer, RequestReturnSerializer,
)
from common.exceptions import ValidationFailed

pytestmark = pytest.mark.unit


def _qd(params: dict) -> QueryDict:
    qd = QueryDict(mutable=True)
    for key, value in params.items():
        qd[key] = value
    return qd


class TestOrderListParams:
    def test_defaults(self):
        params = parse_order_list_params(_qd({}))
        assert params.page == 1
        assert params.sort == "-created_at"

    def test_invalid_status_raises(self):
        with pytest.raises(ValidationFailed):
            parse_order_list_params(_qd({"filter[status]": "bogus"}))

    def test_completed_flag_normalizes_to_status(self):
        params = parse_order_list_params(_qd({"filter[completed]": "true"}))
        assert params.status == "completed"

    def test_cancelled_flag_normalizes_to_status(self):
        params = parse_order_list_params(_qd({"filter[cancelled]": "true"}))
        assert params.status == "cancelled"

    def test_invalid_datetime_raises(self):
        with pytest.raises(ValidationFailed):
            parse_order_list_params(_qd({"filter[created_after]": "not-a-date"}))

    def test_invalid_sort_raises(self):
        with pytest.raises(ValidationFailed):
            parse_order_list_params(_qd({"sort": "bogus"}))


class TestPagination:
    def test_ordering_pagination_defaults(self):
        pagination = OrderingPagination.from_query_params(_qd({}))
        assert pagination.page_size == 20

    def test_ordering_pagination_caps_at_100(self):
        pagination = OrderingPagination.from_query_params(_qd({"page_size": "9999"}))
        assert pagination.page_size == 100

    def test_admin_pagination_defaults_larger(self):
        pagination = AdminOrderingPagination.from_query_params(_qd({}))
        assert pagination.page_size == 50

    def test_admin_pagination_caps_at_200(self):
        pagination = AdminOrderingPagination.from_query_params(_qd({"page_size": "9999"}))
        assert pagination.page_size == 200

    def test_invalid_page_raises(self):
        with pytest.raises(ValidationFailed):
            OrderingPagination.from_query_params(_qd({"page": "not-a-number"}))


class TestSerializers:
    def test_address_input_serializer_valid(self):
        serializer = AddressInputSerializer(data={"recipient_name": "Jane", "line1": "123 Main St", "city": "Tashkent", "country_code": "UZ"})
        assert serializer.is_valid()

    def test_address_input_serializer_rejects_lowercase_country(self):
        serializer = AddressInputSerializer(data={"recipient_name": "Jane", "line1": "123 Main St", "city": "Tashkent", "country_code": "uz"})
        assert not serializer.is_valid()

    def test_order_line_input_serializer_rejects_zero_quantity(self):
        import uuid

        serializer = OrderLineInputSerializer(data={"product_variant_id": str(uuid.uuid4()), "quantity": 0, "unit_price": "10.00"})
        assert not serializer.is_valid()

    def test_create_order_serializer_rejects_empty_line_items(self):
        serializer = CreateOrderSerializer(data={
            "currency": "UZS", "shipping_address": {"recipient_name": "J", "line1": "x", "city": "Tashkent", "country_code": "UZ"},
            "billing_address": {"recipient_name": "J", "line1": "x", "city": "Tashkent", "country_code": "UZ"}, "line_items": [],
        })
        assert not serializer.is_valid()

    def test_lock_order_serializer_requires_valid_reason(self):
        serializer = LockOrderSerializer(data={"reason": "not_a_real_reason"})
        assert not serializer.is_valid()

    def test_request_return_serializer_rejects_empty_lines(self):
        serializer = RequestReturnSerializer(data={"reason": "defective", "lines": []})
        assert not serializer.is_valid()

    def test_request_return_serializer_requires_line_fields(self):
        serializer = RequestReturnSerializer(data={"reason": "defective", "lines": [{"quantity": 1}]})
        assert not serializer.is_valid()
