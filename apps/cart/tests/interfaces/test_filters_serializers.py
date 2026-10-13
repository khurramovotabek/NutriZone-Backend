from __future__ import annotations

import pytest
from django.http import QueryDict

from apps.cart.interfaces.api.v1.filters import parse_cart_list_params, parse_pagination
from apps.cart.interfaces.api.v1.serializers import AddItemSerializer, CreateCartSerializer, LockCartSerializer, UpdateCartSerializer
from common.exceptions import ValidationFailed

pytestmark = pytest.mark.unit


def _qd(params: dict) -> QueryDict:
    qd = QueryDict(mutable=True)
    for key, value in params.items():
        qd[key] = value
    return qd


class TestCartListParams:
    def test_defaults(self):
        params = parse_cart_list_params(_qd({}))
        assert params.page == 1
        assert params.sort == "-created_at"

    def test_invalid_status_raises(self):
        with pytest.raises(ValidationFailed):
            parse_cart_list_params(_qd({"filter[status]": "bogus"}))

    def test_invalid_cart_type_raises(self):
        with pytest.raises(ValidationFailed):
            parse_cart_list_params(_qd({"filter[cart_type]": "bogus"}))

    def test_locked_flag_parsing(self):
        params = parse_cart_list_params(_qd({"filter[locked]": "true"}))
        assert params.is_locked is True

    def test_converted_flag_normalizes_to_status_filter(self):
        params = parse_cart_list_params(_qd({"filter[converted]": "true"}))
        assert params.status == "converted"

    def test_invalid_datetime_raises(self):
        with pytest.raises(ValidationFailed):
            parse_cart_list_params(_qd({"filter[created_after]": "not-a-date"}))

    def test_invalid_sort_raises(self):
        with pytest.raises(ValidationFailed):
            parse_cart_list_params(_qd({"sort": "bogus"}))


class TestPagination:
    def test_caps_page_size(self):
        params = parse_pagination(_qd({"page_size": "9999"}))
        assert params.page_size == 100


class TestSerializers:
    def test_create_cart_serializer_defaults(self):
        serializer = CreateCartSerializer(data={})
        assert serializer.is_valid()
        assert serializer.validated_data["currency"] == "UZS"

    def test_add_item_serializer_rejects_zero_quantity(self):
        import uuid

        serializer = AddItemSerializer(data={"product_variant_id": str(uuid.uuid4()), "quantity": 0})
        assert not serializer.is_valid()

    def test_update_cart_serializer_rejects_too_long_note(self):
        serializer = UpdateCartSerializer(data={"note": "x" * 1001})
        assert not serializer.is_valid()

    def test_lock_cart_serializer_defaults_to_checkout_in_progress(self):
        serializer = LockCartSerializer(data={})
        assert serializer.is_valid()
        assert serializer.validated_data["reason"] == "checkout_in_progress"

    def test_lock_cart_serializer_rejects_invalid_reason(self):
        serializer = LockCartSerializer(data={"reason": "not_a_real_reason"})
        assert not serializer.is_valid()
