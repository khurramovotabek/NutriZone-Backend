from __future__ import annotations

import re
import uuid

import pytest
from django.http import QueryDict

from apps.reviews.interfaces.api.v1.filters import (
    parse_admin_review_list_params, parse_customer_review_list_params, parse_product_review_list_params,
)
from apps.reviews.interfaces.api.v1.pagination import AdminReviewPagination, ReviewPagination
from apps.reviews.interfaces.api.v1.serializers import (
    AttachReviewMediaSerializer, CreateReviewSerializer, EditReviewSerializer, HideReviewSerializer,
    RejectReviewSerializer,
)
from common.exceptions import ValidationFailed

pytestmark = pytest.mark.unit


def _qd(params: dict) -> QueryDict:
    qd = QueryDict(mutable=True)
    for key, value in params.items():
        qd[key] = value
    return qd


class TestProductReviewListParams:
    def test_defaults(self):
        params = parse_product_review_list_params(_qd({}))
        assert params.page == 1
        assert params.status is None

    def test_invalid_status_raises(self):
        with pytest.raises(ValidationFailed):
            parse_product_review_list_params(_qd({"filter[status]": "bogus"}))

    def test_valid_status_accepted(self):
        params = parse_product_review_list_params(_qd({"filter[status]": "published"}))
        assert params.status == "published"


class TestCustomerReviewListParams:
    def test_defaults(self):
        params = parse_customer_review_list_params(_qd({}))
        assert params.page == 1
        assert params.page_size == 20


class TestAdminReviewListParams:
    def test_defaults(self):
        params = parse_admin_review_list_params(_qd({}))
        assert params.status is None

    def test_invalid_status_raises(self):
        with pytest.raises(ValidationFailed):
            parse_admin_review_list_params(_qd({"filter[status]": "bogus"}))


class TestPagination:
    def test_review_pagination_defaults(self):
        pagination = ReviewPagination.from_query_params(_qd({}))
        assert pagination.page_size == 20

    def test_review_pagination_caps_at_100(self):
        pagination = ReviewPagination.from_query_params(_qd({"page_size": "9999"}))
        assert pagination.page_size == 100

    def test_admin_review_pagination_defaults_larger(self):
        pagination = AdminReviewPagination.from_query_params(_qd({}))
        assert pagination.page_size == 50

    def test_admin_review_pagination_caps_at_200(self):
        pagination = AdminReviewPagination.from_query_params(_qd({"page_size": "9999"}))
        assert pagination.page_size == 200

    def test_invalid_page_raises(self):
        with pytest.raises(ValidationFailed):
            ReviewPagination.from_query_params(_qd({"page": "not-a-number"}))


class TestSerializers:
    def test_create_review_serializer_valid(self):
        serializer = CreateReviewSerializer(data={"product_id": str(uuid.uuid4()), "rating": 5, "body": "Great product."})
        assert serializer.is_valid()

    def test_create_review_serializer_rejects_rating_out_of_bounds(self):
        serializer = CreateReviewSerializer(data={"product_id": str(uuid.uuid4()), "rating": 6, "body": "x"})
        assert not serializer.is_valid()

    def test_create_review_serializer_rejects_empty_body(self):
        serializer = CreateReviewSerializer(data={"product_id": str(uuid.uuid4()), "rating": 5, "body": ""})
        assert not serializer.is_valid()

    def test_create_review_serializer_has_no_verified_purchase_field(self):
        """Verifies the deliberate absence documented in views.py/serializers.py -- a client cannot set verified_purchase themselves."""
        serializer = CreateReviewSerializer(data={"product_id": str(uuid.uuid4()), "rating": 5, "body": "x", "verified_purchase": True})
        assert serializer.is_valid()
        assert "verified_purchase" not in serializer.validated_data

    def test_edit_review_serializer_all_fields_optional(self):
        serializer = EditReviewSerializer(data={})
        assert serializer.is_valid()

    def test_reject_review_serializer_requires_valid_reason(self):
        serializer = RejectReviewSerializer(data={"reason": "not_a_real_reason"})
        assert not serializer.is_valid()

    def test_hide_review_serializer_requires_valid_reason(self):
        serializer = HideReviewSerializer(data={"reason": "not_a_real_reason"})
        assert not serializer.is_valid()

    def test_attach_review_media_serializer_requires_url(self):
        serializer = AttachReviewMediaSerializer(data={"media_type": "image"})
        assert not serializer.is_valid()

    def test_zero_duplicate_serializer_names(self):
        names = re.findall(r"^class (\w+)", open("apps/reviews/interfaces/api/v1/serializers.py").read(), re.M)
        assert len(names) == len(set(names))
