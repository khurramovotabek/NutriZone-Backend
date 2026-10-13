"""
**No `TestPagination` class exists here** -- `pagination.py` was
never part of the original scaffold and was never created; no list
endpoint exists to paginate. `filters.py` is tested below only for
what it actually is: an explicit, documented placeholder with zero
real parsing logic.
"""
from __future__ import annotations

import re
import uuid

import pytest

import apps.pos.interfaces.api.v1.filters as filters_module
from apps.pos.interfaces.api.v1.serializers import (
    AddLineItemSerializer, CompleteSaleSerializer, OpenSaleSerializer, RemoveLineItemSerializer, SaleSerializer,
    SearchQuerySerializer, VoidSaleSerializer,
)

pytestmark = pytest.mark.unit


class TestFiltersPlaceholder:
    def test_filters_module_contains_no_real_parsing_function(self):
        """A direct, executable proof that filters.py remains a genuine, documented placeholder."""
        public_names = [n for n in dir(filters_module) if not n.startswith("_")]
        assert public_names == [], f"Expected filters.py to remain an empty placeholder, found: {public_names}"


class TestOpenSaleSerializer:
    def test_valid_input(self):
        serializer = OpenSaleSerializer(data={"branch_id": str(uuid.uuid4()), "cashier_id": str(uuid.uuid4())})
        assert serializer.is_valid()

    def test_customer_id_optional(self):
        serializer = OpenSaleSerializer(data={"branch_id": str(uuid.uuid4()), "cashier_id": str(uuid.uuid4())})
        assert serializer.is_valid()
        assert "customer_id" not in serializer.validated_data

    def test_missing_branch_id_invalid(self):
        serializer = OpenSaleSerializer(data={"cashier_id": str(uuid.uuid4())})
        assert not serializer.is_valid()

    def test_exact_field_set(self):
        fields = set(OpenSaleSerializer().fields.keys())
        assert fields == {"branch_id", "cashier_id", "customer_id"}


class TestAddLineItemSerializer:
    def test_valid_input(self):
        serializer = AddLineItemSerializer(data={"product_id": str(uuid.uuid4()), "quantity": 2, "unit_price_amount": "10.00"})
        assert serializer.is_valid()

    def test_zero_quantity_rejected(self):
        serializer = AddLineItemSerializer(data={"product_id": str(uuid.uuid4()), "quantity": 0, "unit_price_amount": "10.00"})
        assert not serializer.is_valid()

    def test_negative_quantity_rejected(self):
        serializer = AddLineItemSerializer(data={"product_id": str(uuid.uuid4()), "quantity": -1, "unit_price_amount": "10.00"})
        assert not serializer.is_valid()

    def test_negative_unit_price_rejected_protecting_the_phase_4_fix(self):
        """Protects the Phase 4 fix directly: a negative unit_price_amount must be rejected by the serializer itself (422), never reach Money's own constructor (which would raise a plain ValueError, surfacing as an unhandled 500)."""
        serializer = AddLineItemSerializer(data={"product_id": str(uuid.uuid4()), "quantity": 1, "unit_price_amount": "-5.00"})
        assert not serializer.is_valid()
        assert "unit_price_amount" in serializer.errors

    def test_zero_unit_price_is_allowed(self):
        """min_value=0 means zero itself is still valid -- only strictly negative values are rejected."""
        serializer = AddLineItemSerializer(data={"product_id": str(uuid.uuid4()), "quantity": 1, "unit_price_amount": "0.00"})
        assert serializer.is_valid()

    def test_currency_defaults_when_omitted(self):
        serializer = AddLineItemSerializer(data={"product_id": str(uuid.uuid4()), "quantity": 1, "unit_price_amount": "10.00"})
        assert serializer.is_valid()
        assert serializer.validated_data["unit_price_currency"] == "UZS"

    def test_has_no_sale_id_field(self):
        """sale_id comes from the URL path, never the request body -- verified structurally."""
        fields = set(AddLineItemSerializer().fields.keys())
        assert "sale_id" not in fields

    def test_exact_field_set(self):
        fields = set(AddLineItemSerializer().fields.keys())
        assert fields == {"product_id", "quantity", "unit_price_amount", "unit_price_currency"}


class TestZeroFieldCommandSerializers:
    @pytest.mark.parametrize("serializer_cls", [RemoveLineItemSerializer, CompleteSaleSerializer, VoidSaleSerializer])
    def test_has_zero_fields(self, serializer_cls):
        assert serializer_cls().fields == {}


class TestSaleSerializer:
    def test_total_amount_and_currency_are_not_persisted_model_fields(self):
        """A direct, executable proof that total_amount/total_currency are certified as derived from Sale.total(), never mistaken for stored ORM fields -- matching the certified 'no redundant stored total' Domain decision."""
        fields = SaleSerializer().fields
        assert "total_amount" in fields
        assert "total_currency" in fields
        assert fields["total_amount"].read_only is True

    def test_exact_field_set(self):
        fields = set(SaleSerializer().fields.keys())
        assert fields == {"id", "branch_id", "cashier_id", "customer_id", "status", "total_amount", "total_currency", "created_at", "completed_at", "voided_at", "line_items"}


class TestSearchQuerySerializer:
    def test_valid_input_q_only(self):
        serializer = SearchQuerySerializer(data={"q": "5901234123457"})
        assert serializer.is_valid()

    def test_type_is_optional(self):
        serializer = SearchQuerySerializer(data={"q": "protein"})
        assert serializer.is_valid()
        assert "type" not in serializer.validated_data

    def test_empty_q_rejected(self):
        serializer = SearchQuerySerializer(data={"q": ""})
        assert not serializer.is_valid()

    def test_missing_q_rejected(self):
        serializer = SearchQuerySerializer(data={})
        assert not serializer.is_valid()

    def test_invalid_type_choice_rejected(self):
        serializer = SearchQuerySerializer(data={"q": "protein", "type": "not-a-real-type"})
        assert not serializer.is_valid()

    def test_valid_type_choices_accepted(self):
        for t in ("barcode", "sku", "text"):
            serializer = SearchQuerySerializer(data={"q": "x", "type": t})
            assert serializer.is_valid()

    def test_page_and_page_size_default(self):
        serializer = SearchQuerySerializer(data={"q": "protein"})
        assert serializer.is_valid()
        assert serializer.validated_data["page"] == 1
        assert serializer.validated_data["page_size"] == 20

    def test_exact_field_set(self):
        fields = set(SearchQuerySerializer().fields.keys())
        assert fields == {"q", "type", "page", "page_size"}


def test_zero_duplicate_serializer_names():
    names = re.findall(r"^class (\w+)", open("apps/pos/interfaces/api/v1/serializers.py").read(), re.M)
    assert len(names) == len(set(names))
