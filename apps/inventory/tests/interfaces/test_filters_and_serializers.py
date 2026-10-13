from __future__ import annotations

import pytest
from django.http import QueryDict

from apps.inventory.interfaces.api.v1.filters import (
    parse_expiring_batches_params, parse_inventory_list_params, parse_pagination, parse_stock_filter_params,
    parse_uuid_param,
)
from apps.inventory.interfaces.api.v1.serializers import (
    AdjustStockSerializer, CreateBatchSerializer, CreateInventorySerializer, CreateReservationSerializer,
    ReceiveStockSerializer,
)
from common.exceptions import ValidationFailed

pytestmark = pytest.mark.unit


def _qd(params: dict) -> QueryDict:
    qd = QueryDict(mutable=True)
    for key, value in params.items():
        qd[key] = value
    return qd


class TestInventoryListParams:
    def test_defaults(self):
        params = parse_inventory_list_params(_qd({}))
        assert params.page == 1
        assert params.sort == "-created_at"

    def test_valid_status_filter(self):
        params = parse_inventory_list_params(_qd({"filter[status]": "active"}))
        assert params.status == "active"

    def test_invalid_status_filter_raises(self):
        with pytest.raises(ValidationFailed):
            parse_inventory_list_params(_qd({"filter[status]": "bogus"}))

    def test_invalid_sort_raises(self):
        with pytest.raises(ValidationFailed):
            parse_inventory_list_params(_qd({"sort": "not-allowed"}))


class TestStockFilterParams:
    def test_valid_stock_status(self):
        params = parse_stock_filter_params(_qd({"filter[stock_status]": "available"}))
        assert params.stock_status == "available"

    def test_invalid_stock_status_raises(self):
        with pytest.raises(ValidationFailed):
            parse_stock_filter_params(_qd({"filter[stock_status]": "bogus"}))

    def test_warehouse_id_uuid_parsed(self):
        import uuid

        wid = str(uuid.uuid4())
        params = parse_stock_filter_params(_qd({"filter[warehouse_id]": wid}))
        assert str(params.warehouse_id) == wid


class TestExpiringBatchesParams:
    def test_default(self):
        assert parse_expiring_batches_params(_qd({})) == 30

    def test_rejects_non_positive(self):
        with pytest.raises(ValidationFailed):
            parse_expiring_batches_params(_qd({"within_days": "0"}))

    def test_rejects_non_integer(self):
        with pytest.raises(ValidationFailed):
            parse_expiring_batches_params(_qd({"within_days": "abc"}))


class TestPagination:
    def test_caps_page_size(self):
        params = parse_pagination(_qd({"page_size": "9999"}))
        assert params.page_size == 100


class TestSerializers:
    def test_create_inventory_serializer_valid(self):
        import uuid

        serializer = CreateInventorySerializer(data={"code": "WHEY001", "product_variant_id": str(uuid.uuid4())})
        assert serializer.is_valid()

    def test_create_inventory_serializer_rejects_invalid_code(self):
        import uuid

        serializer = CreateInventorySerializer(data={"code": "whey!", "product_variant_id": str(uuid.uuid4())})
        assert not serializer.is_valid()
        assert "code" in serializer.errors

    def test_receive_stock_serializer_rejects_zero_quantity(self):
        import uuid

        serializer = ReceiveStockSerializer(data={"warehouse_inventory_id": str(uuid.uuid4()), "quantity": 0, "reference": "PO-001"})
        assert not serializer.is_valid()

    def test_create_batch_serializer_validates_batch_number_format(self):
        import uuid

        serializer = CreateBatchSerializer(data={"inventory_id": str(uuid.uuid4()), "batch_number": "bad batch!"})
        assert not serializer.is_valid()

    def test_adjust_stock_serializer_requires_valid_enum_choices(self):
        import uuid

        serializer = AdjustStockSerializer(data={"warehouse_inventory_id": str(uuid.uuid4()), "stock_status": "bogus", "quantity_delta": 5, "reason": "manual", "reference": "ADJ-001"})
        assert not serializer.is_valid()

    def test_create_reservation_serializer_validates_number_format(self):
        import uuid

        serializer = CreateReservationSerializer(data={"reservation_number": "not-valid", "owner_type": "user", "owner_id": str(uuid.uuid4()), "warehouse_inventory_id": str(uuid.uuid4()), "quantity": 1})
        assert not serializer.is_valid()
